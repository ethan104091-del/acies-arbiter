"""假裁判：不呼叫模型。登記卷宗不做事；解算卷宗讓每個受指揮編隊待機。
第一階段端到端測試用，也是「最小解讀」的基準行為。"""
import arbiter as ar


def decide(work):
    s, gh, kind = work["state"], work["gh"], work["kind"]
    if kind == "register":
        return {"schema": "acies.HourDecision/1", "kind": "register", "gh": gh}
    actions = []
    for uid, u in sorted(s["units"].items()):
        if u.get("side") in ("allies", "axis") and ar.under_command(s, uid):
            actions.append({"seq": len(actions) + 1, "tier": 1, "verb": "hold", "args": {"uid": uid},
                            "provenance": {"side": u["side"], "clause_id": f"{'藍' if u['side']=='allies' else '紅'}T{work['tick']}-維持",
                                           "quote": "維持原命令"}})
    return {"schema": "acies.HourDecision/1", "kind": "resolve", "gh": gh, "actions": actions}
