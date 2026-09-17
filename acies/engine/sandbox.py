"""沙盒：在快照的深拷貝上試跑二級動作，量測量級（守則第 5 條）。"""
import arbiter as ar

from . import state_io
from . import verbs as V


def weighted_power(s, side):
    """一方的加權戰力值：人員 ＋ 戰車、火砲依 SCORE_W 加權（與 score() 同尺度）。"""
    w = getattr(ar, "SCORE_W", {"personnel": 1, "tanks": 20, "guns": 10})
    tot = 0.0
    for u in s["units"].values():
        if u.get("side") != side:
            continue
        tot += u.get("personnel", 0) * w.get("personnel", 1)
        tot += u.get("equip", {}).get("tanks", 0) * w.get("tanks", 0)
        tot += u.get("equip", {}).get("guns", 0) * w.get("guns", 0)
    return tot


def measure(s, decision):
    """對 decision 的全部二級動作試跑一次，回傳 {side: {power_before, power_after, ratio, points_delta}}。"""
    t = state_io.clone(s)
    before = {sd: weighted_power(t, sd) for sd in ("allies", "axis")}
    sc0 = ar.score(t)
    for act in decision.get("actions", []):
        if act.get("tier", 1) != 2:
            continue
        for prim in act.get("applied", []):
            name, args = prim["primitive"], dict(prim.get("args", {}))
            if V.check_primitive_args(name, args):
                continue
            V.PRIMITIVES[name](t, **args)
    after = {sd: weighted_power(t, sd) for sd in ("allies", "axis")}
    sc1 = ar.score(t)
    out = {}
    for sd in ("allies", "axis"):
        out[sd] = {"power_before": before[sd], "power_after": after[sd],
                   "ratio": (before[sd] - after[sd]) / before[sd] if before[sd] else 0.0,
                   "points_delta": sc1[sd]["points"] - sc0[sd]["points"]}
    return out


def exceeds(measurement, *, power_ratio=0.01, points=50):
    """任一方戰力變動比例或分數變動超過門檻 → True（轉待裁定）。"""
    return any(abs(m["ratio"]) > power_ratio or abs(m["points_delta"]) > points
               for m in measurement.values())
