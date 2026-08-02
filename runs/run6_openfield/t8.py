#!/usr/bin/env python3
"""Run 6 Tick 8 終局解算（gh48-53，1944-08-27 06:00-11:00，全程白天）。

雙方新令皆 [L1]，主指揮所 +1 級 → **gh50 生效**。gh48-49 執行既有常設命令。

  藍軍 gh48-49：應變 1（舊）仍有效 → BLU-2 因敵師級在 3 格內而開始向西後撤，
                 工事於移動瞬間歸零；sp1/sp2/sp3 續行 (14,9)/(15,9) 交替攔阻射擊。
       gh50 起：撤銷全部後撤條款；BLU-AD 由 (10,9) 衝鋒 (13,9)，同格即近戰；
                 sp1/sp2/sp3 砲擊 RED-AD（本師近戰同格後停止該格射擊，避免友軍誤擊）；
                 BLU-2 固守砲擊 RED-AD；BLU-3 固守砲擊 RED-SF；BLU-1 原地不前出，
                 以 155mm 對射程內已偵獲敵編隊射擊；BLU-SF 維持隱蔽。

  紅軍 gh48-49：既有常設命令（砲群砲擊 BLU-2、RED-AD 西進 (12,9)、RED-3 向 (14,8)）。
       gh50 起：全部戰車停止機動、原地分散隱蔽；七個抽離砲營對 BLU-2 全效直接砲擊；
                 應變 1 —— 偵察隊若偵獲藍軍裝甲或砲兵且在射程內，砲群立即改打該目標。

━━ 裁判解讀（各以《裁判解讀_T8.md》單獨通知該方）━━

(甲) 紅軍應變 1 未指明多個合格目標時打哪一個。裁判採**最小解讀**：
     取其命令 1 所列優先序「火砲與裝甲目標」中**距其砲群最近**者。
     不由裁判挑選戰術上最有價值者——那是代下決定。

(乙) 藍軍 BLU-AD 之衝鋒目標為 (13,9)，但敵裝甲師依其自身命令停於 (12,9)。
     依藍軍應變 2「BLU-AD 若與敵編隊同格，立即實施近戰突擊」，
     兩者於 (12,9) 同格時即進入近戰，不再續行至 (13,9)。

(丙) 藍軍自走砲營之友軍誤擊防護依其命令 3 執行：BLU-AD 與 RED-AD 同格後，
     三個砲營停止對該格射擊，改對射程內其他已偵獲敵編隊射擊。

(丁) 近戰參數：攻方之「從行軍中接戰 ×0.7」依**該小時是否移動過**逐時判定
     （裁示 32）——衝入接戰的那一小時適用，其後陷入近戰而未移動之小時不適用；
     守方 RED-AD 依其自身命令「停止一切行軍與攻勢、原地分散隱蔽」，
     認定為**被動應戰**（def_passive=True，守 ×0.85）。兩者皆取自各自命令文義。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 48, f"必須從 gh48 起始，現在 gh={s['global_hour']}"

NEW_ORDERS = [
    ("allies", "L1", "BLU-AD", "由 (10,9) 衝鋒 (13,9)，與敵同格即近戰突擊至本局結束"),
    ("allies", "L1", "BLU-2", "撤銷後撤，固守並對 RED-AD 持續砲擊"),
    ("allies", "L1", "BLU-3", "於 (7,14) 固守，對 RED-SF 持續砲擊"),
    ("allies", "L1", "BLU-1", "於 (9,4) 固守不前出，以 155mm 對射程內已偵獲敵編隊射擊"),
    ("allies", "L1", "BLU-SF", "於 (6,4) 森林維持靜止隱蔽"),
    ("axis", "L1", "RED-AD", "停止一切行軍與攻勢，原地分散隱蔽，戰車不得機動"),
    ("axis", "L1", "RED-2", "停止一切行軍與攻勢，原地分散隱蔽"),
    ("axis", "L1", "RED-3", "停止一切行軍與攻勢，原地分散隱蔽"),
    ("axis", "L1", "RED-2-a1", "自 gh50 起原地不移動，對已偵獲 BLU-2 持續全效直接砲擊"),
]
EFF = {}
for side, lvl, uid, txt in NEW_ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    EFF[uid] = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                                extra_delay=extra)["effective_global_hour"]
G_BLU, G_RED = EFF["BLU-AD"], EFF["RED-AD"]

BLU_GUNS = ["BLU-AD-sp1", "BLU-AD-sp2", "BLU-AD-sp3"]
RED_GUNS = ["RED-2-a1", "RED-2-a2", "RED-2-a3", "RED-2-a4",
            "RED-AD-sp1", "RED-AD-sp2", "RED-AD-sp3"]
OLD_HEXES = [(14, 9), (15, 9)]          # T7 常設之交替攔阻射擊
RED_OLD_MOVE = {"RED-AD": (12, 9), "RED-3": (14, 8)}

retreat = {}          # 舊應變 1：gh48-49 仍有效
melee = [False]
log_once = set()


def sp(s, side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def is_div(u):
    return not u.get("is_detachment") and u.get("type") in ("infantry", "armor")


def shoot(s, shooters, tgt, ev, label):
    """對已偵獲編隊直接砲擊（全效）。"""
    live = [u for u in shooters if u in s["units"]
            and not s["units"][u]["flags"].get("moved")
            and s["units"][u]["equip"]["guns"] > 0]
    if not live or tgt not in s["units"]:
        return
    cas, tk, gk, msg = ar.bombard(s, live, tgt)
    if not (cas or tk or gk):
        return
    t = s["units"][tgt]
    pct = 100.0 * cas / max(t.get("personnel", 1), 1)
    org = ar.org_impact(s, tgt, pct)
    ar.hurt(s, tgt, personnel=cas, tanks=tk, guns=gk, org=org,
            fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
    ev.append((live[0], f"{label} → {tgt}：{msg}（組織度 -{org}）"))
    ev.append((tgt, f"{tgt} 遭敵砲擊：傷亡 {cas} 人"
                    + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else "")
                    + f"、組織度 -{org}"))


def in_range(s, sh, tgt):
    u, t = s["units"][sh], s["units"][tgt]
    mix = u.get("gun_mix") or ar.GUN_MIX.get(u["type"], {})
    d = ar.dist(u["pos"], t["pos"])
    return any(d <= ar.GUN_SPEC[g][2] for g in mix)


def nearest_target(s, shooters, side, kinds, exclude_pos=None):
    """所列類別中距砲群最近且在射程內者。exclude_pos 之格內單位一律排除。

    exclude_pos 用於友軍誤擊防護：近戰格必須在**挑選前**就排除，
    不能挑完最近的再否決——否則最近者恰為近戰格時，該砲群會變成完全不射擊。
    （終局首次解算時即因此讓三個自走砲營閒置三小時，已修。）
    """
    anchor = s["units"][shooters[0]]["pos"]
    cands = [(ar.dist(anchor, s["units"][e]["pos"]), e) for e in sp(s, side)
             if s["units"][e].get("type") in kinds
             and (exclude_pos is None or list(s["units"][e]["pos"]) != list(exclude_pos))
             and any(in_range(s, x, e) for x in shooters if x in s["units"])]
    return min(cands)[1] if cands else None


def resolve(s, gh):
    ev = []

    # ① gh48-49：藍軍舊應變 1 仍有效（敵師級 3 格內 → 向西後撤 2 格）
    if gh < G_BLU:
        for uid in ("BLU-1", "BLU-2", "BLU-3"):
            u = s["units"].get(uid)
            if not u or uid in retreat:
                continue
            th = [e for e in sp(s, "allies")
                  if is_div(s["units"][e]) and ar.dist(s["units"][e]["pos"], u["pos"]) <= 3]
            if th:
                retreat[uid] = [max(0, u["pos"][0] - 2), u["pos"][1]]
                ev.append((uid, f"{uid} 依舊應變 1 開始向西後撤至 {tuple(retreat[uid])}"
                                f"（敵師級 {', '.join(th)} 在 3 格內）｜工事與偽裝歸零"))
    else:
        for uid in list(retreat):
            retreat.pop(uid)
            if uid not in log_once:
                log_once.add(uid)
                ev.append((uid, f"{uid} 新令生效：撤銷後撤條款，於 "
                                f"{tuple(s['units'][uid]['pos'])} 固守不再移動"))
    for uid, dest in list(retreat.items()):
        u = s["units"][uid]
        if list(u["pos"]) == list(dest):
            retreat.pop(uid)
            continue
        _, m = ar.advance(s, uid, list(dest))
        ev.append((uid, f"{uid} 後撤中：{m}"))

    # ② 紅軍機動：gh50 前續行常設命令，gh50 起全部停止
    if gh < G_RED:
        for uid, tgt in RED_OLD_MOVE.items():
            u = s["units"].get(uid)
            if u and list(u["pos"]) != list(tgt):
                _, m = ar.advance(s, uid, list(tgt))
                ev.append((uid, m))
    elif "red_halt" not in log_once:
        log_once.add("red_halt")
        ev.append(("axis", "紅軍新令生效：全部戰車停止機動、原地分散隱蔽"))

    # ③ 藍軍裝甲師衝鋒（gh50 起）；與敵同格即近戰
    ad = s["units"]["BLU-AD"]
    foe = next((e for e in sp(s, "allies")
                if list(s["units"][e]["pos"]) == list(ad["pos"])
                and is_div(s["units"][e])), None)
    if gh >= G_BLU and not melee[0] and foe is None:
        if list(ad["pos"]) != [13, 9]:
            _, m = ar.advance(s, "BLU-AD", [13, 9])
            ev.append(("BLU-AD", f"BLU-AD 衝鋒：{m}"))
        foe = next((e for e in sp(s, "allies")
                    if list(s["units"][e]["pos"]) == list(ad["pos"])
                    and is_div(s["units"][e])), None)
    if gh >= G_BLU and foe:
        melee[0] = True
        # 裁示 32：「從行軍中接戰 ×0.7」是**該小時的戰術狀態**，不是整場交戰的標籤。
        # 判準＝該編隊該小時是否移動過（flags["moved"]），純機械、零裁量、雙方同適用。
        from_march = bool(ad["flags"].get("moved"))
        msg, push = ar.battle(s, ["BLU-AD"], [foe], list(ad["pos"]),
                              atk_from_march=from_march, def_passive=True)
        ev.append(("BLU-AD", f"★近戰突擊於 {tuple(ad['pos'])}：{msg}"))
        ev.append((foe, f"★遭 BLU-AD 近戰突擊：{msg}"))

    # ④ 藍軍火力
    if gh < G_BLU:
        pos = OLD_HEXES[gh % 2]
        live = [u for u in BLU_GUNS if not s["units"][u]["flags"].get("moved")]
        if live:
            cas, tk, gk, msg, hit = ar.bombard_hex(s, live, list(pos))
            if hit:
                t = s["units"][hit]
                org = ar.org_impact(s, hit, 100.0 * cas / max(t.get("personnel", 1), 1))
                ar.hurt(s, hit, personnel=cas, tanks=tk, guns=gk, org=org,
                        fatigue=ar.fatigue_from_combat("light"), note="遭敵攔阻射擊")
                ev.append((live[0], f"藍軍砲群攔阻射擊 {tuple(pos)} → {msg}（組織度 -{org}）"))
                ev.append((hit, f"{hit} 遭敵攔阻射擊：傷亡 {cas} 人"
                                + (f"、戰車 -{tk}" if tk else "")
                                + (f"、火砲 -{gk}" if gk else "") + f"、組織度 -{org}"))
    else:
        # 自走砲營：本師近戰同格後停止該格射擊（命令 3 之友軍誤擊防護）
        t1 = "RED-AD" if "RED-AD" in sp(s, "allies") else None
        if melee[0] and t1 and list(s["units"][t1]["pos"]) == list(ad["pos"]):
            # 友軍誤擊防護：本師所在格排除於候選之外，再挑最近者
            t1 = nearest_target(s, BLU_GUNS, "allies",
                                ("infantry", "armor", "ranger", "artillery", "recon"),
                                exclude_pos=ad["pos"])
        if t1:
            shoot(s, BLU_GUNS, t1, ev, "藍軍自走砲群")
        # BLU-2 → RED-AD；BLU-3 → RED-SF；BLU-1 → 射程內已偵獲者
        if "RED-AD" in sp(s, "allies"):
            shoot(s, ["BLU-2"], "RED-AD", ev, "BLU-2")
        elif sp(s, "allies"):
            t = nearest_target(s, ["BLU-2"], "allies",
                               ("infantry", "armor", "ranger", "artillery", "recon"),
                               exclude_pos=ad["pos"] if melee[0] else None)
            if t:
                shoot(s, ["BLU-2"], t, ev, "BLU-2（應變 3 改目標）")
        if "RED-SF" in sp(s, "allies") and in_range(s, "BLU-3", "RED-SF"):
            shoot(s, ["BLU-3"], "RED-SF", ev, "BLU-3")
        t = nearest_target(s, ["BLU-1"], "allies",
                           ("infantry", "armor", "ranger", "artillery", "recon"))
        if t:
            shoot(s, ["BLU-1"], t, ev, "BLU-1")

    # ⑤ 紅軍火力：gh50 前打 BLU-2；gh50 起依其應變 1 改打最近之藍軍裝甲／砲兵
    live_red = [u for u in RED_GUNS if u in s["units"]]
    if live_red:
        if gh < G_RED:
            if "BLU-2" in sp(s, "axis"):
                shoot(s, live_red, "BLU-2", ev, "紅軍砲群")
        else:
            t = nearest_target(s, live_red, "axis", ("armor", "artillery"))
            if t is None and "BLU-2" in sp(s, "axis"):
                t = "BLU-2"
            if t:
                shoot(s, live_red, t, ev, "紅軍砲群")

    return ev


log = []
lines = ar.run_tick(s, resolve, hours=6, log=log)
ar.save(s)
print("=" * 78)
for line in lines:
    print(line)
print("=" * 78)
sc = ar.score(s)
print(f"★終局計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}"
      f"｜斬首：{command.decapitation(s)}")
print(f"  藍造成 {sc['allies']['inflicted']}")
print(f"  紅造成 {sc['axis']['inflicted']}")
print(f"事實紀錄：{len(s.get('record', []))} 筆")
print()
print(f"{'編隊':14} {'位置':10} {'兵力':>6} {'累損':>5} {'戰車':>4} {'火砲':>4} {'org':>6} {'狀態':>10}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:14} {str(tuple(u['pos'])):10} {u.get('personnel', 0):6} "
          f"{u['losses']['personnel']:5} {u['equip']['tanks']:4} {u['equip']['guns']:4} "
          f"{u.get('org', 0):6.1f} {ar.status_of(u):>10}")
