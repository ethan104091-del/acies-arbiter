#!/usr/bin/env python3
"""Hour 級回合 + 命令延遲佇列 核心模組（Version B+ 對稱即時命令）。

純邏輯，不碰網路/curses，方便單測。被 server.py / 監聽 / 裁判流程共用。

時間模型（rules_v2.md §0）：
  - Tick = 6 hour，一場 max_ticks*6 個 hour。
  - global_hour = tick*6 + hour_in_tick（0 起算）。
  - game_time = 開戰 06:00 + global_hour 小時。

命令延遲（rules_v2.md §0）：
  - L1=1hr、L2=2hr、L3=3hr。命令 issued_global_hour 下達，
    effective_global_hour = issued + 延遲，到期才生效。
  - 雙方對等受同一規則。

新增 state 欄位（不動現有 units/objectives/weather/fog）：
  hour_in_tick, global_hour, phase, pending_orders[], standing_orders{}
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

GAME_DIR = Path.home() / "war-game"
STATE_PATH = GAME_DIR / "state.json"

START = datetime(1944, 8, 25, 6, 0)   # Tick 0 = 06:00 開戰（rules_v2 §0）
LEVEL_DELAY = {"L1": 1, "L2": 2, "L3": 3}
PHASES = ("tick_planning", "awaiting_hour_actions", "resolving")


# ── 時間換算 ────────────────────────────────────────────────────
def global_hour(tick, hour_in_tick):
    return tick * 6 + hour_in_tick


def split_global(gh):
    """global_hour → (tick, hour_in_tick)。"""
    return gh // 6, gh % 6


def game_time_str(gh):
    """global_hour → 'YYYY-MM-DD HH:MM' 字串。"""
    return (START + timedelta(hours=gh)).strftime("%Y-%m-%d %H:%M")


def daynight(gh):
    """回傳該 hour 的時段（白天/黃昏/夜間/黎明），對應 rules_v2 §0 日夜表。"""
    h = (START + timedelta(hours=gh)).hour
    if 6 <= h < 18:
        return "白天"
    if h == 18:
        return "黃昏"
    if h == 5:
        return "黎明"
    return "夜間"


# ── schema 升級（把舊 tick-only state 補上 hour 欄位）──────────────
def ensure_hour_fields(s):
    """就地補齊 hour 級欄位（冪等，已存在不覆蓋）。回傳 s。"""
    tick = s.get("tick", 0)
    s.setdefault("hour_in_tick", 0)
    gh = global_hour(tick, s["hour_in_tick"])
    s.setdefault("global_hour", gh)
    # game_time 對齊 global_hour（保持單一真相）
    s["game_time"] = game_time_str(s["global_hour"])
    s.setdefault("phase", "tick_planning")
    s.setdefault("pending_orders", [])
    s.setdefault("standing_orders", {"allies": "", "axis": ""})
    return s


# ── 命令延遲佇列 ─────────────────────────────────────────────────
def _new_order_id(pending):
    n = 1
    existing = {o.get("id") for o in pending}
    while f"o{n}" in existing:
        n += 1
    return f"o{n}"


def enqueue_order(s, side, level, text, extra_delay=0):
    """把一條臨時令放進延遲佇列。issued=現在，effective=issued+基準延遲+extra_delay。
    extra_delay 給指揮所機制用（未建+2 / 主+1 / 前進0，見 command.py）。回傳 order dict。"""
    if level not in LEVEL_DELAY:
        raise ValueError(f"level 必須是 L1/L2/L3，不是 {level!r}")
    gh = s["global_hour"]
    order = {
        "id": _new_order_id(s["pending_orders"]),
        "side": side,
        "issued_global_hour": gh,
        "effective_global_hour": gh + LEVEL_DELAY[level] + extra_delay,
        "level": level,
        "text": text,
        "status": "pending",
        "extra_delay": extra_delay,
    }
    s["pending_orders"].append(order)
    return order


def due_orders(s, at_global_hour=None):
    """回傳在指定 hour（預設當前）到期生效的 pending 命令清單（不改 state）。"""
    gh = s["global_hour"] if at_global_hour is None else at_global_hour
    return [o for o in s.get("pending_orders", [])
            if o.get("status") == "pending" and o.get("effective_global_hour", 0) <= gh]


def activate_due(s, at_global_hour=None):
    """把到期命令標記為 active（生效），回傳剛生效的清單。裁判結算 hour 時呼叫。"""
    due = due_orders(s, at_global_hour)
    for o in due:
        o["status"] = "active"
    return due


def pending_for(s, side):
    """某方仍未生效的命令（給該方看自己的佇列 + 倒數）。"""
    out = []
    gh = s["global_hour"]
    for o in s.get("pending_orders", []):
        if o.get("side") == side and o.get("status") == "pending":
            o2 = dict(o)
            o2["hours_until_effective"] = max(0, o["effective_global_hour"] - gh)
            out.append(o2)
    return out


# ── hour 推進 ────────────────────────────────────────────────────
def advance_hour(s):
    """把時鐘往前推 1 個 hour，更新 tick/hour_in_tick/global_hour/game_time。
    （裁判在結算完一個 hour 後呼叫；不做戰鬥解算，純時鐘。）回傳 s。"""
    gh = s["global_hour"] + 1
    tick, hit = split_global(gh)
    s["global_hour"] = gh
    s["tick"] = tick
    s["hour_in_tick"] = hit
    s["game_time"] = game_time_str(gh)
    return s


def is_tick_boundary(s):
    """當前是否在 tick 開頭（hour_in_tick==0）→ 該下新主令。"""
    return s.get("hour_in_tick", 0) == 0


def set_standing(s, side, text):
    s.setdefault("standing_orders", {})[side] = text


# ── 裁判 hour 迴圈驅動（Light 版：裁判驅動、引擎只計時）──────────────
# 用法（裁判每個 tick 跑 6 次）：
#   brief = hour_brief(s)          # 看本小時議程：到期令、日夜、應變該查什麼
#   ... 裁判依 brief 裁定移動/接觸/戰鬥/偵察、就地改 units ...
#   end_hour(s, "本小時發生了什麼")  # 記 log + 時鐘 +1
def hour_brief(s):
    """裁判每小時開頭呼叫。會把本小時到期的延遲令標為 active（這就是 L1/L2/L3
    真正生效的時刻），並回傳本小時的「議程」供裁判裁定。只動 pending_orders 狀態，
    不碰 units（戰鬥仍由裁判裁定）。"""
    gh = s["global_hour"]
    newly_active = activate_due(s)        # ← 延遲令在這一刻真正生效
    return {
        "global_hour": gh,
        "game_time": game_time_str(gh),
        "daynight": daynight(gh),
        "tick": s["tick"],
        "hour_in_tick": s["hour_in_tick"],
        "is_tick_boundary": is_tick_boundary(s),
        "newly_active_orders": newly_active,
        "active_orders": [o for o in s.get("pending_orders", [])
                          if o.get("status") == "active"],
        "pending": {side: pending_for(s, side) for side in ("allies", "axis")},
    }


def log_hour(s, summary):
    """把本小時的裁定摘要記進 hour_log（戰報/覆盤用）。"""
    s.setdefault("hour_log", []).append({
        "global_hour": s["global_hour"],
        "game_time": game_time_str(s["global_hour"]),
        "summary": summary,
    })
    return s


def end_hour(s, summary=""):
    """裁判結算完本小時後呼叫：記 log（若給 summary）、時鐘 +1。"""
    if summary:
        log_hour(s, summary)
    advance_hour(s)
    return s


# ── 載入/存檔便利 ────────────────────────────────────────────────
def load(path=STATE_PATH):
    s = json.loads(Path(path).read_text())
    return ensure_hour_fields(s)


def save(s, path=STATE_PATH):
    Path(path).write_text(json.dumps(s, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # 快速自測
    s = {"tick": 0, "game_time": "x"}
    ensure_hour_fields(s)
    assert s["global_hour"] == 0 and s["phase"] == "tick_planning"
    o = enqueue_order(s, "axis", "L2", "2Pz 改往中橋")
    assert o["effective_global_hour"] == 2
    assert due_orders(s) == []            # 還沒到期
    advance_hour(s); advance_hour(s)      # gh=2
    assert s["global_hour"] == 2 and s["hour_in_tick"] == 2
    due = activate_due(s)
    assert len(due) == 1 and due[0]["status"] == "active"
    assert pending_for(s, "axis") == []   # 已生效，不在 pending

    # ── 新增：裁判 hour 迴圈驅動 self-test ──
    s2 = ensure_hour_fields({"tick": 0, "game_time": "x"})
    enqueue_order(s2, "allies", "L2", "3AD 南下")   # gh0 下達、gh2 生效
    fired = []
    for _ in range(6):                               # 跑一個 tick 的 6 個 hour
        brief = hour_brief(s2)                       # ← 到期令在這裡 activate
        if brief["newly_active_orders"]:
            fired.append((brief["global_hour"], brief["newly_active_orders"][0]["text"]))
        end_hour(s2, f"hour {brief['hour_in_tick']} 結算")
    assert fired == [(2, "3AD 南下")], fired          # L2 令確實在 gh2（不是 gh0）生效
    assert s2["global_hour"] == 6 and s2["tick"] == 1 # 跑完 6 hour 進入下個 tick
    assert len(s2["hour_log"]) == 6                   # 每小時都有 log
    print("hourstate self-test OK:", game_time_str(2), daynight(2),
          "| hour-loop OK, L2 fired at gh=2")
