#!/usr/bin/env python3
"""Run 5 Tick 4 解算（gh24-29，1944-08-26 06:00-11:00，全程白天）。

本局第一個雙方都有火力應變條款的 tick。
紅軍全線西進（x=24 → x=20-22），主力離開靜止狀態進入運動（暴露 0.70）。
藍軍 BLU-1/BLU-2 有限前推至 x=8，BLU-3 與 BLU-AD 保持已完成的有頂蓋工事不動。
BLU-SF 轉為反偵察掃蕩，目標先殲滅 (17,3) 的 RED-3-rcn。

延遲逐編隊計算（裁示 57）。雙方均有前進指揮所且軍長進駐：
半徑 6 格內 0 級、半徑外 +1。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 24, f"必須從 gh24 起始，現在 gh={s['global_hour']}"

ORDERS = [
    ("axis", "L2", "RED-3", "向 (20,3) 戰備推進；進入射程且 RED-3-rcn 保持觀測則壓制砲擊敵偵察營"),
    ("axis", "L1", "RED-3-rcn", "留 (17,3) 隱蔽監視，不主動交戰，不單獨追入森林"),
    ("axis", "L2", "RED-2-rcn", "向 (12,8) 前進偵察，發現敵軍即停止前推並隱蔽觀察"),
    ("axis", "L2", "RED-2", "向 (22,9) 戰備推進，保持與 RED-AD 相鄰協同"),
    ("axis", "L2", "RED-AD", "向 (21,10) 行軍縱隊推進，不入森林、不越過 RED-2 向西追擊"),
    ("axis", "L2", "RED-1", "向 (21,12) 戰備推進，保持與 RED-2 聯絡"),
    ("axis", "L2", "RED-SF", "向 (17,15) 隱蔽滲透偵察"),
    ("axis", "L1", "RED-2-1-r4", "留 (29,8) 續構築工事至有頂蓋級"),
    ("allies", "L1", "BLU-1", "經 (6,7)、(7,8) 推進至 (8,8)，抵達後構築工事至有頂蓋"),
    ("allies", "L1", "BLU-2", "經 (6,8)、(7,9) 推進至 (8,9)，抵達後構築工事至有頂蓋"),
    ("allies", "L1", "BLU-3", "(4,11) 原地不動完全休整；拉出工兵營 eng 就地構築工事"),
    ("allies", "L1", "BLU-AD", "(7,9) 原地不動完全休整、節油"),
    ("allies", "L1", "BLU-2-1-r4", "(4,10) 固守，工事已達有頂蓋，改完全休整"),
    ("allies", "L1", "BLU-3-1-r7", "續行進駐 (4,10)，抵達後構築工事至有頂蓋"),
    ("allies", "L1", "BLU-1-1-r1", "續行進駐 (5,9) 森林格，抵達後構築工事至有頂蓋"),
    ("allies", "L1", "BLU-1-rcn", "進駐 (13,6) 森林格，靜止隱蔽觀測"),
    ("allies", "L1", "BLU-AD-rcn", "進駐 (10,13) 森林格，靜止隱蔽觀測"),
    ("allies", "L1", "BLU-3-rcn", "進駐 (16,11) 森林格，靜止隱蔽觀測"),
    ("allies", "L1", "BLU-2-rcn", "(5,15) 原地不動續構築工事"),
    ("allies", "L1", "BLU-SF", "全速東進，朝 (17,3) 搜索接觸並殲滅該處敵偵察隊"),
    ("allies", "L1", "BLU-SF-rcn", "繞過 (17,3) 保持 2 格以上，沿 y=1-2 東進至 (22,2)"),
]
EFF = {}
for side, lvl, uid, txt in ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    o = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}", extra_delay=extra)
    EFF[uid] = o["effective_global_hour"]

MOVE = {  # uid -> 航路
    "RED-3": [(22, 3), (20, 3)], "RED-2": [(22, 9)], "RED-AD": [(21, 10)],
    "RED-1": [(21, 12)], "RED-SF": [(17, 15)], "RED-2-rcn": [(12, 8)],
    "BLU-1": [(6, 7), (7, 8), (8, 8)], "BLU-2": [(6, 8), (7, 9), (8, 9)],
    "BLU-3-1-r7": [(4, 10)], "BLU-1-1-r1": [(5, 9)],
    "BLU-1-rcn": [(13, 6)], "BLU-AD-rcn": [(10, 13)], "BLU-3-rcn": [(16, 11)],
    "BLU-SF": [(17, 3)], "BLU-SF-rcn": [(19, 1), (22, 2)],
}
DIG = ["BLU-2-rcn", "RED-2-1-r4"]
DIG_ON_ARRIVE = {"BLU-1": (8, 8), "BLU-2": (8, 9), "BLU-3-1-r7": (4, 10),
                 "BLU-1-1-r1": (5, 9)}
# 紅軍砲群（師屬砲兵，射程 105mm 4 / 155mm 5）
RED_GUNS = ["RED-1", "RED-2", "RED-3"]
BLU_GUNS = ["BLU-1", "BLU-2", "BLU-3", "BLU-AD"]
eng_out = [False]
halted = set()


def spotted(s, side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def in_range(s, shooter, target):
    d = ar.dist(s["units"][shooter]["pos"], s["units"][target]["pos"])
    mix = ar.GUN_MIX.get(s["units"][shooter]["type"], {})
    return any(d <= ar.GUN_SPEC[g][2] for g in mix)


def pick_target(s, side, shooters):
    """依該方應變條款的優先序挑目標：砲兵 > 偵察/觀測 > 開闊移動或未構工事 > 已構工事。"""
    cands = []
    for e in spotted(s, side):
        u = s["units"][e]
        if ar.status_of(u) not in ar.COMBAT_STATUSES:
            continue
        if not any(in_range(s, sh, e) for sh in shooters if s["units"][sh]["equip"]["guns"]):
            continue
        # 藍軍應變 2 / W1 遵法條款：三要件成立即停火（雙方皆已寫入命令者適用）
        est = u.get("personnel", 0) + u["losses"]["personnel"] or 1
        cas = u["losses"]["personnel"] / est
        a = cas >= 0.70 or (cas >= 0.50 and u.get("org", 100) <= 25) or (
            u["equip"]["tanks"] == 0 and u["equip"]["guns"] == 0 and cas >= 0.50)
        b = (not u["flags"].get("fired")) and (u["equip"]["guns"] == 0
                                               or u.get("supply_status") == "cut")
        c = u.get("supply_status") == "cut"
        if a and b and c:
            continue                        # 依該方自訂的 W1 遵法條款停火
        pri = (0 if u["equip"]["guns"] and u["type"] in ("artillery",) else
               1 if u["type"] == "recon" or u.get("is_detachment") else
               2 if (u["flags"].get("moved") or u.get("fortification", 0) == 0) else 3)
        cands.append((pri, ar.dist(s["units"][shooters[0]]["pos"], u["pos"]), e))
    cands.sort()
    return cands[0][2] if cands else None


def fire(s, side, shooters, ev, label):
    tgt = pick_target(s, side, shooters)
    if not tgt:
        return
    sh = [x for x in shooters if s["units"][x]["equip"]["guns"] and in_range(s, x, tgt)]
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
                    + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else "")
                    + f"、組織度 -{org}"))


def resolve(s, gh):
    ev = []
    # 藍軍：抽離工兵營就地留在 (4,11)（裁示 59：工兵營可入林，但本命令是留在開闊地）
    if gh >= EFF["BLU-3"] and not eng_out[0]:
        uid, _ = ar.detach_bn(s, "BLU-3", "eng", list(s["units"]["BLU-3"]["pos"]))
        eng_out[0] = True
        DIG.append(uid)
        ev.append(("allies", f"BLU-3 抽離工兵營 → {uid} 就地留於 {tuple(s['units'][uid]['pos'])}，"
                             f"為該格與相鄰的 (4,10) 補上第四兵種（裁示 48/50/55）"))

    for uid, route in MOVE.items():
        u = s["units"].get(uid)
        if not u or gh < EFF.get(uid, 0) or uid in halted:
            continue
        tgt = next((p for p in route if list(u["pos"]) != list(p)), None)
        if tgt is None:
            continue
        # 紅軍偵察隊：發現敵軍即停止前推
        if uid == "RED-2-rcn":
            near = [e for e in spotted(s, "axis")
                    if ar.dist(s["units"][e]["pos"], u["pos"]) <= 3]
            if near:
                halted.add(uid)
                ev.append((uid, f"{uid} 依命令停止前推、原地隱蔽觀察（3 格內 {', '.join(near)}）"))
                continue
        _, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, msg))

    for uid in DIG:
        u = s["units"].get(uid)
        if not u or u.get("dig_hours", 0) >= 8.0 or u["flags"].get("moved"):
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))
    for uid, pos in DIG_ON_ARRIVE.items():
        u = s["units"].get(uid)
        if u and list(u["pos"]) == list(pos) and not u["flags"].get("moved"):
            r = ar.dig(s, uid)
            if r:
                ev.append((uid, f"{uid} 抵達後構築工事 → {r[0]}（{u['dig_hours']:.2f}hr）"))

    # 火力（雙方應變條款）
    fire(s, "axis", RED_GUNS, ev, "師屬砲兵")
    fire(s, "allies", BLU_GUNS, ev, "師屬砲兵")
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
print(f"事實紀錄：{len(s.get('record',[]))} 筆")
for side in ("allies", "axis"):
    print(f"{side:7} 已偵獲：{spotted(s, side) or '（無）'}")
print()
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>6} {'工事':>6} {'暴露':>6} {'累損人':>6}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel',0):6} {u.get('fatigue',0):4} "
          f"{u.get('org',0):6} {u.get('fortification',0):6.2f} "
          f"{ar.exposure_factor(u, ar.terr(s,u['pos'])):6} {u['losses']['personnel']:6}")
