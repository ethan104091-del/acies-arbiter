#!/usr/bin/env python3
"""Run 5 Tick 8 解算（gh48-53，1944-08-27 06:00-11:00，白天）★終局★

紅軍：三個火力群持續壓制 BLU-3-rcn，其餘固守休整，不前進。
藍軍：全軍留在工事內、把砲口對準射程邊界；BLU-3-rcn 撤出敵砲兵射程止血。

★ 節奏差的最後一次體現：BLU-3-rcn 在藍軍前進指揮所 6 格半徑之外（距 11 格），
  故其撤退令為 +1 級延遲、gh50 才生效；gh48-49 仍依 T7 既有命令留在原地挨打。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar, hourstate as hs, command      # noqa: E402

s = ar.load()
assert s["global_hour"] == 48, f"必須從 gh48 起始，現在 gh={s['global_hour']}"

ORDERS = [
    ("axis", "L1", "RED-1", "留 (18,12) 戰鬥行進，全師砲兵持續集中射擊可見的 BLU-3-rcn"),
    ("axis", "L1", "RED-2", "留 (18,9) 戰鬥行進，全師砲兵持續集中射擊可見的 BLU-3-rcn"),
    ("axis", "L2", "RED-AD", "留 (17,10) 戰鬥行進，自走砲持續集中射擊可見的 BLU-3-rcn"),
    ("axis", "L1", "RED-2-rcn", "留 (17,8) 固守完全休整"),
    ("axis", "L1", "RED-SF", "留 (13,16) 固守完全休整"),
    ("axis", "L1", "RED-3", "留 (18,3) 固守完全休整"),
    ("axis", "L1", "RED-3-rcn", "留 (17,3) 固守監視西側接近路線"),
    ("axis", "L1", "RED-2-2-r4", "留 (24,9) 固守前進指揮所"),
    ("allies", "L1", "BLU-3-rcn", "立即向西撤出敵砲兵射程（目標 (9,11)），不接戰"),
    ("allies", "L1", "BLU-1", "(9,8) 固守工事，砲口對準射程邊界，不出擊"),
    ("allies", "L1", "BLU-2", "(9,10) 固守工事，砲口對準射程邊界，不出擊"),
    ("allies", "L1", "BLU-AD", "(9,9) 固守工事（含戰車掩壕），不出擊不前出"),
    ("allies", "L1", "BLU-3", "(4,11) 固守完全休整；BLU-3-eng 同"),
    ("allies", "L1", "BLU-2-1-r4", "(4,10) 固守"),
    ("allies", "L1", "BLU-3-1-r7", "(4,10) 固守"),
    ("allies", "L1", "BLU-1-1-r1", "(5,9) 固守"),
    ("allies", "L1", "BLU-1-rcn", "(13,6) 固守續構築工事"),
    ("allies", "L1", "BLU-AD-rcn", "(10,13) 固守續構築工事"),
    ("allies", "L1", "BLU-2-rcn", "(5,15) 固守續構築工事"),
    ("allies", "L1", "BLU-SF-rcn", "(11,4) 固守續構築工事"),
    ("allies", "L1", "BLU-SF", "(12,6) 森林保持隱蔽完全休整"),
]
EFF = {}
for side, lvl, uid, txt in ORDERS:
    o = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                         extra_delay=command.delay_tier_adjust(s, side, s["units"][uid]["pos"]))
    EFF[uid] = o["effective_global_hour"]

DIG = ["BLU-1", "BLU-2", "BLU-AD", "BLU-1-rcn", "BLU-AD-rcn", "BLU-2-rcn", "BLU-SF-rcn"]
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
        return
    cas, tk, gk, msg = ar.bombard(s, sh, tgt)
    if not (cas or tk or gk):
        return
    t = s["units"][tgt]
    pct = 100.0 * cas / max(t.get("personnel", 1), 1)
    org = ar.org_impact(s, tgt, pct)
    ar.hurt(s, tgt, personnel=cas, tanks=tk, guns=gk, org=org,
            fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
    ev.append((side, f"我方{label}對 {tgt} 集中射擊：{msg}（組織度 -{org}）"))
    ev.append((tgt, f"{tgt} 遭敵砲擊：傷亡 {cas} 人"
                    + (f"、火砲 -{gk}" if gk else "") + f"、組織度 -{org}"))


def resolve(s, gh):
    ev = []
    # BLU-3-rcn：gh50 起撤退（+1 級延遲，因在前進指揮所半徑外）
    u = s["units"]["BLU-3-rcn"]
    if gh >= EFF["BLU-3-rcn"] and list(u["pos"]) != [9, 11]:
        _, msg = ar.advance(s, "BLU-3-rcn", [9, 11])
        ev.append(("BLU-3-rcn", f"BLU-3-rcn 依命令西撤脫離敵砲兵射程：{msg}"))
    elif gh < EFF["BLU-3-rcn"]:
        r = ar.dig(s, "BLU-3-rcn")
        if r:
            ev.append(("BLU-3-rcn", f"BLU-3-rcn 依 T7 既有命令續構築工事"
                                    f"（撤退令 gh{EFF['BLU-3-rcn']} 才生效）"))

    for uid in DIG:
        x = s["units"].get(uid)
        if not x or x.get("dig_hours", 0) >= 8.0 or x["flags"].get("moved"):
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{x['dig_hours']:.2f}hr，人員暴露 {r[2]}）"))

    if "BLU-3-rcn" in sp("axis"):
        shoot("axis", RED_FIRE, "BLU-3-rcn", ev, "三個火力群")
    # 藍軍：優先 RED-AD（未構工事）＞師級＞旅級；不打 600 人以下
    cands = []
    for e in sp("allies"):
        x = s["units"][e]
        if ar.status_of(x) not in ar.COMBAT_STATUSES or x.get("personnel", 0) < 600:
            continue
        if not any(s["units"][y]["equip"]["guns"] and reach(y, e) for y in BLU_FIRE):
            continue
        p = x.get("personnel", 0)
        cands.append((0 if e == "RED-AD" and x.get("fortification", 0) == 0
                      else 1 if p >= 10000 else 2, e))
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
print(f"★終局計分★  藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}")
print(f"  藍軍殲敵：{sc['allies']['inflicted']}")
print(f"  紅軍殲敵：{sc['axis']['inflicted']}")
print(f"斬首：{command.decapitation(s)}")
print(f"事實紀錄：{len(s.get('record',[]))} 筆")
print()
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'org':>6} {'工事':>6} {'累損人':>6} {'累損砲':>6} {'狀態'}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel',0):6} {u.get('org',0):6} "
          f"{u.get('fortification',0):6.2f} {u['losses']['personnel']:6} "
          f"{u['losses']['guns']:6} {ar.status_of(u)}")
