"""工作佇列與逐小時落定（計劃 §4.10）。

一個工作項＝(桌, 小時, 種類)。種類：register（tick 首小時前的登記卷宗）或 resolve。
取件加租約；提交決定→驗證→沙盒量級→執行→稽核→落定（冪等鍵 桌／小時／attempt）。
掛起＝該小時不落定，桌轉「待人工裁定」。
"""
import datetime as dt
import hashlib

from sqlalchemy import select, update

import _audit
import arbiter as ar
import command
from acies.db import models as M
from acies.engine import executor, hour_orders, sandbox, state_io
from acies.referee import validate
from acies.ledger import clauses as clause_rules

from . import briefs, events, rounds, tables

SIDES = ("allies", "axis")


class WorkError(Exception):
    pass


def _now():
    return dt.datetime.now(dt.timezone.utc)


def pending_kind(db, t):
    """本桌目前需要的卷宗種類；無工作回 None。"""
    if t.status != M.TableStatus.running:
        return None
    r = tables.get_round(db, t.id, t.tick)
    if r is None:
        return None
    if r.status == M.RoundStatus.ready:
        return "register"
    if r.status in (M.RoundStatus.registering, M.RoundStatus.resolving):
        return "resolve"
    return None


def expire_windows(db):
    """窗口逾時：開啟中的窗口過期 → 未提交方視為「維持原命令」（command_v2 §4.2）；
    裁示後重開的窗口過了設定分鐘數 → 未回應方視為確認不改（試打時將軍常沒額度，不能讓一桌永遠停在這）。"""
    now = _now()
    rows = db.scalars(select(M.Round).join(M.Table, M.Table.id == M.Round.table_id)
                      .where(M.Table.status == M.TableStatus.running, M.Round.tick == M.Table.tick,
                             M.Round.status.in_([M.RoundStatus.open, M.RoundStatus.reopened]))).all()
    for r in rows:
        t = db.get(M.Table, r.table_id)
        missing = [sd for sd in SIDES if not (r.confirmed or {}).get(sd)]
        if not missing:
            continue
        if r.status == M.RoundStatus.open:
            if r.window_deadline and now > r.window_deadline:
                for sd in missing:
                    rounds.submit_order(db, t, sd, r.tick, "## 命令\n（逾時未提交：視為維持原命令）", f"timeout-T{r.tick}")
                events.emit(db, t.id, "窗口逾時視為維持原命令", gh=t.global_hour, sides=missing)
        else:
            mins = t.settings.get("reopen_auto_confirm_minutes", 30)
            if r.window_opened_at and (now - r.window_opened_at).total_seconds() > mins * 60:
                for sd in missing:
                    try:
                        rounds.confirm_unchanged(db, t, sd, r.tick)
                    except rounds.WindowClosed:
                        pass
                events.emit(db, t.id, "重開逾時視為確認不改", gh=t.global_hour, sides=missing)
    db.flush()


def claim(db, worker_id, lease_seconds=900):
    """取一桌可解算的工作（租約鎖定，跳過被別人持有的桌）。回傳工作描述或 None。"""
    expire_windows(db)
    now = _now()
    stmt = (select(M.Round).join(M.Table, M.Table.id == M.Round.table_id)
            .where(M.Table.status == M.TableStatus.running,
                   M.Round.tick == M.Table.tick,
                   M.Round.status.in_([M.RoundStatus.ready, M.RoundStatus.registering, M.RoundStatus.resolving]),
                   (M.Round.lease_until.is_(None)) | (M.Round.lease_until < now))
            .with_for_update(skip_locked=True).limit(1))
    r = db.scalar(stmt)
    if r is None:
        return None
    t = db.get(M.Table, r.table_id)
    r.lease_worker = worker_id
    r.lease_until = now + dt.timedelta(seconds=lease_seconds)
    kind = "register" if r.status == M.RoundStatus.ready else "resolve"
    events.emit(db, t.id, "取件", gh=t.global_hour, worker=worker_id, work_kind=kind)
    db.flush()
    return describe(db, t, kind)


