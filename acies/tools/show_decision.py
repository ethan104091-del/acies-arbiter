"""印出某桌最近的決定紀錄（含驗證錯誤、執行結果、用量），供實測對照。

用法：.venv/bin/python -m acies.tools.show_decision [桌號前綴] [--all]
"""
import json
import sys

from sqlalchemy import select

import acies  # noqa: F401
from acies.db import models as M
from acies.db.session import session


def main(prefix=None, show_all=False):
    with session() as db:
        q = select(M.Decision).order_by(M.Decision.created_at.desc())
        if prefix:
            q = q.where(M.Decision.table_id.like(prefix + "%"))
        rows = db.scalars(q).all()
        rows = rows if show_all else rows[:1]
        for r in reversed(rows):
            print(f"═══ 桌 {r.table_id[:8]} gh{r.gh} {r.kind} attempt {r.attempt} → {r.status}")
            d = r.decision
            print(f"動作 {len(d.get('actions', []))}　裁示 {len(d.get('rulings', []))}　應變檢查 {len(d.get('contingency_checks', []))}"
                  f"　條款更新 {len(d.get('clause_updates', []))}　待裁定 {len(d.get('pending', []))}　答覆 {len(d.get('answers', []))}")
            for a in sorted(d.get("actions", []), key=lambda a: a["seq"]):
                p = a.get("provenance", {})
                print(f"  {a['seq']:>2} {'二級 ' + str(a.get('ruling_id')) if a.get('tier') == 2 else a.get('verb'):<16} "
                      f"{json.dumps(a.get('args', {}), ensure_ascii=False)[:90]}  ← {p.get('clause_id')}")
            for c in d.get("clause_updates", []):
                print(f"  條款 {c['clause_id']} [{c.get('kind')}/{c.get('status')}] {(c.get('text') or '')[:70]}"
                      + (f"\n      述詞：{c['predicate'][:100]}" if c.get("predicate") else ""))
            for x in d.get("contingency_checks", []):
                print(f"  應變 {x['cont_id']}：{'觸發' if x.get('fired') else '未觸發'}　{x.get('evidence', '')[:80]}")
            for x in d.get("rulings", []):
                print(f"  裁示 {x['ruling_id']}：{x['condition']} → {x['effect']}　（{x.get('beneficiary')}）")
            for x in d.get("pending", []):
                print(f"  待裁定 {x['pending_id']}（{x['kind']}{'，重大' if x.get('material') else ''}）：{x.get('question', '')[:100]}")
            for x in d.get("answers", []):
                print(f"  答覆 {x['question_id']}（{x['kind']}）：{(x.get('public_text') or x.get('private_text', ''))[:120]}")
            for sd, lst in (d.get("signals") or {}).items():
                for t in lst:
                    print(f"  徵候→{sd}：{t[:100]}")
            if r.validation:
                print("  驗證錯誤：")
                for e in r.validation:
                    print(f"    - {e}")
            if r.execution:
                for e in r.execution.get("events", [])[:30]:
                    print(f"  事件 [{e[0]}] {e[1][:100]}")
            if r.dossier_id:
                ds = db.get(M.Dossier, r.dossier_id)
                if ds:
                    u = ds.usage or {}
                    print(f"  卷宗 {ds.id}　用量 {u}　列價 {ds.response.get('list_price_usd') if ds.response else None}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else None, "--all" in sys.argv)
