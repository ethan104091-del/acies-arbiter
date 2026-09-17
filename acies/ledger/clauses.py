"""條款帳的機械規則（裁判的外部記憶由後端維護，裁判只讀帳、寫帳）。

- 生效：effective_gh ≤ gh 且狀態 pending → active（後端於每小時尾段標記，裁判不算延遲）。
- 取代：新條款宣告 supersedes → 舊條款 superseded_by；未宣告者續行。
- 應變：不跨 tick，tick 邊界全部標 expired；觸發即 consumed。
- 完整性（G9）：每條 active 條款每小時要有更新或被動作引用；每條 armed 應變恰一筆檢查。
"""


def activate_due(clauses, gh):
    changed = []
    for c in clauses:
        if c["status"] == "pending" and c.get("effective_gh") is not None and c["effective_gh"] <= gh:
            c["status"] = "active"; changed.append(c["clause_id"])
    return changed


def armed_contingencies(clauses, tick):
    return [c for c in clauses if c["kind"] == "contingency" and c["tick"] == tick
            and c["status"] in ("pending", "active")]


def active_standing(clauses):
    return [c for c in clauses if c["kind"] in ("standing", "self_constraint") and c["status"] == "active"]


def completeness_errors(decision, clauses, tick):
    """G9 的條款面：回傳 [(編號, 說明)]。"""
    errs = []
    checks = {c["cont_id"] for c in decision.get("contingency_checks", [])}
    for c in armed_contingencies(clauses, tick):
        if c["clause_id"] not in checks:
            errs.append(("G9", f"已武裝應變 {c['clause_id']} 本小時沒有檢查紀錄"))
    updated = {u["clause_id"] for u in decision.get("clause_updates", [])}
    referenced = {a["provenance"]["clause_id"] for a in decision.get("actions", [])}
    for c in active_standing(clauses):
        if c["clause_id"] not in updated and c["clause_id"] not in referenced:
            errs.append(("G9", f"生效中的條款 {c['clause_id']} 本小時既未更新也未被任何動作引用"))
    return errs