def heartbeat(db, table_id, worker_id, lease_seconds=900):
    t = db.get(M.Table, table_id)
    r = tables.get_round(db, t.id, t.tick)
    if r.lease_worker != worker_id:
        raise WorkError("租約不屬於此工作者")
    r.lease_until = _now() + dt.timedelta(seconds=lease_seconds)


def release(db, table_id, worker_id):
    t = db.get(M.Table, table_id)
    r = tables.get_round(db, t.id, t.tick)
    if r and r.lease_worker == worker_id:
        r.lease_worker = None; r.lease_until = None


def describe(db, t, kind):
    """工作者要的一切：小時起始快照、雙方命令原文、條款帳、待裁定回覆、已落定的上一小時。"""
    snap = tables.latest_snapshot(db, t.id, t.global_hour)
    if snap is None:
        raise WorkError(f"gh{t.global_hour} 無快照")
    orders = rounds.current_orders(db, t.id, t.tick)
    clauses = db.scalars(select(M.Clause).where(M.Clause.table_id == t.id)).all()
    prev = db.scalar(select(M.Decision).where(M.Decision.table_id == t.id, M.Decision.gh == t.global_hour - 1,
                                              M.Decision.committed.is_(True)))
    answered = db.scalars(select(M.Pending).where(M.Pending.table_id == t.id, M.Pending.status == "answered")).all()
    r = tables.get_round(db, t.id, t.tick)
    prev_reg = None
    if kind == "register" and r is not None and (r.reopen_count or 0) > 0:
        pr = db.scalar(select(M.Decision).where(M.Decision.table_id == t.id, M.Decision.gh == t.global_hour,
                                                M.Decision.kind == "register", M.Decision.status == "committed")
                       .order_by(M.Decision.attempt.desc()).limit(1))
        prev_reg = pr.decision if pr else None
    attempt = (db.scalar(select(M.Decision.attempt).where(M.Decision.table_id == t.id, M.Decision.gh == t.global_hour,
                                                          M.Decision.kind == kind)
                         .order_by(M.Decision.attempt.desc()).limit(1)) or 0) + 1
    rl = db.scalars(select(M.Ruling).where(M.Ruling.table_id == t.id).order_by(M.Ruling.seq)).all()
    return {
        "rulings": [{"seq": x.seq, "ruling_id": x.ruling_id, "gh": x.gh, **x.body} for x in rl],
        "table_id": t.id, "kind": kind, "gh": t.global_hour, "tick": t.tick, "attempt": attempt,
        "tick_hours": t.tick_hours, "settings": t.settings,
        "state": snap.state, "state_hash": snap.state_hash,
        "orders": {sd: (o.text if o else "") for sd, o in orders.items()},
        "clauses": [_clause_dict(c) for c in clauses],
        "previous": (prev.decision if prev else None),
        "previous_register": prev_reg,
        "reopened": bool(r is not None and (r.reopen_count or 0) > 0 and kind == "register"),
        "previous_execution": (prev.execution if prev else None),
        "adjudications": [{"pending_id": p.pending_id, "kind": p.kind, "answer": p.answer} for p in answered],
    }


def _clause_dict(c):
    return {k: getattr(c, k) for k in ("clause_id", "side", "kind", "tick", "text", "level", "issued_gh",
                                       "effective_gh", "status", "units", "supersedes", "superseded_by",
                                       "phase", "predicate", "consumed_gh")}


