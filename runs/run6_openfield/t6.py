#!/usr/bin/env python3
"""Run 6 Tick 6 解算（gh36-41，1944-08-26 18:00-23:00）。

gh36 黃昏（引擎判定仍屬白天），gh37-41 夜間：移動 ×0.5、行軍疲勞 +8/hr、
視距縮為師 2／特戰 3／偵察 3。

雙方新令皆 [L1]，主指揮所 +1 級 → **gh38 生效**。gh36-37 執行既有常設命令。

  藍軍 BLU-3 停止後撤、就地構築工事（其後撤於 gh36 走完最後一格後即完成）；
       BLU-AD、BLU-1 固守並完全休整（工事有頂蓋＋偽裝已完成）；
       BLU-2 續挖至有頂蓋；BLU-SF 於森林續挖。全軍不移動、不主動開火。
       應變門檻由「師級或旅級」提高為**僅師級**；BLU-SF 明令即使條件成立亦不後撤。

  紅軍 RED-AD 停止機動、以全師火砲持續砲擊 BLU-2；RED-2-rcn 前出 (14,9) 持續觀測；
       RED-2 續沿軸線西進、接觸即近戰；RED-SF 向 (9,14) 追擊 BLU-3。

━━ 裁判的三項解讀（各以《裁判解讀_T6.md》單獨通知該方）━━

(甲) 藍軍 BLU-2 **不還擊**。理由三項，任一單獨成立：
     ① 其命令自 T5 起一貫載明「不主動開火」，且藍軍全局未曾授權任何火力任務；
     ② 夜間師級視距 2 格，射擊方在其視距外，藍軍無從識別目標；
     ③ 修正 C 的攔阻射擊雖可對格面開火而不需偵獲，但須**指揮官指定格子**。
        由裁判代選一格等同代下戰術決定，且開火會使該編隊轉為 EXPOSED。
     裁判不代為決定。此缺口於解算後通知藍軍，可於 T7 補正，不追溯。

(乙) 紅軍 RED-SF **不攻擊**。其命令為「向 (9,14) 機動追擊 BLU-3；接觸後立即近戰襲擊」，
     但 BLU-3 已西移，(9,14) 無敵編隊，故「接觸」要件不成立。
     其自身應變 2 明定「若 BLU-3 向西撤退，改在最後偵獲位置持續偵察，不單獨深入」，
     裁判依該條執行：進至 (9,14) 後就地觀測，不再西進。

(丙) 紅軍 RED-AD 的砲擊自 **gh38** 起始。其「停止機動」之新令 gh38 生效，
     gh36-37 仍執行既有的西進常設命令。依裁示 18，行軍之小時不得砲擊。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 36, f"必須從 gh36 起始，現在 gh={s['global_hour']}"

NEW_ORDERS = [
    ("allies", "L1", "BLU-3", "停止後撤，就地構築工事，優先達散兵壕級，此後固守"),
    ("allies", "L1", "BLU-AD", "於 (10,9) 固守，工事與偽裝維持，完全休整"),
    ("allies", "L1", "BLU-1", "於 (9,4) 固守，工事與偽裝維持，完全休整"),
    ("allies", "L1", "BLU-2", "於 (11,9) 續行構築工事至有頂蓋級"),
    ("allies", "L1", "BLU-SF", "於 (6,4) 森林維持靜止隱蔽並續行構築工事"),
    ("axis", "L1", "RED-AD", "停止一切機動，未行軍之小時以全師火砲持續砲擊 BLU-2"),
    ("axis", "L1", "RED-2-rcn", "向 (14,9) 機動並持續偵察 BLU-2，不主動交戰"),
    ("axis", "L1", "RED-2", "續沿 (17,9)-(13,9) 軸線西進，接觸 BLU-2 即近戰攻擊"),
    ("axis", "L1", "RED-SF", "向 (9,14) 機動追擊 BLU-3，接觸後近戰襲擊"),
]
EFF = {}
for side, lvl, uid, txt in NEW_ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    EFF[uid] = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                                extra_delay=extra)["effective_global_hour"]

RETREAT = {"BLU-3": [7, 14]}          # T5 未走完的應變後撤，續行至 gh38 新令生效為止
AXIS_OLD = {"RED-AD": (12, 9), "RED-2": (13, 9)}   # gh36-37 的既有西進常設命令
RED_MOVE_NEW = {"RED-2-rcn": (14, 9), "RED-SF": (9, 14), "RED-2": (13, 9)}
DIG = ["BLU-2", "BLU-SF"]             # BLU-3 於新令生效後加入
ad_stopped = [False]
sf_holding = [False]
halted, retreated = set(), set()


def spotted(s, side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def is_div(u):
    """師級：非抽離營，且兵種為 infantry/armor（旅級 ranger 不算——藍軍 T6 已提高門檻）。"""
    return not u.get("is_detachment") and u.get("type") in ("infantry", "armor")


def resolve(s, gh):
    ev = []

    # ① 藍軍應變 1（T6 起：僅敵師級觸發；BLU-SF 依應變 5 一律不後撤）
    for uid in ("BLU-1", "BLU-2", "BLU-3", "BLU-AD"):
        u = s["units"].get(uid)
        if not u or uid in retreated or uid in RETREAT:
            continue
        threat = [e for e in spotted(s, "allies")
                  if is_div(s["units"][e]) and ar.dist(s["units"][e]["pos"], u["pos"]) <= 3]
        if threat:
            retreated.add(uid)
            RETREAT[uid] = [max(0, u["pos"][0] - 2), u["pos"][1]]
            ev.append((uid, f"{uid} 依應變 1 開始向西後撤 2 格至 {tuple(RETREAT[uid])}"
                            f"（敵師級 {', '.join(threat)} 已在 3 格內）｜工事與偽裝歸零"))

    # ①-b 後撤續行至終點；BLU-3 的新令於 gh38 生效即停止後撤
    for uid, dest in list(RETREAT.items()):
        u = s["units"].get(uid)
        if not u:
            continue
        if uid == "BLU-3" and gh >= EFF["BLU-3"]:
            RETREAT.pop(uid)
            DIG.append(uid)
            ev.append((uid, f"BLU-3 新令生效：停止後撤，於 {tuple(u['pos'])} 就地構築工事"))
            continue
        if list(u["pos"]) == list(dest):
            RETREAT.pop(uid)
            if uid == "BLU-3":
                DIG.append(uid)
            ev.append((uid, f"{uid} 後撤完成，抵達 {tuple(dest)}"))
            continue
        _, m = ar.advance(s, uid, list(dest))
        ev.append((uid, f"{uid} 後撤中：{m}"))

    # ② 紅軍機動
    for uid in ("RED-AD", "RED-2", "RED-2-rcn", "RED-SF"):
        u = s["units"].get(uid)
        if not u or uid in halted:
            continue
        if uid == "RED-AD":
            if gh >= EFF["RED-AD"]:
                if not ad_stopped[0]:
                    ad_stopped[0] = True
                    ev.append((uid, f"RED-AD 新令生效：停止一切機動，就地於 "
                                    f"{tuple(u['pos'])} 轉為射擊平台"))
                continue                       # 停止機動
            tgt = AXIS_OLD[uid]
        elif gh < EFF.get(uid, 99):
            tgt = AXIS_OLD.get(uid)
            if tgt is None:
                continue
        else:
            tgt = RED_MOVE_NEW[uid]
            # 解讀(乙)：RED-SF 抵 (9,14) 而該處無敵編隊 → 依其應變 2 就地觀測，不再西進
            if uid == "RED-SF" and list(u["pos"]) == list(tgt):
                if not sf_holding[0]:
                    sf_holding[0] = True
                    halted.add(uid)
                    ev.append((uid, "RED-SF 抵 (9,14)，該格無敵編隊，「接觸」要件不成立；"
                                    "依其應變 2 就地持續偵察，不單獨深入"))
                continue
        if list(u["pos"]) == list(tgt):
            continue
        _, m = ar.advance(s, uid, list(tgt))
        ev.append((uid, m))

    # ③ 紅軍 RED-AD 的砲擊（裁示 18：該小時未行軍才可實施）
    if ad_stopped[0]:
        ad = s["units"]["RED-AD"]
        tgt = "BLU-2"
        if tgt in spotted(s, "axis"):
            d = ar.dist(ad["pos"], s["units"][tgt]["pos"])
            rng = max(ar.GUN_SPEC[g][2] for g in ar.GUN_MIX["armor"])
            if d <= rng:
                cas, tk, gk, msg = ar.bombard(s, ["RED-AD"], tgt)
                if cas or tk or gk:
                    pct = 100.0 * cas / max(s["units"][tgt].get("personnel", 1), 1)
                    org = ar.org_impact(s, tgt, pct)
                    ar.hurt(s, tgt, personnel=cas, tanks=tk, guns=gk, org=org,
                            fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
                    ev.append(("RED-AD", f"RED-AD 對 {tgt} 實施砲擊：{msg}（組織度 -{org}）"))
                    ev.append((tgt, f"{tgt} 遭敵砲擊：傷亡 {cas} 人"
                                    + (f"、戰車 -{tk}" if tk else "")
                                    + (f"、火砲 -{gk}" if gk else "") + f"、組織度 -{org}"))
                else:
                    ev.append(("RED-AD", f"RED-AD 對 {tgt} 射擊未生效果：{msg}"))

    # ④ 藍軍構築工事（解讀(甲)：藍軍不還擊——未授權火力任務、目標在視距外、
    #    攔阻射擊須由指揮官指定格子）
    for uid in DIG:
        u = s["units"].get(uid)
        if not u or u["flags"].get("moved") or u.get("dig_hours", 0.0) >= 8.0:
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))

    return ev


log = []
lines = ar.run_tick(s, resolve, hours=6, log=log)
ar.save(s)
print("=" * 78)
for line in lines:
    print(line)
print("=" * 78)
sc = ar.score(s)
print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}"
      f"｜斬首：{command.decapitation(s)}")
print(f"事實紀錄：{len(s.get('record', []))} 筆")
for side in ("allies", "axis"):
    print(f"{side:7} 已偵獲敵編隊：{spotted(s, side) or '（無）'}")
print()
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'累損':>5} {'疲勞':>4} {'org':>5} {'工事':>5} "
      f"{'偽裝':>5} {'暴露':>6} {'能見':>12}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel', 0):6} "
          f"{u['losses']['personnel']:5} {u.get('fatigue', 0):4} {u.get('org', 0):5} "
          f"{u.get('dig_hours', 0):5.1f} {u.get('camo_hours', 0):5.1f} "
          f"{ar.exposure_factor(u, ar.terr(s, u['pos'])):6} "
          f"{u.get('visibility_state', '?'):>12}")
