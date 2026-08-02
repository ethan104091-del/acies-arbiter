#!/usr/bin/env python3
"""Tick 4 解算（gh24-29, 1944-08-26 06:00-12:00，全程白天）★本局第一次交火★

延遲：紅軍前進指揮所 (22,8) 罩內 → 基準（L1→gh25、L2→gh26）；藍軍僅主指揮所 → +1（L1→gh26、L2→gh27）。
應變（雙方預先授權的條件反應）不吃延遲，條件成立即執行。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, orbat, hourstate as hs, command

s = of.load()
ROUTES = {k: [tuple(p) for p in v] for k, v in s.get("standing_routes", {}).items()}

for lvl, txt in [("L1", "RED-AD 固守 (20,9) 並對已偵獲的 BLU-AD-rcn 實施集中砲擊，不以戰車追擊"),
                 ("L1", "RED-2-rcn 向 (18,8) 前進偵察，觀察敵偵察營撤向與其後方主力"),
                 ("L2", "RED-2 向 (20,8) 戰鬥行進，抵達後固守並與 RED-AD 相鄰協同"),
                 ("L2", "RED-1 向 (19,12) 戰備推進，始終位於 RED-1-rcn 以東"),
                 ("L2", "RED-3 向 (19,3) 戰備推進，始終位於 RED-3-rcn 以東")]:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=0)
for lvl, txt in [("L2", "陣線變更：BLU-1→(16,8)、BLU-2→(16,9)、BLU-3→(15,10)、BLU-AD+eng→(15,9)，抵達即以eng ×1.5 挖滿工事"),
                 ("L2", "BLU-3-rcn 改任跟監 RED-SF、維持 2 格接觸當砲兵觀測員，不進其格、不交戰"),
                 ("L2", "BLU-1-rcn→(18,3) 設觀測所，搜索定位 RED-3/RED-2"),
                 ("L2", "BLU-AD-rcn→(16,6) 設觀測所，持續觀測 RED-AD 作砲兵指示"),
                 ("L2", "BLU-2-rcn→(8,12) 設觀測所，罩住主指揮所接近路與補給走廊中段"),
                 ("L2", "BLU-SF 經 (20,4)/(19,4) 森林向 (24,7)→(25,8) 森林推進"),
                 ("L1", "射擊紀律增列：敵旅級以上編隊在開闊地未構工事時可開火；仍不打敵偵察營"),
                 ("L2", "條件令：主力抵新陣線且 (15,9) 工事挖滿後於 (15,9) 架前進指揮所")]:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=1)

NEW_RED_25 = {"RED-2-rcn": [(18, 8)]}
NEW_RED_26 = {"RED-2": [(20, 8)], "RED-1": [(19, 12)], "RED-3": [(19, 3)]}
NEW_BLUE_27 = {"BLU-1": [(16, 8)], "BLU-2": [(16, 9)], "BLU-3": [(15, 10)],
               "BLU-AD": [(15, 9)], "BLU-AD-eng": [(15, 9)],
               "BLU-1-rcn": [(18, 3)], "BLU-AD-rcn": [(16, 6)], "BLU-2-rcn": [(8, 12)],
               "BLU-SF": [(19, 4), (24, 7)]}
HOLD = set(k for k in ("RED-1-rcn", "RED-3-rcn", "BLU-3-rcn", "RED-SF", "RED-AD", "RED-2-1-r4")
           if k in s["units"])
for u in s["units"].values():
    u.setdefault("fortification", 0.0)

AD_MARCH_HOURS = [0]
log = []
for gh in range(24, 30):
    command.activate_due_cps(s)
    hs.hour_brief(s)
    ev = []
    if gh == 25:
        ROUTES.update(NEW_RED_25); HOLD -= set(NEW_RED_25)
    if gh == 26:
        ROUTES.update(NEW_RED_26); HOLD -= set(NEW_RED_26)
    if gh == 27:
        ROUTES.update(NEW_BLUE_27); HOLD -= set(NEW_BLUE_27)

    # ── 砲擊（紅軍 L1 令自 gh25 起）──
    if gh >= 25:
        tgt = "BLU-AD-rcn"
        spotted = tgt in s["fog_of_war"].get("axis_spotted", [])
        if spotted and of.dist(s["units"]["RED-AD"]["pos"], s["units"][tgt]["pos"]) <= 5:
            cas, tk, gk, msg = of.bombard(s, ["RED-AD"], tgt)
            if cas or tk or gk:
                of.hurt(s, tgt, personnel=cas, tanks=tk, guns=gk,
                        org=round(cas / max(s["units"][tgt]["personnel"], 1) * 150, 1), fatigue=5,
                        note="遭敵自走砲集中砲擊")
                s["units"]["RED-AD"]["flags"]["fired"] = True
                of.consume(s, "RED-AD", "L3")
                ev.append(("axis", f"我方 RED-AD 對敵 {tgt} 實施集中砲擊：{msg}"))
                ev.append((tgt, f"{tgt} 遭敵砲擊：傷亡 {cas} 人（{msg.split('｜')[0]}）"))
                # 藍軍應變 4：偵察營遭砲擊 → 立即向西後撤 3 格
                p = s["units"][tgt]["pos"]
                esc = (max(0, p[0] - 3), p[1])
                ROUTES[tgt] = [esc]; HOLD.discard(tgt)
                ev.append(("allies", f"★應變觸發：{tgt} 遭砲擊 → 依命令向西後撤 3 格至 {esc}"))

    for uid in list(ROUTES):
        wps = ROUTES[uid]
        if uid not in s["units"] or not wps or uid in HOLD:
            continue
        u = s["units"][uid]
        # ★藍軍命令 1 的兩條自訂紀律（裁判必須執行）：
        #   ① BLU-AD 不得推進到步兵線以東，須在最前方步兵師西側 1 格以內
        #   ② BLU-AD 每 tick 行軍不超過 4 小時（節油）
        if uid in ("BLU-AD", "BLU-AD-eng"):
            front = max(s["units"][d]["pos"][0] for d in ("BLU-1", "BLU-2", "BLU-3"))
            if u["pos"][0] >= front:
                ev.append((uid, f"{uid} 依命令紀律停止前進（不得超越步兵線 x={front}）"))
                continue
            if AD_MARCH_HOURS[0] >= 4:
                ev.append((uid, f"{uid} 依節油令本 tick 行軍已達 4 小時，停止機動"))
                continue
            if uid == "BLU-AD":
                AD_MARCH_HOURS[0] += 1
        tgt = wps[0]
        moved, msg = of.advance(s, uid, tgt)
        if list(u["pos"]) == list(tgt):
            if len(wps) > 1:
                wps.pop(0)
            else:
                HOLD.add(uid); ev.append((uid, f"{uid} 抵達 {tuple(tgt)}，依命令轉入原地"))
        if moved:
            ev.append((uid, msg))
    for uid, u in s["units"].items():
        of.consume(s, uid, "L1" if u["flags"].get("moved") else "L0")
        if not u["flags"].get("moved"):
            u["fatigue"] = max(0, u.get("fatigue", 0) - 3)
    of.refresh_visibility(s)
    newly = of.spot(s)
    # 紅軍應變：RED-SF 偵獲敵 3 格內 → 向南/東脫離一格
    sf = s["units"]["RED-SF"]
    near = [u for u in s["units"].values() if u["side"] == "allies" and of.dist(u["pos"], sf["pos"]) <= 3]
    if near and sf["pos"][1] < 17:
        esc = (sf["pos"][0], sf["pos"][1] + 1)
        if of.RATE["ranger"].get(of.terr(s, esc), 0) == 0:
            esc = (sf["pos"][0] + 1, sf["pos"][1])
        if ROUTES.get("RED-SF") != [esc]:
            ROUTES["RED-SF"] = [esc]; HOLD.discard("RED-SF")
            ev.append(("axis", f"★應變觸發：RED-SF 偵獲敵於 3 格內 → 向南脫離至 {esc}"))
    for side, lst in newly.items():
        for uid in lst:
            ev.append((side, f"★我方偵獲敵 {uid} 於 {tuple(s['units'][uid]['pos'])}"))
    of.push_log(s, ev, gh_label=f"[gh{gh}] ")
    log.append(f"[gh{gh} {hs.game_time_str(gh)}] " + ("；".join(t for _, t in ev) if ev else "無事件"))
    of.clear_flags(s)
    hs.end_hour(s, log[-1])

sup = of.resupply(s)
s["standing_routes"] = {k: [list(p) for p in v] for k, v in ROUTES.items() if k not in HOLD and v}
of.save(s)
print("\n".join(log))
print("\n=== 計分 ===", of.score(s))
print("=== 斬首 ===", command.decapitation(s))
print("\n" + of.ascii_map(s, "god"))
