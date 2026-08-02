#!/usr/bin/env python3
"""Run 6 Tick 7 解算（gh42-47，1944-08-27 00:00-05:00，gh42-46 夜間、gh47 黎明）。

雙方新令皆 [L1]，主指揮所 +1 級 → **gh44 生效**。gh42-43 執行既有常設命令。

  藍軍 抽離 BLU-AD 之 sp1/sp2/sp3 留守 (10,9)；三營與 BLU-2 對 (14,9) 攔阻射擊；
       BLU-AD 本隊原地不動、不開火，保住有頂蓋與偽裝，衝擊留待 T8 白天；
       BLU-1/BLU-3/BLU-SF 固守或續挖。

  紅軍 抽離 RED-2 之 a1-a4、RED-AD 之 sp1-sp3 留置原地，對 BLU-2 持續砲擊；
       RED-2 本隊西進 (13,9)、RED-AD 本隊西進 (12,9) 準備黎明近戰；
       RED-3 轉為預備隊向 (14,8)；RED-SF 進至 (8,14) 以東相鄰格隱蔽待機；
       RED-1 與 RED-2-1-r4 原地固守。

━━ 裁判解讀（各以《裁判解讀_T7.md》單獨通知該方）━━

(甲) 藍軍應變 3 的執行方式。其文為「依落彈分析所示之方位，由射程內未於該小時行軍
     之砲兵對**該方位上距我 3 格與 4 格之兩格**實施攔阻射擊」。自 BLU-2 (11,9) 起
     正東方向的 3 格與 4 格分別為 **(14,9)** 與 **(15,9)**。其命令已將全部火力指定
     (14,9)，故應變 3 的增額指示為「亦須涵蓋 (15,9)」。
     裁判採**逐小時交替**：偶數小時全部打 (14,9)、奇數小時全部打 (15,9)。
     理由：一個編隊一小時只能執行一次火力任務，要涵蓋兩格只能分配；
     交替是唯一不含裁判裁量的分配方式（任何「誰打哪格」的指派都是代下戰術決定）。

(乙) 藍軍 BLU-AD 本隊抽離砲兵後 **equip["guns"] = 0**，故縱使應變 3 或 4 觸發，
     它也無砲可射。其命令中「不開火」與此一致，無衝突。

(丙) 紅軍「各砲營射擊時母師不得同時射擊」為其自我約束，裁判照辦：
     抽離之砲營射擊時，其母師不列入射擊方。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 42, f"必須從 gh42 起始，現在 gh={s['global_hour']}"

NEW_ORDERS = [
    ("allies", "L1", "BLU-AD", "抽離 sp1/sp2/sp3 留守 (10,9)；本隊原地不動、不開火、完全休整"),
    ("allies", "L1", "BLU-2", "於 (11,9) 對 (14,9) 實施攔阻射擊，工事維持，不移動"),
    ("allies", "L1", "BLU-3", "於 (7,14) 續行構築工事至有頂蓋級"),
    ("allies", "L1", "BLU-1", "於 (9,4) 固守，工事與偽裝維持，完全休整"),
    ("allies", "L1", "BLU-SF", "於 (6,4) 森林維持靜止隱蔽"),
    ("axis", "L1", "RED-2", "抽離 a1-a4 留置原地對 BLU-2 砲擊；本隊西進 (13,9) 後停止"),
    ("axis", "L1", "RED-AD", "抽離 sp1-sp3 留置原地對 BLU-2 砲擊；本隊西進 (12,9) 後停止"),
    ("axis", "L1", "RED-SF", "進至 (8,14) 以東相鄰格隱蔽待機，只偵察不強攻"),
    ("axis", "L1", "RED-3", "向 (14,8) 轉為預備隊，不得砲擊"),
    ("axis", "L1", "RED-1", "原地固守 (21,12)，不移動不射擊"),
]
EFF = {}
for side, lvl, uid, txt in NEW_ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    EFF[uid] = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                                extra_delay=extra)["effective_global_hour"]

BLU_DET = ["sp1", "sp2", "sp3"]
RED_DET = {"RED-2": ["a1", "a2", "a3", "a4"], "RED-AD": ["sp1", "sp2", "sp3"]}
BLU_HEXES = [(14, 9), (15, 9)]        # 解讀(甲)：逐小時交替
RED_MOVE = {"RED-AD": (12, 9), "RED-2": (13, 9), "RED-3": (14, 8), "RED-SF": (9, 14)}
DIG_BLU = ["BLU-3"]                    # BLU-2/BLU-1/BLU-AD/BLU-SF 工事已封頂

blu_guns, red_guns = [], []
done = {"blu": False, "red": False}
halted = set()


def spotted(s, side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def fire_hex(s, shooters, pos, ev, label):
    live = [u for u in shooters if u in s["units"]
            and not s["units"][u]["flags"].get("moved")
            and s["units"][u]["equip"]["guns"] > 0]
    if not live:
        return
    cas, tk, gk, msg, hit = ar.bombard_hex(s, live, list(pos))
    if hit is None:
        ev.append((live[0], f"{label} 對 {tuple(pos)} 攔阻射擊：該格無敵編隊，"
                            f"彈藥與暴露照付，效果為零"))
        return
    t = s["units"][hit]
    pct = 100.0 * cas / max(t.get("personnel", 1), 1)
    org = ar.org_impact(s, hit, pct)
    ar.hurt(s, hit, personnel=cas, tanks=tk, guns=gk, org=org,
            fatigue=ar.fatigue_from_combat("light"), note="遭敵攔阻射擊")
    ev.append((live[0], f"{label} 對 {tuple(pos)} 攔阻射擊 → {msg}（組織度 -{org}）"))
    ev.append((hit, f"{hit} 遭敵攔阻射擊：傷亡 {cas} 人"
                    + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else "")
                    + f"、組織度 -{org}"))


def fire_unit(s, shooters, tgt, ev, label):
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
    ev.append((live[0], f"{label} 對 {tgt} 砲擊 → {msg}（組織度 -{org}）"))
    ev.append((tgt, f"{tgt} 遭敵砲擊：傷亡 {cas} 人"
                    + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else "")
                    + f"、組織度 -{org}"))


def resolve(s, gh):
    ev = []

    # ① 抽離（雙方新令生效時）
    if gh >= EFF["BLU-AD"] and not done["blu"]:
        done["blu"] = True
        for c in BLU_DET:
            uid, _ = ar.detach_bn(s, "BLU-AD", c, list(s["units"]["BLU-AD"]["pos"]))
            blu_guns.append(uid)
        ev.append(("BLU-AD", f"BLU-AD 抽離自走砲營 → {', '.join(blu_guns)} 留守 "
                             f"{tuple(s['units'][blu_guns[0]]['pos'])}；"
                             f"母師餘 戰車{s['units']['BLU-AD']['equip']['tanks']}"
                             f"／火砲{s['units']['BLU-AD']['equip']['guns']}"))
    if gh >= EFF["RED-2"] and not done["red"]:
        done["red"] = True
        for div, codes in RED_DET.items():
            for c in codes:
                uid, _ = ar.detach_bn(s, div, c, list(s["units"][div]["pos"]))
                red_guns.append(uid)
            ev.append((div, f"{div} 抽離砲兵營 → "
                            f"{', '.join(u for u in red_guns if u.startswith(div))} 留置 "
                            f"{tuple(s['units'][div]['pos'])}；母師餘 "
                            f"火砲{s['units'][div]['equip']['guns']}"))

    # ② 紅軍機動（RED-AD 於 gh44 前仍受 T6「停止機動」之常設命令拘束）
    for uid, tgt in RED_MOVE.items():
        u = s["units"].get(uid)
        if not u or uid in halted:
            continue
        if uid == "RED-AD" and gh < EFF["RED-AD"]:
            continue                                   # T6 令：停止一切機動
        if list(u["pos"]) == list(tgt):
            halted.add(uid)
            ev.append((uid, f"{uid} 抵達 {tuple(tgt)}，停止行軍"))
            continue
        _, m = ar.advance(s, uid, list(tgt))
        ev.append((uid, m))

    # ③ 紅軍火力：gh44 前由 RED-AD 本隊（T6 常設令），gh44 後由抽離砲營（解讀丙）
    if gh < EFF["RED-AD"]:
        if "BLU-2" in spotted(s, "axis"):
            fire_unit(s, ["RED-AD"], "BLU-2", ev, "RED-AD")
    elif red_guns:
        if "BLU-2" in spotted(s, "axis"):
            fire_unit(s, red_guns, "BLU-2", ev, "紅軍抽離砲群")

    # ④ 藍軍火力：命令＋應變 3，逐小時交替 (14,9)/(15,9)（解讀甲）
    if gh >= EFF["BLU-2"]:
        pos = BLU_HEXES[(gh - EFF["BLU-2"]) % 2]
        fire_hex(s, ["BLU-2"] + blu_guns, pos, ev, "藍軍砲群")

    # ⑤ 藍軍構築工事（射擊之小時仍可構築——裁判解讀_T6 已向紅軍明示，雙方同適用）
    for uid in DIG_BLU + blu_guns:
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
print(f"{'編隊':14} {'位置':10} {'兵力':>6} {'累損':>5} {'火砲':>4} {'org':>6} {'工事':>5} "
      f"{'暴露':>6} {'能見':>12}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:14} {str(tuple(u['pos'])):10} {u.get('personnel', 0):6} "
          f"{u['losses']['personnel']:5} {u['equip']['guns']:4} {u.get('org', 0):6.1f} "
          f"{u.get('dig_hours', 0):5.1f} {ar.exposure_factor(u, ar.terr(s, u['pos'])):6} "
          f"{u.get('visibility_state', '?'):>12}")
