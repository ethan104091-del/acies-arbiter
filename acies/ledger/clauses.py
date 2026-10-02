"""條款帳的機械規則（裁判的外部記憶由後端維護，裁判只讀帳、寫帳）。

- 生效：effective_gh ≤ gh 且狀態 pending → active（後端於每小時標記，裁判不算延遲）。
- 取代：新條款宣告 supersedes；**被取代自新條款生效小時起**（判例 §二十八 28.3），生效前舊條款照常展開。
  裁判在登記時就把舊條款標 superseded 的更新會被改成「待取代」，只記 superseded_by。
- 應變：觸發即 consumed（記 consumed_gh）；不跨 tick，tick 邊界未消耗者標 expired。
- 位移類應變：觸發且產生行軍動作時，後端自動合成一條常設條款「{應變}→(x,y)」，直到該編隊抵達才 completed；
  跨 tick 不停（60_指揮 §2.3）。裁判不必自己記得。
- 滯回計數器：phase 裡以 `_hours`／`_count` 結尾的數值每小時只能 +1 或歸零（例：連續 2 小時未遭砲擊）。
- 自我約束：phase["expires_gh"] 到期即 expired。
- 完整性（G9）：每條 armed 應變恰一筆檢查；每條 active 常設條款有更新或被引用（後者只記警告）。
"""
import re

COUNTER_KEY = re.compile(r"(_hours|_count|計數)$")
SYNTH_MARK = "合成：應變位移"


def activate_due(clauses, gh):
    """pending → active；新生效的條款使其 supersedes 所列（及 superseded_by 指向它）的條款轉 superseded。"""
    by_id = {c["clause_id"]: c for c in clauses}
    changed, superseded = [], []
    for c in clauses:
        if c["status"] == "pending" and c.get("effective_gh") is not None and c["effective_gh"] <= gh:
            c["status"] = "active"; changed.append(c["clause_id"])
            for old_id in (c.get("supersedes") or []):
                old = by_id.get(old_id)
                if old and old["status"] in ("pending", "active"):
                    old["status"] = "superseded"; old["superseded_by"] = c["clause_id"]; superseded.append(old_id)
            for old in clauses:
                if old.get("superseded_by") == c["clause_id"] and old["status"] in ("pending", "active"):
                    old["status"] = "superseded"; superseded.append(old["clause_id"])
    return changed, superseded


def counter_errors(updates, clauses):
    """滯回計數器：新值只能是 0 或舊值 +1。回傳 [(編號, 說明)]。"""
    by_id = {c["clause_id"]: c for c in clauses}
    errs = []
    for u in updates:
        ph = u.get("phase") or {}
        old = (by_id.get(u["clause_id"]) or {}).get("phase") or {}
        for k, v in ph.items():
            if not COUNTER_KEY.search(str(k)) or not isinstance(v, (int, float)):
                continue
            ov = old.get(k, 0)
            if not (v == 0 or v == (ov if isinstance(ov, (int, float)) else 0) + 1):
                errs.append(("G10", f"條款 {u['clause_id']} 的計數器 {k} 由 {ov} 變 {v}：每小時只能 +1 或歸零"))
    return errs


def normalize_update(update, clauses, gh):
    """登記期把舊條款標 superseded 的更新改為「待取代」：只記 superseded_by，狀態不動（28.3）。回傳修正後的更新。"""
    by_id = {c["clause_id"]: c for c in clauses}
    u = dict(update)
    if u.get("status") == "superseded" and u.get("superseded_by"):
        succ = by_id.get(u["superseded_by"])
        if succ is None or succ["status"] == "pending" or (succ.get("effective_gh") or 0) > gh:
            u.pop("status")
    if u.get("status") == "consumed" and u.get("consumed_gh") is None:
        u["consumed_gh"] = gh
    return u


def synthesize_displacements(decision, clauses, gh):
    """應變觸發且含行軍動作 → 合成常設條款。回傳新條款 dict 清單（已存在者不重建）。"""
    fired = {c["cont_id"] for c in decision.get("contingency_checks", []) if c.get("fired")}
    existing = {c["clause_id"] for c in clauses}
    by_id = {c["clause_id"]: c for c in clauses}
    out = []
    for a in decision.get("actions", []):
        p = a.get("provenance", {})
        if a.get("verb") != "march" or p.get("clause_id") not in fired:
            continue
        cont = by_id.get(p["clause_id"], {})
        uid, dest = a["args"]["uid"], a["args"]["dest"]
        cid = f"{p['clause_id']}→({dest[0]},{dest[1]})"
        if cid in existing:
            continue
        existing.add(cid)
        out.append({"clause_id": cid, "side": cont.get("side") or p.get("side"), "kind": "standing", "tick": cont.get("tick"),
                    "text": f"應變位移：{uid} 移動至 ({dest[0]},{dest[1]}) 為止（{SYNTH_MARK}，源自 {p['clause_id']}）",
                    "level": None, "issued_gh": gh, "effective_gh": gh, "status": "active", "units": [uid],
                    "supersedes": [], "superseded_by": None, "phase": {uid: f"march→({dest[0]},{dest[1]})", "_origin": p["clause_id"],
                                                                      "_dest": [int(dest[0]), int(dest[1])]},
                    "predicate": SYNTH_MARK})
    return out


def complete_arrivals(clauses, state):
    """合成位移條款：編隊已在目的地 → completed。回傳完成的條款 id。"""
    done = []
    for c in clauses:
        if c.get("predicate") != SYNTH_MARK or c["status"] != "active":
            continue
        dest = (c.get("phase") or {}).get("_dest")
        units = c.get("units") or []
        if dest and all(list(state["units"].get(u, {}).get("pos", [])) == list(dest) for u in units):
            c["status"] = "completed"; done.append(c["clause_id"])
    return done


def expire_self_constraints(clauses, gh):
    done = []
    for c in clauses:
        exp = (c.get("phase") or {}).get("expires_gh")
        if c["kind"] == "self_constraint" and c["status"] == "active" and isinstance(exp, (int, float)) and gh >= exp:
            c["status"] = "expired"; done.append(c["clause_id"])
    return done


def tick_boundary(clauses, gh):
    """tick 邊界：未消耗的應變 → expired；合成位移條款與常設條款續行。"""
    done = []
    for c in clauses:
        if c["kind"] == "contingency" and c["status"] in ("pending", "active"):
            c["status"] = "expired"; done.append(c["clause_id"])
    return done


def armed_contingencies(clauses, tick):
    return [c for c in clauses if c["kind"] == "contingency" and c["tick"] == tick
            and c["status"] in ("pending", "active")]


def active_standing(clauses):
    return [c for c in clauses if c["kind"] in ("standing", "self_constraint") and c["status"] == "active"
            and c.get("predicate") != SYNTH_MARK]


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
