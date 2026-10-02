"""條款帳：取代自生效起、計數器、合成位移條款、到期與 tick 邊界；純函式＋整段流程。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import acies  # noqa: E402,F401
from acies.ledger import clauses as L  # noqa: E402
from acies.referee import stub  # noqa: E402
from acies.db import models as M  # noqa: E402
from acies.db import session as S  # noqa: E402
from acies.service import rounds, tables, work  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _c(cid, kind="standing", status="active", **kw):
    d = {"clause_id": cid, "side": "allies", "kind": kind, "tick": 0, "text": cid, "level": None, "issued_gh": 0,
         "effective_gh": 0, "status": status, "units": [], "supersedes": [], "superseded_by": None, "phase": {},
         "predicate": None, "consumed_gh": None}
    d.update(kw); return d


def test_supersession_takes_effect_at_activation():
    old = _c("藍T0-1"); new = _c("藍T1-1", status="pending", effective_gh=8, supersedes=["藍T0-1"])
    cs = [old, new]
    assert L.activate_due(cs, 7) == ([], []) and old["status"] == "active"
    changed, sup = L.activate_due(cs, 8)
    assert changed == ["藍T1-1"] and sup == ["藍T0-1"] and old["status"] == "superseded" and old["superseded_by"] == "藍T1-1"


def test_registration_cannot_supersede_early():
    cs = [_c("藍T0-1"), _c("藍T1-1", status="pending", effective_gh=8)]
    u = L.normalize_update({"clause_id": "藍T0-1", "status": "superseded", "superseded_by": "藍T1-1"}, cs, 6)
    assert "status" not in u and u["superseded_by"] == "藍T1-1"
    u2 = L.normalize_update({"clause_id": "藍T0-應變1", "status": "consumed"}, cs, 6)
    assert u2["consumed_gh"] == 6


def test_counters_only_increment_or_reset():
    cs = [_c("藍T0-應變4", kind="contingency", phase={"clean_hours": 1})]
    ok = [{"clause_id": "藍T0-應變4", "phase": {"clean_hours": 2}}]
    bad = [{"clause_id": "藍T0-應變4", "phase": {"clean_hours": 3}}]
    reset = [{"clause_id": "藍T0-應變4", "phase": {"clean_hours": 0}}]
    assert not L.counter_errors(ok, cs) and not L.counter_errors(reset, cs)
    assert L.counter_errors(bad, cs)[0][0] == "G10"


def test_synthetic_displacement_and_arrival():
    cs = [_c("藍T0-應變6", kind="contingency")]
    d = {"contingency_checks": [{"cont_id": "藍T0-應變6", "fired": True}],
         "actions": [{"seq": 1, "verb": "march", "args": {"uid": "BLU-SF", "dest": [6, 4]},
                      "provenance": {"side": "allies", "clause_id": "藍T0-應變6"}}]}
    new = L.synthesize_displacements(d, cs, 3)
    assert len(new) == 1 and new[0]["clause_id"] == "藍T0-應變6→(6,4)" and new[0]["predicate"] == L.SYNTH_MARK
    assert not L.synthesize_displacements(d, cs + new, 4)          # 不重建
    cs2 = cs + new
    assert L.complete_arrivals(cs2, {"units": {"BLU-SF": {"pos": [5, 4]}}}) == []
    assert L.complete_arrivals(cs2, {"units": {"BLU-SF": {"pos": [6, 4]}}}) == ["藍T0-應變6→(6,4)"]
    assert new[0]["status"] == "completed"


def test_expiry_rules():
    cs = [_c("藍T0-應變1", kind="contingency"), _c("藍T0-應變2", kind="contingency", status="consumed"),
          _c("藍T0-應變6→(6,4)", predicate=L.SYNTH_MARK), _c("藍T0-約束", kind="self_constraint", phase={"expires_gh": 10})]
    assert L.expire_self_constraints(cs, 9) == [] and L.expire_self_constraints(cs, 10) == ["藍T0-約束"]
    assert L.tick_boundary(cs, 6) == ["藍T0-應變1"]
    assert [c["status"] for c in cs] == ["expired", "consumed", "active", "expired"]
    assert L.active_standing(cs) == []          # 合成條款不列入 G9 的常設清單


def _run(client, tid, worker, decide):
    w = client.post("/work/claim", json={"worker_id": worker}).json()
    assert w is not None
    d = decide(w)
    r = client.post(f"/work/{tid}/decision", json={"worker_id": worker, "decision": d}).json()
    return w, r


def test_ledger_through_a_tick(client):
    r = client.post("/tables", json={}).json(); tid, tok = r["table_id"], r["tokens"]
    for sd, k in (("allies", "a"), ("axis", "x")):
        client.put(f"/tables/{tid}/rounds/0/order", headers={"Authorization": f"Bearer {tok[sd]}"},
                   json={"text": "維持", "idempotency_key": k})
    # 登記：一條常設、一條應變、一條到期自我約束
    def reg(w):
        d = stub.decide(w)
        d["clause_updates"] = [
            {"clause_id": "藍T0-1", "side": "allies", "kind": "standing", "text": "BLU-SF 偵察", "status": "active", "units": ["BLU-SF"]},
            {"clause_id": "藍T0-應變6", "side": "allies", "kind": "contingency", "text": "若… 則 BLU-SF 前往 (6,4)", "status": "active", "units": ["BLU-SF"]},
            {"clause_id": "藍T0-約束", "side": "allies", "kind": "self_constraint", "text": "gh3 前不射擊", "status": "active", "phase": {"expires_gh": 3}},
        ]
        return d
    w, res = _run(client, tid, "w1", reg); assert res["status"] == "committed"
    # gh0：應變觸發、BLU-SF 行軍 → 後端合成位移條款
    def h0(w):
        d = stub.decide(w)
        d["actions"] = [a for a in d["actions"] if a["args"]["uid"] != "BLU-SF"]
        d["actions"].append({"seq": 99, "tier": 1, "verb": "march", "args": {"uid": "BLU-SF", "dest": [3, 2]},
                             "provenance": {"side": "allies", "clause_id": "藍T0-應變6", "quote": "若…則前往"}})
        d["contingency_checks"] = [{"cont_id": "藍T0-應變6", "evaluated": True, "fired": True, "evidence": "條件成立"}]
        d["clause_updates"] = [{"clause_id": "藍T0-應變6", "status": "consumed"}, {"clause_id": "藍T0-1", "phase": {"BLU-SF": "改依應變"}}]
        return d
    w, res = _run(client, tid, "w1", h0); assert res["status"] == "committed", res
    with S.session() as db:
        cl = {c.clause_id: c for c in db.scalars(select(M.Clause).where(M.Clause.table_id == tid)).all()}
        assert "藍T0-應變6→(3,2)" in cl and cl["藍T0-應變6→(3,2)"].status == "active"
        assert cl["藍T0-應變6"].status == "consumed" and cl["藍T0-應變6"].consumed_gh == 0
    # gh1、gh2：照合成條款續行；抵達即 completed（BLU-SF 由 (2,2) 到 (3,2) 一格，特戰旅 1.0 格/時）
    def hn(w):
        d = stub.decide(w)
        d["actions"] = [a for a in d["actions"] if a["args"]["uid"] != "BLU-SF"]
        d["actions"].append({"seq": 99, "tier": 1, "verb": "march", "args": {"uid": "BLU-SF", "dest": [3, 2]},
                             "provenance": {"side": "allies", "clause_id": "藍T0-應變6→(3,2)", "quote": "合成"}})
        d["clause_updates"] = [{"clause_id": "藍T0-1", "phase": {"BLU-SF": "依合成條款"}}]
        return d
    w, res = _run(client, tid, "w1", hn); assert res["status"] == "committed", res
    with S.session() as db:
        cl = {c.clause_id: c for c in db.scalars(select(M.Clause).where(M.Clause.table_id == tid)).all()}
        assert cl["藍T0-應變6→(3,2)"].status == "completed"
    # 計數器：跳兩格被擋
    def bad(w):
        d = stub.decide(w); d["clause_updates"] = [{"clause_id": "藍T0-1", "phase": {"clean_hours": 2}}]; return d
    w, res = _run(client, tid, "w1", bad); assert res["status"] == "rejected" and any(e[0] == "G10" for e in res["errors"])
    # 被退回的小時租約仍在手上：同一工作者直接重送（與真實工作者一致），不再取件
    good = lambda w: {**stub.decide(w), "clause_updates": [{"clause_id": "藍T0-1", "phase": {"clean_hours": 0}}]}
    res = client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": good(w)}).json()
    assert res["status"] == "committed", res
    # 跑完本 tick：自我約束 gh3 到期、常設續行
    for _ in range(3):
        w, res = _run(client, tid, "w1", good)
        assert res["status"] == "committed", res
    with S.session() as db:
        cl = {c.clause_id: c.status for c in db.scalars(select(M.Clause).where(M.Clause.table_id == tid)).all()}
        assert cl["藍T0-約束"] == "expired" and cl["藍T0-1"] == "active" and cl["藍T0-應變6→(3,2)"] == "completed"