def submit(db, table_id, worker_id, decision, dossier_id=None):
    """提交一份決定紀錄。回傳 {"status": committed|rejected|suspended, ...}。"""
    t = db.get(M.Table, table_id)
    r = tables.get_round(db, t.id, t.tick)
    if r is None or r.lease_worker != worker_id:
        raise WorkError("無租約，不得提交")
    kind = decision.get("kind", "resolve")
    expect = pending_kind(db, t)
    if kind != expect:
        raise WorkError(f"本桌現在要的是 {expect} 卷宗，收到 {kind}")
    gh = t.global_hour
    if decision.get("gh") != gh:
        raise WorkError(f"決定紀錄的 gh {decision.get('gh')} 不是本桌當前小時 {gh}")
    if kind == "register" and (r.reopen_count or 0) > 0:
        _reset_registration(db, t, gh)
    snap = tables.latest_snapshot(db, t.id, gh)
    s = state_io.clone(snap.state)
    attempt = (db.scalar(select(M.Decision.attempt).where(M.Decision.table_id == t.id, M.Decision.gh == gh,
                                                          M.Decision.kind == kind)
                         .order_by(M.Decision.attempt.desc()).limit(1)) or 0) + 1
    rec = M.Decision(table_id=t.id, gh=gh, attempt=attempt, kind=kind, dossier_id=dossier_id, decision=decision)
    db.add(rec)

    clause_rows = db.scalars(select(M.Clause).where(M.Clause.table_id == t.id)).all()
    for c in clause_rows:                      # 到期生效由後端標記，裁判不算延遲
        if c.status == "pending" and c.effective_gh is not None and c.effective_gh <= gh:
            c.status = "active"
    clause_status = {c.clause_id: c.status for c in clause_rows}
    errs = validate.validate(decision, s, kind=kind, clause_status=clause_status)
    warnings = []
    if kind == "resolve":
        for code, msg in clause_rules.completeness_errors(decision, [_clause_dict(c) for c in clause_rows], t.tick):
            (errs if "應變" in msg else warnings).append((code, msg))   # 漏檢應變仍擋；條款未更新只記警告
    if errs:
        rec.validation = [list(e) for e in errs]; rec.status = "rejected"
        events.emit(db, t.id, "決定被拒", gh=gh, attempt=attempt, errors=len(errs))
        db.flush()
        return {"status": "rejected", "errors": errs, "attempt": attempt}

    # 沙盒量級（G4）：超門檻 → 待裁定、掛桌
    m = sandbox.measure(s, decision)
    if any(a.get("tier") == 2 for a in decision.get("actions", [])) and sandbox.exceeds(
            m, power_ratio=t.settings.get("magnitude_power_ratio", 0.01), points=t.settings.get("magnitude_points", 50)):
        return _suspend(db, t, r, rec, gh, "magnitude_threshold",
                        {"measurement": m, "question": "二級動作的量級超過門檻，需人工裁定"})
    if any(p.get("material") for p in decision.get("pending", [])):
        item = next(p for p in decision["pending"] if p.get("material"))
        return _suspend(db, t, r, rec, gh, item["kind"], item)

    if kind == "register":
        decision = {**decision, "signals": {"allies": [], "axis": []}}   # 登記不解算任何事，徵候無意義，不發、不檢
        rec.decision = decision
        return _commit_register(db, t, r, rec, s, decision, gh)
    return _commit_resolve(db, t, r, rec, s, decision, gh, snap, warnings)


def suspend(db, table_id, worker_id, kind, body):
    """工作者主動掛起（模型無有效輸出、連續退回）。"""
    t = db.get(M.Table, table_id)
    r = tables.get_round(db, t.id, t.tick)
    if r is None or r.lease_worker != worker_id:
        raise WorkError("無租約")
    rec = M.Decision(table_id=t.id, gh=t.global_hour, kind=pending_kind(db, t) or "resolve",
                     attempt=(db.scalar(select(M.Decision.attempt).where(M.Decision.table_id == t.id, M.Decision.gh == t.global_hour)
                                        .order_by(M.Decision.attempt.desc()).limit(1)) or 0) + 1,
                     decision={}, status="suspended")
    db.add(rec)
    return _suspend(db, t, r, rec, t.global_hour, kind, body)


