#!/usr/bin/env python3
"""Run 5 Tick 6 解算（gh36-41，1944-08-26 18:00-23:00）。
gh36=18:00 依裁示 52 算白天，gh37-41 夜間。

紅軍夜行壓縮距離：三師＋裝甲師 x=19 → x=15-16，特戰旅深入 (10,15)，被砲擊的偵察隊撤回 (16,8)。
藍軍東移兩格到 x=9 以把砲兵射程從 x≤12 推到 x≤14（棄散兵壕、抵達後重挖）。
BLU-SF 續行進駐 (12,6) 森林，並有「敵營級 2 格內出擊殲滅並立即返回」條款（裁示 66）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar, hourstate as hs, command      # noqa: E402

s = ar.load()
assert s["global_hour"] == 36, f"必須從 gh36 起始，現在 gh={s['global_hour']}"

ORDERS = [
    ("axis", "L1", "RED-2-rcn", "自 (12,8) 向 (16,8) 撤回，隱蔽行軍、不交戰不停留"),
    ("axis", "L2", "RED-3", "向 (15,3) 戰備推進；觀測到 BLU-SF 且入射程則壓制；夜間不地面突擊"),
    ("axis", "L1", "RED-3-rcn", "留 (17,3) 隱蔽監視 BLU-SF；靠近 2 格內則退至 (18,3) 維持觀測"),
    ("axis", "L2", "RED-2", "向 (16,9) 戰備推進，保持與 RED-AD 相鄰；夜間不主動攻擊"),
    ("axis", "L2", "RED-AD", "向 (16,10) 行軍縱隊推進；夜間不主動攻擊"),
    ("axis", "L2", "RED-1", "向 (16,12) 戰備推進；夜間不主動攻擊"),
    ("axis", "L2", "RED-SF", "向 (10,15) 隱蔽滲透偵察"),
    ("axis", "L1", "RED-2-2-r4", "留 (24,9) 固守前進指揮所"),
    ("allies", "L1", "BLU-1", "由 (7,8) 東移至 (9,8)，抵達後構築工事至有頂蓋，此後固守"),
    ("allies", "L1", "BLU-2", "由 (7,9) 東移至 (9,10)，抵達後構築工事至有頂蓋，此後固守"),
    ("allies", "L1", "BLU-AD", "由 (7,9) 東移至 (9,9)，抵達後構築工事（含戰車掩壕）至有頂蓋"),
    ("allies", "L1", "BLU-3", "(4,11) 固守不動完全休整；BLU-3-eng 同"),
    ("allies", "L1", "BLU-2-1-r4", "(4,10) 固守"),
    ("allies", "L1", "BLU-3-1-r7", "(4,10) 續構築工事至有頂蓋"),
    ("allies", "L1", "BLU-1-1-r1", "(5,9) 續構築工事至有頂蓋"),
    ("allies", "L1", "BLU-1-rcn", "留 (13,6) 靜止隱蔽觀測、續構築工事"),
    ("allies", "L1", "BLU-3-rcn", "留 (16,11) 靜止隱蔽觀測、續構築工事"),
    ("allies", "L1", "BLU-AD-rcn", "留 (10,13) 靜止隱蔽觀測、續構築工事；旅級進 2 格內則西撤 3 格"),
    ("allies", "L1", "BLU-2-rcn", "留 (5,15) 靜止隱蔽觀測、續構築工事"),
    ("allies", "L1", "BLU-SF", "續行進駐 (12,6) 森林並構築工事；敵營級入 2 格開闊地則出擊殲滅並立即返回"),
    ("allies", "L1", "BLU-SF-rcn", "西南移至 (11,4)，構築工事並觀測北路"),
]
EFF = {}
for side, lvl, uid, txt in ORDERS:
    o = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                         extra_delay=command.delay_tier_adjust(s, side, s["units"][uid]["pos"]))
    EFF[uid] = o["effective_global_hour"]

MOVE = {"RED-2-rcn": [(16, 8)], "RED-3": [(15, 3)], "RED-2": [(16, 9)],
        "RED-AD": [(16, 10)], "RED-1": [(16, 12)], "RED-SF": [(10, 15)],
        "BLU-1": [(9, 8)], "BLU-2": [(9, 10)], "BLU-AD": [(9, 9)],
        "BLU-SF-rcn": [(11, 4)]}
WP = {u: 0 for u in MOVE}
SF_HOME = (12, 6)
DIG = ["BLU-3-1-r7", "BLU-1-1-r1", "BLU-1-rcn", "BLU-3-rcn", "BLU-AD-rcn", "BLU-2-rcn",
       "BLU-3-eng"]
ARRIVE = {"BLU-1": (9, 8), "BLU-2": (9, 10), "BLU-AD": (9, 9), "BLU-SF-rcn": (11, 4)}
rcn_pulled = set()


def sp(side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def next_wp(uid, u):
    r = MOVE[uid]
    while WP[uid] < len(r) and list(u["pos"]) == list(r[WP[uid]]):
        WP[uid] += 1
    return r[WP[uid]] if WP[uid] < len(r) else None


def guns_reach(sh, tgt):
    d = ar.dist(s["units"][sh]["pos"], s["units"][tgt]["pos"])
    return any(d <= ar.GUN_SPEC[g][2] for g in ar.GUN_MIX.get(s["units"][sh]["type"], {}))


def barrage(side, shooters, order, ev, label):
    """order：目標優先序判定函式，回傳排序鍵；None 表示不打。"""
    cands = []
    for e in sp(side):
        u = s["units"][e]
        if ar.status_of(u) not in ar.COMBAT_STATUSES:
            continue
        sh = [x for x in shooters if s["units"][x]["equip"]["guns"] and guns_reach(x, e)]
        if not sh:
            continue
        k = order(u, e)
        if k is None:
            continue
        cands.append((k, e, sh))
    if not cands:
        return
    cands.sort(key=lambda c: c[0])
    _, tgt, sh = cands[0]
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
                    + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else "")
                    + f"、組織度 -{org}"))


def resolve(s, gh):
    ev = []
    # 藍軍偵察哨：敵師級或旅級進 2 格內 → 西撤 3 格（BLU-AD-rcn 對 RED-SF）
    for uid in ("BLU-AD-rcn", "BLU-1-rcn", "BLU-3-rcn", "BLU-2-rcn"):
        u = s["units"].get(uid)
        if not u or uid in rcn_pulled or gh < EFF.get(uid, 0):
            continue
        big = [e for e in sp("allies")
               if s["units"][e].get("personnel", 0) >= 2000
               and ar.dist(s["units"][e]["pos"], u["pos"]) <= 2]
        if big:
            rcn_pulled.add(uid)
            dest = [max(0, u["pos"][0] - 3), u["pos"][1]]
            MOVE[uid] = [tuple(dest)]
            WP[uid] = 0
            EFF[uid] = gh
            ev.append((uid, f"{uid} 依命令西撤 3 格（{', '.join(big)} 進入 2 格內）→ 朝 {tuple(dest)}"))

    for uid in list(MOVE):
        u = s["units"].get(uid)
        if not u or gh < EFF.get(uid, 0):
            continue
        tgt = next_wp(uid, u)
        if tgt is None:
            continue
        _, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, msg))

    # BLU-SF：續行進駐 (12,6)；到位後依裁示 66 執行「出擊殲滅並立即返回」
    sf = s["units"]["BLU-SF"]
    if gh >= EFF["BLU-SF"] or True:
        if list(sf["pos"]) != list(SF_HOME):
            near = None
        else:
            near = next((e for e in sp("allies")
                         if s["units"][e].get("personnel", 0) <= 1000
                         and ar.terr(s, s["units"][e]["pos"]) != "F"
                         and ar.dist(s["units"][e]["pos"], sf["pos"]) <= 2), None)
        if near:
            _, msg = ar.advance(s, "BLU-SF", list(s["units"][near]["pos"]))
            ev.append(("BLU-SF", f"BLU-SF 依命令出擊 {near}（2 格內開闊地之敵營級）：{msg}"))
        elif list(sf["pos"]) != list(SF_HOME):
            _, msg = ar.advance(s, "BLU-SF", list(SF_HOME))
            ev.append(("BLU-SF", msg))
        else:
            r = ar.dig(s, "BLU-SF")
            if r:
                ev.append(("BLU-SF", f"BLU-SF 構築工事 → {r[0]}（{sf['dig_hours']:.2f}hr，暴露 {r[2]}）"))

    for uid in DIG + [k for k, p in ARRIVE.items()
                      if s["units"].get(k) and list(s["units"][k]["pos"]) == list(p)]:
        u = s["units"].get(uid)
        if not u or u.get("dig_hours", 0) >= 8.0 or u["flags"].get("moved"):
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))

    # 紅軍：只打 BLU-SF（照命令字面）
    barrage("axis", ["RED-1", "RED-2", "RED-3"],
            lambda u, e: 0 if e == "BLU-SF" else None, ev, "師屬砲兵")
    # 藍軍：裁示 61 之後改寫的優先序 —— 師級 > 旅級 > 營級／偵察
    def blu_pri(u, e):
        p = u.get("personnel", 0)
        if e == "RED-SF" and u.get("fortification", 0) == 0:
            return 0
        if p >= 10000:
            return 1
        if p >= 2000:
            return 2
        return 3
    barrage("allies", ["BLU-1", "BLU-2", "BLU-3", "BLU-AD"], blu_pri, ev, "師屬砲兵")
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
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>6} {'工事':>6} {'暴露':>6} {'累損':>6}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel',0):6} {u.get('fatigue',0):4} "
          f"{u.get('org',0):6} {u.get('fortification',0):6.2f} "
          f"{ar.exposure_factor(u, ar.terr(s,u['pos'])):6} {u['losses']['personnel']:6}")
