"""判例審查：機械檢查、辯論收斂、落地寫檔（用暫存副本）、整桌流程（假審查官）。"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import acies  # noqa: E402,F401
import arbiter as ar  # noqa: E402
from acies.review import checks, debate, run as review_run, writer  # noqa: E402
from acies.db import models as M  # noqa: E402
from acies.db import session as S  # noqa: E402
from acies.service import tables  # noqa: E402
from sqlalchemy import select  # noqa: E402

R1 = {"ruling_id": "R-1", "gh": 12, "condition": "同一小時既受命構工又受命固守", "effect": "主動作為構工",
      "basis": "50_工事 §4", "beneficiary": "neutral", "anchor": None, "why_not_tier1": "", "tier2_used": False}


def _review(verdict, revision=None, amendment=None, ok=True):
    return {"derivable_from_rules": True, "derivation": "50_工事 §4 已寫固守不構成構工", "conflicts": [],
            "exploit": "無", "beneficiary_ok": ok, "beneficiary_should_be": "neutral", "verdict": verdict,
            "revision": revision, "amendment": amendment, "reasoning": "理由。"}


def test_checks_form_and_numbers():
    bad = {**R1, "condition": "藍軍於夜間", "effect": "大概少 37 人", "basis": ""}
    f = checks.form_checks(bad)
    kinds = {k for k, _ in f}
    assert "形式" in kinds and "欄位" in kinds
    assert checks.number_provenance(bad, "規則全文裡沒有那個數") == [("數字", "效果中的數字 37 在規則書找不到出處")]
    assert not checks.number_provenance({"effect": "上限 8%"}, "飽和上限 8%")


def test_impact_formula_relative_to_game():
    apps = [{"measurement": {"allies": {"points_delta": 30, "ratio": 0.001}, "axis": {"points_delta": 0, "ratio": 0}}}] * 2
    imp = checks.impact(apps, {"allies": 1300, "axis": 1370})
    assert imp["limit_points"] == ar.TIE_BAND * 1370 and imp["flagged"]          # 60 > 27.4
    assert not checks.impact(apps[:1], {"allies": 13000, "axis": 13700})["flagged"]


def test_debate_converges_and_disputes():
    calls = []
    def ask(name, ruling, ck, apps, *, role, opponent=None, round_=0):
        calls.append((name, round_))
        if name == "claude": return _review("定案"), {}
        return (_review("推翻") if round_ == 0 else _review("定案")), {}   # 乙看到甲的意見後改口
    r = debate.run(R1, {}, [], ask, log=lambda *_: None)
    assert r["outcome"] == "定案" and len(r["rounds"]) == 2 and (("codex", 1) in calls)
    def stubborn(name, ruling, ck, apps, *, role, opponent=None, round_=0):
        return (_review("定案") if name == "claude" else _review("推翻")), {}
    r = debate.run(R1, {}, [], stubborn, log=lambda *_: None)
    assert r["outcome"] == "爭議" and len(r["rounds"]) == debate.MAX_ROUNDS + 1


def test_same_verdict_different_text_gets_merged():
    def ask(name, ruling, ck, apps, *, role, opponent=None, round_=0, merge_of=None):
        if merge_of:
            return _review("改寫", {"condition": "合稿條件", "effect": "合稿效果"}), {}
        rev = {"condition": "甲的條件寫法", "effect": "甲的效果"} if name == "claude" else {"condition": "乙的完全不同寫法", "effect": "乙的另一效果"}
        return _review("改寫", rev), {}
    r = debate.run(R1, {}, [], ask, log=lambda *_: None)
    assert r["outcome"] == "改寫" and r["final"]["revision"]["condition"] == "合稿條件" and r["rounds"][-1]["round"] == "合稿"


def test_rewrite_agreement_needs_similar_text():
    a = _review("改寫", {"condition": "編隊受命固守某座標而不在該格", "effect": "就地待機"})
    b = _review("改寫", {"condition": "編隊受命固守某座標而不在該格時", "effect": "就地待機，不視為位移"})
    c = _review("改寫", {"condition": "完全不同的條件", "effect": "完全不同的效果"})
    assert debate.agree(a, b) and not debate.agree(a, c)


def test_writer_appends_precedent_and_annotates_rule(tmp_path, monkeypatch):
    law = tmp_path / "law"; law.mkdir(); rules = tmp_path / "rules"; rules.mkdir()
    (law / "precedents.md").write_text("# 判例\n\n## §二十八 舊節\n\n內容\n")
    (rules / "60_指揮.md").write_text("# 60 指揮\n\n## §2 命令的兩欄\n\n表格\n\n## §3 提交窗口\n\n文\n")
    monkeypatch.setattr(writer, "PRECEDENTS", law / "precedents.md")
    monkeypatch.setattr(writer, "RULES", rules)
    monkeypatch.setattr(writer, "LOG_DIR", law / "review_log")
    assert writer.next_section_no() == 29 and writer.cn(29) == "二十九" and writer.cn(10) == "十" and writer.cn(21) == "二十一"
    res = {"outcome": "改寫", "final": _review("改寫", {"condition": "c", "effect": "e"},
                                              {"file": "60_指揮.md", "section": "§2", "sentence": "取代自新條款生效小時起。"}),
           "rounds": [{"round": 0, "reviews": {}}]}
    applied = writer.apply("tbl-1234-5678", R1, res, {"findings": [], "impact": {"points_delta": {}}})
    assert applied["section_no"] == 29 and len(applied["changes"]) == 2
    assert "## §二十九" in (law / "precedents.md").read_text()
    rt = (rules / "60_指揮.md").read_text()
    assert "★ 判例 §二十九" in rt and rt.index("★ 判例 §二十九") < rt.index("## §3")
    p = writer.write_log("tbl-1234-5678", [{"ruling_id": "R-1", "outcome": "改寫", "changes": applied["changes"], "checks": {}, "rounds": res["rounds"]}])
    assert p.exists() and "改動前" in p.read_text()


def test_run_table_with_fake_reviewers(db_engine, tmp_path, monkeypatch):
    law = tmp_path / "law"; law.mkdir(); rules = tmp_path / "rules"; rules.mkdir()
    (law / "precedents.md").write_text("# 判例\n"); (rules / "50_工事.md").write_text("# 50\n\n## §4 工時池\n\n文\n")
    monkeypatch.setattr(writer, "PRECEDENTS", law / "precedents.md"); monkeypatch.setattr(writer, "RULES", rules)
    monkeypatch.setattr(writer, "LOG_DIR", law / "review_log")
    with S.session() as db:
        t, _ = tables.create_table(db, "審查測試")
        db.add(M.Ruling(table_id=t.id, ruling_id="R-1", seq=1, gh=0, body={k: v for k, v in R1.items() if k not in ("ruling_id", "gh", "tier2_used")}, text_hash="x"))
        db.add(M.Ruling(table_id=t.id, ruling_id="R-2", seq=2, gh=0, body={"condition": "c2", "effect": "人員 -50", "basis": "b", "beneficiary": "neutral"}, text_hash="y"))
        snap = tables.latest_snapshot(db, t.id, 0)
        db.add(M.Decision(table_id=t.id, gh=0, attempt=1, kind="resolve", committed=True, status="committed",
                          decision={"actions": [{"seq": 1, "tier": 2, "ruling_id": "R-2",
                                                 "applied": [{"primitive": "hurt", "args": {"uid": "RED-1", "personnel": 50}}],
                                                 "provenance": {"side": "axis", "clause_id": "x", "quote": "q"}}]},
                          execution={"events": [["both", "裁示 R-2"]]}))
        db.commit(); tid = t.id
    def ask(name, ruling, ck, apps, *, role, opponent=None, round_=0):
        if ruling["ruling_id"] == "R-1": return _review("定案"), {}
        return _review("推翻", amendment={"file": "50_工事.md", "section": "§4", "sentence": "不得以裁示直接扣人。"}), {}
    entries = review_run.run_table(tid, ask=ask, log=lambda *_: None)
    assert [e["outcome"] for e in entries] == ["定案", "推翻"]
    assert entries[1]["checks"]["impact"]["applications"] == 1
    txt = (law / "precedents.md").read_text()
    assert "## §一" in txt and "## §二" in txt and "推翻，不入判例" in txt
    assert "★ 判例 §二" in (rules / "50_工事.md").read_text()
    with S.session() as db:
        st = {r.ruling_id: r.body.get("status") for r in db.scalars(select(M.Ruling).where(M.Ruling.table_id == tid))}
        assert st == {"R-1": "precedent", "R-2": "overturned"}
    # 已審過的不再重審
    assert review_run.run_table(tid, ask=ask, log=lambda *_: None) == []


if __name__ == "__main__":
    print("用 pytest 跑")