def _suspend(db, t, r, rec, gh, kind, body):
    rec.status = "suspended"
    pid = f"P-{t.id[:8]}-gh{gh}-{rec.attempt}"
    db.add(M.Pending(table_id=t.id, pending_id=pid, gh=gh, phase=rec.kind, kind=kind,
                     side=body.get("side"), clause_id=body.get("clause_id"), body=body, material=True))
    t.status = M.TableStatus.awaiting_adjudication
    r.lease_worker = None; r.lease_until = None
    events.emit(db, t.id, "掛起待裁定", gh=gh, pending_id=pid, pending_kind=kind)
    db.flush()
    return {"status": "suspended", "pending_id": pid, "attempt": rec.attempt}


def _apply_ledger(db, t, decision, gh):
    """條款帳與待裁定／問答的寫入（第一階段：直接落表；狀態機細節在第二階段）。"""
    for cu in decision.get("clause_updates", []):
        c = db.scalar(select(M.Clause).where(M.Clause.table_id == t.id, M.Clause.clause_id == cu["clause_id"]))
        if c is None:
            c = M.Clause(table_id=t.id, clause_id=cu["clause_id"], side=cu.get("side") or "allies",
                         kind=cu.get("kind") or "standing", tick=t.tick, text=cu.get("text") or "",
                         issued_gh=gh, status="pending")
            db.add(c)
        for k in ("side", "kind", "text", "level", "units", "supersedes", "superseded_by", "phase", "predicate", "status"):
            if cu.get(k) is not None:
                setattr(c, k, cu[k])
        c.history = list(c.history or []) + [{"gh": gh, "update": cu}]
    for p in decision.get("pending", []):
        if p.get("material"):
            continue
        row = db.scalar(select(M.Pending).where(M.Pending.table_id == t.id, M.Pending.pending_id == p["pending_id"]))
        if row is None:
            db.add(M.Pending(table_id=t.id, pending_id=p["pending_id"], gh=gh, phase=decision.get("kind", "resolve"),
                             kind=p["kind"], side=p.get("side"), clause_id=p.get("clause_id"), body=p, material=False))
        elif row.status == "open":
            row.body = p                      # 裁判每小時重申同一件待裁定：更新內容，不重複建檔
    for a in decision.get("answers", []):
        q = db.scalar(select(M.Question).where(M.Question.table_id == t.id, M.Question.question_id == a["question_id"]))
        if q is None:
            qid = a["question_id"]
            side = "allies" if qid.startswith(("藍", "Q-allies")) else "axis" if qid.startswith(("紅", "Q-axis")) else None
            q = M.Question(table_id=t.id, tick=t.tick, side=side or "allies", question_id=qid, text="（命令內的提問）")
            db.add(q)
        q.answer = a


def _store_rulings(db, t, decision, gh):
    n = db.scalar(select(M.Ruling.seq).where(M.Ruling.table_id == t.id).order_by(M.Ruling.seq.desc()).limit(1)) or 0
    new = []
    for r in decision.get("rulings", []):
        n += 1
        txt = f"{r['condition']} → {r['effect']}"
        db.add(M.Ruling(table_id=t.id, ruling_id=r["ruling_id"], seq=n, gh=gh, body=r,
                        text_hash=hashlib.sha256(txt.encode()).hexdigest()))
        new.append(r["ruling_id"])
    return new


