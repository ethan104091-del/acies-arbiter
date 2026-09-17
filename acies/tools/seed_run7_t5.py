"""建一桌從 Run 7 T5 起始快照（gh30）開始的桌，並送入雙方 T5 定稿命令——裁判工作者的實測基準。

用法：.venv/bin/python -m acies.tools.seed_run7_t5 [桌名]
印出桌號與四個席位權杖；之後跑 python -m acies.referee.worker --once 逐小時解算。
"""
import json
import sys

import acies
from acies.db.session import session
from acies.engine import state_io
from acies.service import rounds, tables

RUN = acies.ROOT / "runs" / "run7_openfield"


def main(name="Run7-T5 實測"):
    s = state_io.loads((RUN / "snap_T5start.json").read_text())
    with session() as db:
        t, tok = tables.create_table(db, name, "open_field", state=s)
        for sd, fn in (("allies", "命令_T5_藍軍_定稿.md"), ("axis", "命令_T5_紅軍_定稿.md")):
            rounds.submit_order(db, t, sd, t.tick, (RUN / fn).read_text(), f"seed-{sd}")
        db.commit()
        print(json.dumps({"table_id": t.id, "tick": t.tick, "global_hour": t.global_hour, "tokens": tok},
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
