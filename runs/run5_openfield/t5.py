#!/usr/bin/env python3
"""Run 5 Tick 5 解算（gh30-35，1944-08-26 12:00-17:00，全程白天）。

紅軍全線西進至 x=19，仍全部零工事。藍軍取消最後一格前推，就地釘在 x=7 重新挖工事。
BLU-SF 放棄東進斬首行程，改進駐 (12,6) 森林（裁示 59 訂正：特戰旅可入林）。
BLU-SF-rcn 西撤脫離砲兵射程。

紅軍砲擊條件（照命令字面）：只打 BLU-SF，且須 RED-3-rcn 持續觀測、RED-3 進入射程；
失去觀測則明確不得盲射（與裁示 58 一致）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar, hourstate as hs, command      # noqa: E402

s = ar.load()
assert s["global_hour"] == 30, f"必須從 gh30 起始，現在 gh={s['global_hour']}"

ORDERS = [
    ("axis", "L2", "RED-3", "向 (19,3) 戰備推進；RED-3-rcn 持續觀測 BLU-SF 且進入射程則集中壓制，失去觀測不盲射"),
    ("axis", "L1", "RED-3-rcn", "留 (17,3) 隱蔽監視 BLU-SF 與 BLU-SF-rcn"),
    ("axis", "L2", "RED-2-rcn", "向 (12,8) 前進偵察，發現敵主力即停止並隱蔽觀察"),
    ("axis", "L2", "RED-2", "向 (19,9) 戰備推進，保持與 RED-AD 相鄰協同"),
    ("axis", "L2", "RED-AD", "向 (19,10) 行軍縱隊推進"),
    ("axis", "L2", "RED-1", "向 (19,12) 戰備推進"),
    ("axis", "L2", "RED-SF", "向 (14,15) 隱蔽滲透偵察"),
    ("axis", "L1", "RED-2-1-r4", "留 (29,8) 續構築工事至有頂蓋級"),
    ("allies", "L1", "BLU-1", "取消前推，(7,8) 就地構築工事至有頂蓋，此後固守"),
    ("allies", "L1", "BLU-2", "取消前推，(7,9) 就地構築工事至有頂蓋，此後固守"),
    ("allies", "L1", "BLU-AD", "(7,9) 固守完全休整，作為反擊拳頭待命"),
    ("allies", "L1", "BLU-3", "(4,11) 固守完全休整；BLU-3-eng 續構築工事"),
    ("allies", "L1", "BLU-2-1-r4", "(4,10) 續構築工事至有頂蓋"),
    ("allies", "L1", "BLU-3-1-r7", "(4,10) 續構築工事至有頂蓋"),
    ("allies", "L1", "BLU-1-1-r1", "(5,9) 續構築工事至有頂蓋"),
    ("allies", "L1", "BLU-1-rcn", "留 (13,6) 靜止隱蔽觀測並構築工事至散兵壕以上"),
    ("allies", "L1", "BLU-3-rcn", "留 (16,11) 靜止隱蔽觀測並構築工事"),
    ("allies", "L1", "BLU-AD-rcn", "留 (10,13) 靜止隱蔽觀測並構築工事"),
    ("allies", "L1", "BLU-2-rcn", "留 (5,15) 靜止隱蔽觀測並構築工事"),
    ("allies", "L1", "BLU-SF", "取消東進，經 (14,3)(13,4)(12,5) 進駐 (12,6) 森林格並構築工事"),
    ("allies", "L1", "BLU-SF-rcn", "西撤至 (14,2) 就地構築工事並觀測北路"),
]
EFF = {}
for side, lvl, uid, txt in ORDERS:
    o = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                         extra_delay=command.delay_tier_adjust(s, side, s["units"][uid]["pos"]))
    EFF[uid] = o["effective_global_hour"]

MOVE = {"RED-3": [(19, 3)], "RED-2": [(19, 9)], "RED-AD": [(19, 10)], "RED-1": [(19, 12)],
        "RED-SF": [(14, 15)], "RED-2-rcn": [(12, 8)],
        "BLU-SF": [(14, 3), (13, 4), (12, 5), (12, 6)], "BLU-SF-rcn": [(14, 2)]}
DIG = ["BLU-1", "BLU-2", "BLU-2-1-r4", "BLU-3-1-r7", "BLU-1-1-r1", "BLU-3-eng",
       "BLU-1-rcn", "BLU-3-rcn", "BLU-AD-rcn", "BLU-2-rcn", "RED-2-1-r4"]
ARRIVE_DIG = {"BLU-SF": (12, 6), "BLU-SF-rcn": (14, 2)}
halted = set()
# 缺陷 18：原本用「航路上第一個還沒到達的點」當目標，會使部隊在兩個航路點之間
# 來回振盪（走到 B 後發現 A 未到達 → 走回 A）。改為逐編隊記住航路索引，只前進。
WP = {uid: 0 for uid in MOVE}


def next_wp(uid, u):
    route = MOVE[uid]
    while WP[uid] < len(route) and list(u["pos"]) == list(route[WP[uid]]):
        WP[uid] += 1
    return route[WP[uid]] if WP[uid] < len(route) else None


def spotted(side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def resolve(s, gh):
    ev = []
    for uid, route in MOVE.items():
        u = s["units"].get(uid)
        if not u or gh < EFF.get(uid, 0) or uid in halted:
            continue
        if uid == "RED-2-rcn":
            near = [e for e in spotted("axis")
                    if ar.dist(s["units"][e]["pos"], u["pos"]) <= 3
                    # 「敵主力」＝師級編隊。紅軍 T4 意圖自己區分過「敵主力」與
                    # 「單一偵察營」，且其命令並列「敵主力或敵裝甲師」，
                    # 故旅級（特戰旅 3,200 人）不算主力。[判例]
                    and s["units"][e].get("personnel", 0) >= 10000]
            if near:
                halted.add(uid)
                ev.append((uid, f"{uid} 依命令停止前推、原地隱蔽觀察（偵獲主力 {', '.join(near)}）"))
                continue
        tgt = next_wp(uid, u)
        if tgt is None:
            continue
        _, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, msg))

    for uid in DIG + [k for k, p in ARRIVE_DIG.items()
                      if s["units"].get(k) and list(s["units"][k]["pos"]) == list(p)]:
        u = s["units"].get(uid)
        if not u or u.get("dig_hours", 0) >= 8.0 or u["flags"].get("moved"):
            continue
        if gh < EFF.get(uid, 0):
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))

    # 紅軍：照命令字面，只打 BLU-SF，且須觀測＋射程
    obs_sf = "BLU-SF" in spotted("axis")
    if obs_sf:
        sh = [x for x in ("RED-1", "RED-2", "RED-3") if s["units"][x]["equip"]["guns"]
              and any(ar.dist(s["units"][x]["pos"], s["units"]["BLU-SF"]["pos"])
                      <= ar.GUN_SPEC[g][2] for g in ar.GUN_MIX[s["units"][x]["type"]])]
        if sh:
            cas, tk, gk, msg = ar.bombard(s, sh, "BLU-SF")
            if cas or tk or gk:
                t = s["units"]["BLU-SF"]
                pct = 100.0 * cas / max(t.get("personnel", 1), 1)
                org = ar.org_impact(s, "BLU-SF", pct)
                ar.hurt(s, "BLU-SF", personnel=cas, tanks=tk, guns=gk, org=org,
                        fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
                ev.append(("axis", f"我方師屬砲兵對 BLU-SF 集中射擊：{msg}（組織度 -{org}）"))
                ev.append(("BLU-SF", f"BLU-SF 遭敵砲擊：傷亡 {cas} 人、組織度 -{org}"))
    # 藍軍砲兵：射程內有已偵獲敵編隊才開火（本 tick 逐小時檢查）
    blu = [x for x in ("BLU-1", "BLU-2", "BLU-3", "BLU-AD") if s["units"][x]["equip"]["guns"]]
    cands = []
    for e in spotted("allies"):
        u = s["units"][e]
        if ar.status_of(u) not in ar.COMBAT_STATUSES:
            continue
        sh = [x for x in blu if any(ar.dist(s["units"][x]["pos"], u["pos"])
                                    <= ar.GUN_SPEC[g][2] for g in ar.GUN_MIX[s["units"][x]["type"]])]
        if sh:
            pri = 0 if e == "RED-SF" and u.get("fortification", 0) == 0 else \
                  1 if u["type"] == "recon" or u.get("is_detachment") else 2
            cands.append((pri, e, sh))
    if cands:
        cands.sort()
        _, tgt, sh = cands[0]
        cas, tk, gk, msg = ar.bombard(s, sh, tgt)
        if cas or tk or gk:
            t = s["units"][tgt]
            pct = 100.0 * cas / max(t.get("personnel", 1), 1)
            org = ar.org_impact(s, tgt, pct)
            ar.hurt(s, tgt, personnel=cas, tanks=tk, guns=gk, org=org,
                    fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
            ev.append(("allies", f"我方師屬砲兵對 {tgt} 集中射擊：{msg}（組織度 -{org}）"))
            ev.append((tgt, f"{tgt} 遭敵砲擊：傷亡 {cas} 人、組織度 -{org}"))
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
for side in ("allies", "axis"):
    print(f"{side:7} 已偵獲：{spotted(side) or '（無）'}")
print()
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>6} {'工事':>6} {'暴露':>6} {'累損':>6} {'補給':9}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel',0):6} {u.get('fatigue',0):4} "
          f"{u.get('org',0):6} {u.get('fortification',0):6.2f} "
          f"{ar.exposure_factor(u, ar.terr(s,u['pos'])):6} {u['losses']['personnel']:6} "
          f"{str(u.get('supply_status')):9}")