def _commit_register(db, t, r, rec, s, decision, gh):
    """登記：只執行登記類動詞（進佇列，不動部隊），更新 gh 快照，回合轉 registering。

    command_v2 §4.3：登記期若公告了通則裁示（含通則答覆），該 tick 的提交窗口對雙方重開一次，
    雙方都在完整裁示集下確認後才重新登記；重新登記前把快照還原到登記前、清掉本 tick 新登記的條款。
    """
    snap = tables.latest_snapshot(db, t.id, gh)
    pre_state = state_io.clone(snap.state)
    resolve, ex = executor.make_resolve(decision)
    resolve(s, gh)
    new_rulings = _store_rulings(db, t, decision, gh)
    _apply_ledger(db, t, decision, gh)
    snap.state = s; snap.state_hash = state_io.state_hash(s)
    rec.execution = {**ex.to_dict(), "pre_state": pre_state}; rec.end_state_hash = snap.state_hash
    rec.committed = True; rec.status = "committed"
    r.lease_worker = None; r.lease_until = None
    general = new_rulings or [a for a in decision.get("answers", []) if a.get("kind") == "general"]
    if general and (r.reopen_count or 0) == 0:
        rounds.reopen_window(db, t, t.tick, why=f"登記期公告通則裁示 {new_rulings}")
        briefs.publish(db, t, pre_state, t.tick)          # 重發簡報：附上新裁示與答覆
        events.emit(db, t.id, "登記落定（窗口重開）", gh=gh, attempt=rec.attempt)
        db.flush()
        return {"status": "committed", "kind": "register", "gh": gh, "end_state_hash": snap.state_hash, "reopened": True}
    r.status = M.RoundStatus.registering
    events.emit(db, t.id, "登記落定", gh=gh, attempt=rec.attempt)
    db.flush()
    return {"status": "committed", "kind": "register", "gh": gh, "end_state_hash": snap.state_hash}


def _reset_registration(db, t, gh):
    """窗口重開後雙方再次到齊：把快照還原到上次登記前，清掉本 tick 新登記的條款（裁示與答覆保留）。"""
    prev = db.scalar(select(M.Decision).where(M.Decision.table_id == t.id, M.Decision.gh == gh,
                                              M.Decision.kind == "register", M.Decision.committed.is_(True))
                     .order_by(M.Decision.attempt.desc()).limit(1))
    if prev is None or not prev.execution or "pre_state" not in prev.execution:
        return
    snap = tables.latest_snapshot(db, t.id, gh)
    snap.state = prev.execution["pre_state"]; snap.state_hash = state_io.state_hash(snap.state)
    for c in db.scalars(select(M.Clause).where(M.Clause.table_id == t.id, M.Clause.tick == t.tick)).all():
        db.delete(c)
    prev.status = "superseded"; prev.committed = False
    events.emit(db, t.id, "登記重置", gh=gh)
    db.flush()


def _commit_resolve(db, t, r, rec, s, decision, gh, snap, warnings=()):
    before = _audit.snapshot(s)
    first = (gh % t.tick_hours == 0)
    try:
        line, ex = executor.execute_hour(s, decision, first_hour_of_tick=first)
    except executor.ExecutionError as e:
        rec.status = "rejected"; rec.validation = [["執行", str(e)]]
        db.flush()
        return {"status": "rejected", "errors": [("執行", str(e))], "attempt": rec.attempt}
    prior = db.scalars(select(M.Decision).where(M.Decision.table_id == t.id, M.Decision.kind == "resolve",
                                                M.Decision.committed.is_(True),
                                                M.Decision.gh >= t.tick * t.tick_hours, M.Decision.gh < gh)
                       .order_by(M.Decision.gh)).all()
    mf = hour_orders.to_manifest(snap.state, decision, tick=t.tick, gh=gh, prior_decisions=[d.decision for d in prior])
    findings = _audit.run(s, before, mf)
    errors = [(k, m) for k, items in findings.items() for sev, m in items if sev == "錯誤"]
    if errors:
        rec.status = "rejected"; rec.validation = [["稽核:" + k, m] for k, m in errors]
        events.emit(db, t.id, "稽核擋下", gh=gh, attempt=rec.attempt, errors=len(errors))
        db.flush()
        return {"status": "rejected", "errors": [("稽核", f"{k}：{m}") for k, m in errors], "attempt": rec.attempt}

    # 徵候：洩漏的句子直接刪掉、留事件（徵候只是說明，不值得為它退回整份決定）；裁示照存
    from acies.engine import leakcheck
    redacted = []
    for sd in SIDES:
        for text in decision.get("signals", {}).get(sd, []):
            leaks = leakcheck.check_leak(s, text, sd, skip_history=False)
            if leaks:
                redacted.append((sd, text[:80], leaks)); continue
            db.add(M.Signal(table_id=t.id, gh=gh, side=sd, text=text))
    if redacted:
        events.emit(db, t.id, "徵候刪句", gh=gh, items=[{"side": a, "text": b, "leaks": c} for a, b, c in redacted])
    _store_rulings(db, t, decision, gh)
    _apply_ledger(db, t, decision, gh)

    # 落定
    h = state_io.state_hash(s)
    rec.execution = {**ex.to_dict(), "line": line, "audit": {k: v for k, v in findings.items() if v},
                     "warnings": [list(w) for w in warnings], "redacted_signals": [[a, b, c] for a, b, c in redacted]}
    rec.end_state_hash = h; rec.committed = True; rec.status = "committed"
    db.add(M.Snapshot(table_id=t.id, gh=gh + 1, state=s, state_hash=h))
    t.global_hour = gh + 1
    r.status = M.RoundStatus.resolving
    r.lease_worker = None; r.lease_until = None      # 每小時落定即釋放；下一小時任何工作者可取
    events.emit(db, t.id, "小時落定", gh=gh, attempt=rec.attempt, hash=h)

    # 斬首即勝
    loser = command.decapitation(s)
    if loser:
        s["victory_state"] = {"decapitated": ar.ENEMY[loser]}
        return _finish(db, t, r, s, gh + 1)
    # tick 結束
    if (gh + 1) % t.tick_hours == 0:
        r.status = M.RoundStatus.committed
        r.lease_worker = None; r.lease_until = None
        _expire_contingencies(db, t, gh + 1)
        events.emit(db, t.id, "回合落定", gh=gh + 1, tick=t.tick)
        if t.tick + 1 > t.max_ticks:
            return _finish(db, t, r, s, gh + 1)
        t.tick += 1
        tables.open_round(db, t, t.tick)
        briefs.publish(db, t, s, t.tick)
    db.flush()
    return {"status": "committed", "kind": "resolve", "gh": gh, "end_state_hash": h}


