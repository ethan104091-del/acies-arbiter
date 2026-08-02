#!/usr/bin/env python3
"""Run 5 Tick 7 解算（gh42-47，1944-08-27 00:00-05:00，全程夜間）。

紅軍放棄前進，三個火力群（RED-1/RED-2/RED-AD）集中壓制 BLU-3-rcn；受損單位後撤。
藍軍全線靜止構築工事（目標：戰車掩壕使 216 輛戰車暴露 0.30 → 0.05），並停止對低價值目標射擊。
裁示 70：BLU-3-rcn 依「停止後撤、就地停止」留在實際位置 (15,11)。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar, hourstate as hs, command      # noqa: E402

s = ar.load()
assert s["global_hour"] == 42, f"必須從 gh42 起始，現在 gh={s['global_hour']}"

ORDERS = [
    ("axis", "L1", "RED-1", "留 (18,12) 戰鬥行進；BLU-3-rcn 可見且入射程則集中射擊，失接觸即停火"),
    ("axis", "L1", "RED-2", "留 (18,9) 戰鬥行進；同上"),
    ("axis", "L1", "RED-AD", "留 (17,10) 戰鬥行進；同上，不前出追擊"),
    ("axis", "L1", "RED-2-rcn", "自 (15,8) 向 (18,8) 撤回，不交戰"),
    ("axis", "L1", "RED-SF", "自 (12,15) 向 (14,17) 隱蔽撤離，不交戰不切補給"),
    ("axis", "L1", "RED-3", "在 (18,3) 完全休整；僅在 RED-3-rcn 觀測到 BLU-SF 且入射程才壓制"),
    ("axis", "L1", "RED-3-rcn", "留 (17,3) 隱蔽觀察北翼"),
    ("axis", "L1", "RED-2-2-r4", "留 (24,9) 固守前進指揮所"),
    ("allies", "L1", "BLU-1", "(9,8) 固守，全程構築工事至有頂蓋"),
    ("allies", "L1", "BLU-2", "(9,10) 固守，全程構築工事；除師級目標外不開火"),
    ("allies", "L1", "BLU-AD", "(9,9) 固守，全程構築工事含戰車掩壕；不出擊不前出"),
    ("allies", "L1", "BLU-3", "(4,11) 固守完全休整；BLU-3-eng 同"),
    ("allies", "L1", "BLU-2-1-r4", "(4,10) 固守完全休整"),
    ("allies", "L1", "BLU-3-1-r7", "(4,10) 固守完全休整"),
    ("allies", "L1", "BLU-1-1-r1", "(5,9) 固守完全休整"),
    ("allies", "L1", "BLU-3-rcn", "停止後撤、就地停止並構築工事（裁示 70：實際位置 (15,11)）"),
    ("allies", "L1", "BLU-1-rcn", "(13,6) 固守續構築工事"),
    ("allies", "L1", "BLU-AD-rcn", "(10,13) 固守續構築工事"),
    ("allies", "L1", "BLU-2-rcn", "(5,15) 固守續構築工事"),
    ("allies", "L1", "BLU-SF-rcn", "(11,4) 就地構築工事至散兵壕，觀測北路"),
    ("allies", "L1", "BLU-SF", "(12,6) 森林保持 CONCEALED，全程完全休整壓疲勞"),
]
EFF = {}
for side, lvl, uid, txt in ORDERS:
    o = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                         extra_delay=command.delay_tier_adjust(s, side, s["units"][uid]["pos"]))
    EFF[uid] = o["effective_global_hour"]

MOVE = {"RED-2-rcn": [(18, 8)], "RED-SF": [(14, 17)]}
WP = {u: 0 for u in MOVE}
DIG = ["BLU-1", "BLU-2", "BLU-AD", "BLU-3-rcn", "BLU-1-rcn", "BLU-AD-rcn",
       "BLU-2-rcn", "BLU-SF-rcn"]
RED_FIRE = ["RED-1", "RED-2", "RED-AD"]
BLU_FIRE = ["BLU-1", "BLU-2", "BLU-3", "BLU-AD"]


def sp(side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def reach(sh, tgt):
    d = ar.dist(s["units"][sh]["pos"], s["units"][tgt]["pos"])
    return any(d <= ar.GUN_SPEC[g][2] for g in ar.GUN_MIX.get(s["units"][sh]["type"], {}))


def shoot(side, shooters, tgt, ev, label):
    sh = [x for x in shooters if s["units"][x]["equip"]["guns"] and reach(x, tgt)]
    if not sh:
        return False
    cas, tk, gk, msg = ar.bombard(s, sh, tgt)
    if not (cas or tk or gk):
        return False
    t = s["units"][tgt]
    pct = 100.0 * cas / max(t.get("personnel", 1), 1)
    org = ar.org_impact(s, tgt, pct)
    ar.hurt(s, tgt, personnel=cas, tanks=tk, guns=gk, org=org,
            fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
    ev.append((side, f"我方{label}對 {tgt} 集中射擊：{msg}（組織度 -{org}）"))
    ev.append((tgt, f"{tgt} 遭敵砲擊：傷亡 {cas} 人"
                    + (f"、火砲 -{gk}" if gk else "") + f"、組織度 -{org}"))
    return True


def resolve(s, gh):
    ev = []
    for uid in list(MOVE):
        u = s["units"].get(uid)
        if not u or gh < EFF.get(uid, 0):
            continue
        r = MOVE[uid]
        while WP[uid] < len(r) and list(u["pos"]) == list(r[WP[uid]]):
            WP[uid] += 1
        if WP[uid] >= len(r):
            continue
        _, msg = ar.advance(s, uid, list(r[WP[uid]]))
        ev.append((uid, msg))

    for uid in DIG:
        u = s["units"].get(uid)
        if not u or u.get("dig_hours", 0) >= 8.0 or u["flags"].get("moved"):
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，"
                            f"人員暴露 {r[2]}）"))

    # 紅軍：三個火力群集中 BLU-3-rcn（可見且入射程）
    if "BLU-3-rcn" in sp("axis"):
        shoot("axis", RED_FIRE, "BLU-3-rcn", ev, "三個火力群")
    # 紅軍 RED-3：僅在觀測到 BLU-SF 且入射程
    if "BLU-SF" in sp("axis"):
        shoot("axis", ["RED-3"], "BLU-SF", ev, "RED-3 師屬砲兵")
    # 藍軍：應變 3 終局優先序（RED-AD 未構工事最高、不打 600 人以下小單位）
    cands = []
    for e in sp("allies"):
        u = s["units"][e]
        if ar.status_of(u) not in ar.COMBAT_STATUSES:
            continue
        if not any(s["units"][x]["equip"]["guns"] and reach(x, e) for x in BLU_FIRE):
            continue
        p = u.get("personnel", 0)
        if p < 600:
            continue                       # 應變 3 ⑤：不打小單位
        pri = 0 if e == "RED-AD" and u.get("fortification", 0) == 0 else \
              1 if p >= 10000 else 2
        cands.append((pri, e))
    if cands:
        cands.sort()
        shoot("allies", BLU_FIRE, cands[0][1], ev, "師屬砲兵")
    return ev


log = []
lines = ar.run_tick(s, resolve, hours=6, log=log)
ar.save(s)
print("=" * 78)
for line in lines:
    print(line)
print("=" * 78)
sc = ar.score(s)
print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}｜斬首：{command.decapitation(s)}")
print()
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>6} {'工事':>6} {'人暴露':>6} {'車暴露':>6} {'累損':>6} {'狀態'}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    f = u.get("fortification", 0)
    te = 1.0 if u["flags"].get("moved") else (0.05 if f >= 0.35 else 0.15 if f > 0 else 0.30)
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel',0):6} {u.get('fatigue',0):4} "
          f"{u.get('org',0):6} {f:6.2f} {ar.exposure_factor(u, ar.terr(s,u['pos'])):6} "
          f"{te:6} {u['losses']['personnel']:6} {ar.status_of(u)}")
