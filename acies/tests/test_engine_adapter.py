"""動詞、執行器、命令清單、沙盒、重放器：用 Run 7 快照做一小時／一 tick 的實跑。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import acies  # noqa: E402,F401
from acies.engine import executor, hour_orders, replay, sandbox, state_io, verbs  # noqa: E402
import _audit  # noqa: E402
import arbiter as ar  # noqa: E402

RUN = ROOT / "runs" / "run7_openfield"


def _snap(t):
    return state_io.loads((RUN / f"snap_T{t}start.json").read_text())


def _decision(gh, actions, rulings=()):
    return {"schema": "acies.HourDecision/1", "gh": gh, "actions": actions, "rulings": list(rulings),
            "signals": {"allies": [], "axis": []}, "pending": [], "answers": [],
            "contingency_checks": [], "clause_updates": []}


def _prov(side, clause):
    return {"side": side, "clause_id": clause, "quote": "…"}


def test_catalogue_lists_every_verb():
    txt = verbs.render_catalogue()
    for name in verbs.VERBS:
        assert f"**{name}**" in txt
    for p in verbs.PRIMITIVES:
        assert f"- {p}" in txt


def test_primitives_cannot_increase():
    assert verbs.check_primitive_args("hurt", {"personnel": -5})
    assert verbs.check_primitive_args("add_works", {"man_hours": -1})
    assert verbs.check_primitive_args("resupply", {})       # 不在白名單
    assert not verbs.check_primitive_args("hurt", {"personnel": 5, "org": 2})


def test_hour_march_and_fire_replays_to_same_hash():
    s = _snap(5)                       # gh30，雙方已接觸
    gh = s["global_hour"]
    d = _decision(gh, [
        {"seq": 1, "tier": 1, "verb": "fire",
         "args": {"shooters": ["BLU-1-a1", "BLU-1-a2"], "target": "RED-3-rcn", "mission": "急襲"},
         "provenance": _prov("allies", "藍T5-1")},
        {"seq": 2, "tier": 1, "verb": "march", "args": {"uid": "RED-AD", "dest": [16, 8]},
         "provenance": _prov("axis", "紅T5-1")},
        {"seq": 3, "tier": 1, "verb": "dig", "args": {"uid": "RED-1"}, "provenance": _prov("axis", "紅T5-3")},
    ])
    before = _audit.snapshot(s)
    a = state_io.clone(s)
    line, ex = executor.execute_hour(a, d, first_hour_of_tick=True)
    assert a["global_hour"] == gh + 1 and "RED-3-rcn" in line
    assert any(r["verb"] == "fire" and r["applied"] for r in ex.results)
    # v1 稽核（含 A3–A8）以決定紀錄轉出的命令清單通過
    mf = hour_orders.to_manifest(s, d, tick=5, gh=gh)
    findings = _audit.run(a, before, mf)
    errors = [(k, m) for k, items in findings.items() for sev, m in items if sev == "錯誤"]
    assert not errors, errors
    # 重放得到相同雜湊
    d["end_state_hash"] = state_io.state_hash(a)
    _final, rows = replay.replay(s, [d])
    assert rows == [(gh, d["end_state_hash"], True)]


def test_tier2_requires_ruling_and_records_it():
    s = _snap(5); gh = s["global_hour"]
    r = {"ruling_id": "R-t-001", "condition": "夜間隱蔽機動之編隊", "effect": "組織度 -5",
         "basis": "movement_v1 未涵蓋", "beneficiary": "neutral", "precedent": True}
    d = _decision(gh, [
        {"seq": 1, "tier": 2, "ruling_id": "R-t-001",
         "applied": [{"primitive": "hurt", "args": {"uid": "RED-AD", "org": 5}}],
         "provenance": _prov("axis", "紅T5-2")},
        {"seq": 2, "tier": 1, "verb": "hold", "args": {"uid": "RED-AD"}, "provenance": _prov("axis", "紅T5-2")},
    ], rulings=[r])
    org0 = s["units"]["RED-AD"]["org"]
    m = sandbox.measure(s, d)
    assert not sandbox.exceeds(m)
    line, ex = executor.execute_hour(s, d, first_hour_of_tick=True)
    assert ex.rulings_applied and ex.rulings_applied[0]["ruling_id"] == "R-t-001"
    assert s["units"]["RED-AD"]["org"] < org0
    assert any(x.get("kind") == "裁示" for x in s["record"])
    # 指向不存在的裁示 → 拒絕
    bad = _decision(gh + 1, [{"seq": 1, "tier": 2, "ruling_id": "nope", "applied": [],
                              "provenance": _prov("axis", "x")}])
    try:
        executor.execute_hour(s, bad)
        assert False, "應拒絕"
    except executor.ExecutionError:
        pass


def test_assault_uses_engine_push():
    s = _snap(8); gh = s["global_hour"]
    # 找一組相鄰的敵我編隊
    pair = None
    for a, ua in s["units"].items():
        if ua["side"] != "allies" or ar.status_of(ua) not in ar.COMBAT_STATUSES: continue
        for b, ub in s["units"].items():
            if ub["side"] == "axis" and ar.status_of(ub) in ar.COMBAT_STATUSES and ar.dist(ua["pos"], ub["pos"]) == 1:
                pair = (a, ub["pos"]); break
        if pair: break
    if not pair:
        return
    d = _decision(gh, [{"seq": 1, "tier": 1, "verb": "assault", "args": {"attackers": [pair[0]], "hex": pair[1]},
                        "provenance": _prov("allies", "藍T8-應變1")}])
    line, ex = executor.execute_hour(s, d, first_hour_of_tick=True)
    res = ex.results[0]["result"]
    assert res is None or "displaced" in res


def test_sandbox_threshold():
    s = _snap(5); gh = s["global_hour"]
    big = _decision(gh, [{"seq": 1, "tier": 2, "ruling_id": "R", "applied": [
        {"primitive": "hurt", "args": {"uid": "RED-1", "personnel": 3000}}], "provenance": _prov("axis", "x")}],
        rulings=[{"ruling_id": "R", "condition": "c", "effect": "e"}])
    assert sandbox.exceeds(sandbox.measure(s, big))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"✅ {name}")


def test_manifest_carries_prior_hours_of_the_tick():
    """前小時挖過、本小時改做別的：A3 對照整個 tick 的構工帳，命令清單必須帶入前小時的登記。"""
    s = _snap(5); gh = s["global_hour"]
    h1 = _decision(gh, [{"seq": 1, "tier": 1, "verb": "dig", "args": {"uid": "RED-1"}, "provenance": _prov("axis", "紅T5-3")}])
    before = _audit.snapshot(s)
    executor.execute_hour(s, h1, first_hour_of_tick=True)
    h2 = _decision(gh + 1, [{"seq": 1, "tier": 1, "verb": "hold", "args": {"uid": "RED-1"}, "provenance": _prov("axis", "紅T5-3")}])
    b2 = _audit.snapshot(s)
    executor.execute_hour(s, h2)
    bad = hour_orders.to_manifest(s, h2, tick=5, gh=gh + 1)
    assert any(sev == "錯誤" for sev, _ in _audit.check_dig_authorized(s, b2, bad))
    good = hour_orders.to_manifest(s, h2, tick=5, gh=gh + 1, prior_decisions=[h1])
    assert not _audit.check_dig_authorized(s, b2, good)


def test_unknown_verb_args_are_rejected_not_crash():
    from acies.referee import validate
    s = _snap(5); gh = s["global_hour"]
    d = _decision(gh, [{"seq": 1, "tier": 1, "verb": "fire",
                        "args": {"shooters": ["BLU-1-a1"], "target": "RED-3-rcn", "mission": "急襲", "cas": 5},
                        "provenance": _prov("allies", "藍T5-1")}])
    assert any(c == "結構" and "多了未定義的參數" in m for c, m in validate.validate(d, s))
    try:
        executor.execute_hour(state_io.clone(s), d, first_hour_of_tick=True)
        assert False
    except executor.ExecutionError:
        pass