def _expire_contingencies(db, t, gh):
    db.execute(update(M.Clause).where(M.Clause.table_id == t.id, M.Clause.kind == "contingency",
                                      M.Clause.status.in_(["pending", "active"]))
               .values(status="expired"))


def _finish(db, t, r, s, gh):
    winner, why = ar.verdict(s)
    t.status = M.TableStatus.finished
    t.settings = {**t.settings, "verdict": {"winner": winner, "why": why}}
    r.lease_worker = None; r.lease_until = None
    events.emit(db, t.id, "終局", gh=gh, winner=winner, why=why)
    db.flush()
    return {"status": "committed", "finished": True, "winner": winner, "why": why}


def adjudicate(db, table_id, pending_id, answer):
    """人工裁定回覆；桌恢復進行，該小時以新 attempt 重跑。"""
    t = db.get(M.Table, table_id)
    p = db.scalar(select(M.Pending).where(M.Pending.table_id == t.id, M.Pending.pending_id == pending_id))
    if p is None or p.status != "open":
        raise WorkError("無此待裁定或已回覆")
    p.answer = answer; p.status = "answered"; p.answered_at = _now()
    if answer.get("kind") == "public_ruling" and answer.get("public_text"):
        n = db.scalar(select(M.Ruling.seq).where(M.Ruling.table_id == t.id).order_by(M.Ruling.seq.desc()).limit(1)) or 0
        cond, _, eff = answer["public_text"].partition("→")
        db.add(M.Ruling(table_id=t.id, ruling_id=f"A-{pending_id}", seq=n + 1, gh=t.global_hour,
                        body={"condition": cond.strip(), "effect": eff.strip(), "basis": "人工裁定",
                              "beneficiary": answer.get("beneficiary", "neutral")},
                        text_hash=hashlib.sha256(answer["public_text"].encode()).hexdigest(), source="adjudication"))
    if t.status == M.TableStatus.awaiting_adjudication:
        t.status = M.TableStatus.running
    events.emit(db, t.id, "人工裁定", gh=t.global_hour, pending_id=pending_id, answer_kind=answer.get("kind"))
    db.flush()
