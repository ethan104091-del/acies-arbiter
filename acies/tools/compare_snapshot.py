"""比對某桌某小時的快照與一份參考快照（例：人工腳本產生的 runs/run7_openfield/snap_T6start.json）。

用法：.venv/bin/python -m acies.tools.compare_snapshot <桌號前綴> <gh> <參考快照檔>
"""
import json
import sys

from sqlalchemy import select

import acies  # noqa: F401
import arbiter as ar
from acies.db import models as M
from acies.db.session import session
from acies.engine import state_io

FIELDS = ("pos", "personnel", "org", "fatigue", "fortification", "camo_hours", "visibility_state", "status")


def main(prefix, gh, ref_path):
    ref = state_io.loads(open(ref_path).read())
    with session() as db:
        t = db.scalar(select(M.Table).where(M.Table.id.like(prefix + "%")))
        snap = db.scalar(select(M.Snapshot).where(M.Snapshot.table_id == t.id, M.Snapshot.gh == int(gh)))
        if snap is None:
            print(f"桌 {prefix} 無 gh{gh} 快照"); return
        s = snap.state
    sa, sr = ar.score(s), ar.score(ref)
    print(f"計分  本桌 藍 {sa['allies']['points']} : 紅 {sa['axis']['points']}　　參考 藍 {sr['allies']['points']} : 紅 {sr['axis']['points']}")
    print(f"{'編隊':14} {'欄位':14} {'本桌':>22} {'參考':>22}")
    same = 0
    for uid in sorted(set(s["units"]) | set(ref["units"])):
        a, b = s["units"].get(uid), ref["units"].get(uid)
        if a is None or b is None:
            print(f"{uid:14} {'（只在一邊）':14} {str(a is not None):>22} {str(b is not None):>22}"); continue
        diffs = []
        for f in FIELDS:
            va, vb = a.get(f), b.get(f)
            if isinstance(va, float) or isinstance(vb, float):
                if abs(float(va or 0) - float(vb or 0)) > 0.01: diffs.append((f, va, vb))
            elif va != vb:
                diffs.append((f, va, vb))
        for g in sorted(set(a.get("ammo") or {}) | set(b.get("ammo") or {})):
            va, vb = (a.get("ammo") or {}).get(g, 0), (b.get("ammo") or {}).get(g, 0)
            if abs(va - vb) > 0.5: diffs.append((f"ammo.{g}", round(va), round(vb)))
        if not diffs:
            same += 1
        for f, va, vb in diffs:
            print(f"{uid:14} {f:14} {str(va):>22} {str(vb):>22}")
    print(f"完全相同的編隊：{same}/{len(s['units'])}")
    print("偵獲  本桌 藍→", sorted(s['fog_of_war'].get('allies_spotted', [])), " 紅→", sorted(s['fog_of_war'].get('axis_spotted', [])))
    print("      參考 藍→", sorted(ref['fog_of_war'].get('allies_spotted', [])), " 紅→", sorted(ref['fog_of_war'].get('axis_spotted', [])))


if __name__ == "__main__":
    main(*sys.argv[1:4])
