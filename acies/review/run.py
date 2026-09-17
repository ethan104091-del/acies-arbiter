"""跑一桌的判例審查：機械檢查 → 兩官 → 辯論 → 落地 → 紀錄。

用法：.venv/bin/python -m acies.review.run <桌號或前綴> [--dry]
終局時裁判工作者會自動呼叫 run_table。
"""
import json
import sys

from sqlalchemy import select

import acies  # noqa: F401
import arbiter as ar
from acies.db import models as M
from acies.db.session import session
from acies.engine import sandbox

from . import checks, debate, dossier, reviewer, writer


def collect(db, t):
    """每條裁示：原文、被引用的小時（動作、事件、量級）。"""
    rulings = db.scalars(select(M.Ruling).where(M.Ruling.table_id == t.id).order_by(M.Ruling.seq)).all()
    decs = db.scalars(select(M.Decision).where(M.Decision.table_id == t.id, M.Decision.committed.is_(True))
                      .order_by(M.Decision.gh)).all()
    snaps = {s.gh: s.state for s in db.scalars(select(M.Snapshot).where(M.Snapshot.table_id == t.id)).all()}
    out = []
    for r in rulings:
        apps = []
        for d in decs:
            acts = [a for a in d.decision.get("actions", []) if a.get("tier") == 2 and a.get("ruling_id") == r.ruling_id]
            if not acts:
                continue
            state = snaps.get(d.gh)
            m = sandbox.measure(state, {"actions": acts}) if state else None
            apps.append({"gh": d.gh, "actions": acts, "events": (d.execution or {}).get("events", [])[:20], "measurement": m})
        body = dict(r.body)
        body.update({"ruling_id": r.ruling_id, "gh": r.gh, "seq": r.seq, "tier2_used": bool(apps)})
        out.append((r, body, apps))
    final = snaps.get(max(snaps)) if snaps else None
    scores = {k: v["points"] for k, v in ar.score(final).items()} if final else {}
    return out, scores


def run_table(table_id, *, ask=None, dry=False, force=False, log=print):
    ask = ask or reviewer.ask
    rules_text = dossier.rules_text(); sections = dossier.rule_sections()
    entries = []
    with session() as db:
        t = db.scalar(select(M.Table).where(M.Table.id.like(table_id + "%")))
        if t is None:
            raise SystemExit(f"無此桌 {table_id}")
        items, scores = collect(db, t)
        log(f"桌 {t.id[:8]}：{len(items)} 條裁示，終局 {scores}")
        for r, body, apps in items:
            if not force and (r.body or {}).get("status") in ("precedent", "overturned", "rewritten", "disputed"):
                log(f"裁示 {r.ruling_id} 已審過（{r.body['status']}），略過"); continue
            ck = checks.run_all(body, rules_text, sections, apps, scores)
            log(f"裁示 {r.ruling_id}：機械檢查 {len(ck['findings'])} 項發現，被引用 {len(apps)} 次")
            result = debate.run(body, ck, apps, ask, log=log)
            log(f"  結論：{result['outcome']}")
            entry = {"ruling_id": r.ruling_id, "outcome": result["outcome"], "checks": ck, "rounds": result["rounds"]}
            if not dry and result["outcome"] != "失敗":
                applied = writer.apply(t.id, body, result, ck)
                entry["changes"] = applied["changes"]
                status = {"定案": "precedent", "推翻": "overturned", "改寫": "rewritten", "爭議": "disputed"}[result["outcome"]]
                r.body = {**r.body, "status": status, "review": result["final"], "precedent_no": applied["section_no"]}
            entries.append(entry)
        if not dry:
            db.commit()
    p = writer.write_log(t.id, entries) if entries else None
    log(f"審查紀錄：{p}")
    return entries


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_table(args[0], dry="--dry" in sys.argv, force="--force" in sys.argv)
