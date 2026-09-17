"""裁判工作者：卷宗確定性、假模型跑完一 tick、退回後重出、連續退回掛起。不呼叫真模型。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import acies  # noqa: E402,F401
from acies.db import models as M  # noqa: E402
from acies.db import session as S  # noqa: E402
from acies.referee import dossier, stub, worker  # noqa: E402
from acies.service import tables, rounds, work  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _new_table(db):
    t, tok = tables.create_table(db, "工作者測試")
    for sd, k in (("allies", "a"), ("axis", "x")):
        rounds.submit_order(db, t, sd, 0, "## 命令\n1. [—] 維持原命令", k)
    db.commit()
    return t.id


def test_dossier_deterministic(db_engine):
    with S.session() as db:
        tid = _new_table(db)
        w = work.claim(db, "w0"); db.commit()
        w["rulings"] = []
    pa = dossier.prefix_a()
    d1, d2 = dossier.build(w, pa), dossier.build(w, pa)
    assert d1["hash"] == d2["hash"] and d1["prefix_a_hash"] == d2["prefix_a_hash"]
    ids = [b["id"] for b in d1["blocks"]]
    assert ids[:3] == ["A1", "A2", "A3"] and "A5.precedents" in ids and ids[-1] == "C"
    assert "裁判手冊 v2" in d1["system"][0]["text"] and "全知狀態" in d1["user"]
    assert d1["system"][0]["cache_control"]["ttl"] == "1h"
    assert sum(b["chars"] for b in d1["blocks"] if b["id"].startswith("A")) > 80_000   # 字元數；2026-09-11 規則書重整後前綴約 11.5 萬字


def _fake_model(system, messages, *, model, effort, **_):
    """假模型：從尾段讀出 gh 與種類，回傳假裁判的決定。"""
    user = messages[0]["content"]
    gh = int(user.split("gh")[1].split("　")[0])
    kind = "register" if "卷宗種類：**register**" in user else "resolve"
    with S.session() as db:
        t = db.scalar(select(M.Table))
        snap = tables.latest_snapshot(db, t.id, gh)
        d = stub.decide({"state": snap.state, "gh": gh, "kind": kind, "tick": t.tick})
    return d, {"text": json.dumps(d, ensure_ascii=False), "usage": {"input_tokens": 1, "output_tokens": 1}, "request_id": "fake"}


def test_worker_runs_a_tick_with_fake_model(db_engine):
    with S.session() as db:
        tid = _new_table(db)
    pa = dossier.prefix_a()
    kinds = []
    for _ in range(10):
        r = worker.run_one("w1", decide=_fake_model, prefix_a=pa, log=lambda *_: None)
        if r is None:
            break
        kinds.append(r.get("kind") or r["status"])
    assert kinds == ["register"] + ["resolve"] * 6
    with S.session() as db:
        t = db.get(M.Table, tid)
        assert t.tick == 1 and t.global_hour == 6
        ds = db.scalars(select(M.Dossier).where(M.Dossier.table_id == tid)).all()
        assert len(ds) == 7 and all(d.dossier_hash for d in ds)
        assert len({d.request["system_hashes"][0] for d in ds}) == 1       # 前綴 A 整局同一雜湊


def test_worker_retries_then_suspends(db_engine):
    with S.session() as db:
        tid = _new_table(db)
    calls = []

    def bad_model(system, messages, *, model, effort, **_):
        calls.append(len(messages))
        d = {"schema": "acies.HourDecision/1", "kind": "register", "gh": 0,
             "rulings": [{"ruling_id": "R", "condition": "藍軍夜間", "effect": "大概減半"}]}
        return d, {"text": json.dumps(d), "usage": {}}

    r = worker.run_one("w1", decide=bad_model, prefix_a=dossier.prefix_a(), log=lambda *_: None)
    assert r["status"] == "suspended" and calls == [1, 3, 5, 7]      # 預設最多 4 次，每次在同對話追加錯誤、升功率
    with S.session() as db:
        t = db.get(M.Table, tid)
        assert t.status == M.TableStatus.awaiting_adjudication
        p = db.scalar(select(M.Pending).where(M.Pending.table_id == tid))
        assert p.kind == "audit_failed" and p.body["errors"]
