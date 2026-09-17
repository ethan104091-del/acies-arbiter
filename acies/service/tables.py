"""建桌、席位、劇本起始狀態。"""
import datetime as dt
import json
from pathlib import Path

from sqlalchemy import select

import acies
from acies.db import models as M
from acies.engine import state_io

from . import auth, events

DEFAULT_SETTINGS = {
    "llm_backend": "cli",              # cli＝這台機器的 Claude Code（訂閱方案）；api＝金鑰計費
    "model": "claude-opus-5",
    "effort_resolve": "high",
    "effort_register": "medium",
    "magnitude_power_ratio": 0.01,
    "magnitude_points": 50,
    "poll_seconds": 30,
    "lease_seconds": 900,
    "window_hours": 24,                 # 提交窗口期限；逾時未提交＝維持原命令
    "reopen_auto_confirm_minutes": 30,  # 裁示後重開，未回應方逾此分鐘數視為確認不改
    "llm_fallback_backend": None,       # 呼叫層失敗（額度、當機）時改用的後端，例 "codex"／"cli"
    "max_attempts": 4,                  # 同一小時最多呼叫次數；驗證退回時逐次提高推理強度
}

# 劇本起始狀態：純戰場用 Run 7 的 T0 起始快照（即 scenarios/openfield_setup.py 的產物，
# 直接執行該腳本會覆寫 maps/open_field_state.json，故不在此呼叫）。
SCENARIOS = {
    "open_field": acies.ROOT / "runs" / "run7_openfield" / "snap_T0start.json",
}


def scenario_state(scenario_id):
    p = SCENARIOS.get(scenario_id)
    if p is None:
        raise ValueError(f"未知劇本 {scenario_id!r}")
    return state_io.loads(Path(p).read_text())


def create_table(db, name="", scenario_id="open_field", settings=None, state=None):
    """建桌：存起始快照、開提交窗口、發四個席位的權杖（明文只回傳這一次）。
    state：直接給起始狀態（例：從某局中途的快照開桌，做裁判測試）。"""
    s = state_io.normalize(state_io.clone(state)) if state is not None else scenario_state(scenario_id)
    t = M.Table(name=name, scenario_id=scenario_id, tick=int(s.get("tick", 0)),
                global_hour=int(s.get("global_hour", 0)), max_ticks=int(s.get("max_ticks", 8)),
                status=M.TableStatus.running,
                settings={**DEFAULT_SETTINGS, **(settings or {})})
    db.add(t); db.flush()
    db.add(M.Snapshot(table_id=t.id, gh=t.global_hour, state=s, state_hash=state_io.state_hash(s)))
    tokens = {}
    for role in M.SeatRole:
        tok = auth.new_token()
        db.add(M.Seat(table_id=t.id, role=role, token_hash=auth.token_hash(tok)))
        tokens[role.value] = tok
    open_round(db, t, t.tick)
    events.emit(db, t.id, "建桌", gh=t.global_hour, scenario=scenario_id)
    db.flush()
    from . import briefs
    briefs.publish(db, t, s, t.tick)
    return t, tokens


def open_round(db, t, tick):
    now = dt.datetime.now(dt.timezone.utc)
    r = M.Round(table_id=t.id, tick=tick, status=M.RoundStatus.open, window_opened_at=now,
                window_deadline=now + dt.timedelta(hours=t.settings.get("window_hours", 24)),
                confirmed={"allies": None, "axis": None})
    db.add(r)
    events.emit(db, t.id, "窗口開啟", gh=t.global_hour, tick=tick)
    return r


def get_table(db, table_id):
    return db.get(M.Table, table_id)


def get_round(db, table_id, tick, lock=False):
    """lock=True：鎖住該列（雙方同時送命令時，confirmed 這個 JSON 欄位會互相蓋掉——2026-09-08 Run 8 T1 實際發生過）。"""
    q = select(M.Round).where(M.Round.table_id == table_id, M.Round.tick == tick)
    if lock:
        q = q.with_for_update()
    return db.scalar(q)


def latest_snapshot(db, table_id, gh):
    return db.scalar(select(M.Snapshot).where(M.Snapshot.table_id == table_id, M.Snapshot.gh == gh))
