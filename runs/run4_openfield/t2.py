#!/usr/bin/env python3
"""Tick 2 解算（gh12-17, 18:00-24:00：gh12 黃昏、gh13-17 夜間）。

延遲：雙方皆有主指揮所 → +1。紅軍全 L1 → gh14 生效；藍軍 L1 → gh14、L2 → gh15 生效。
生效前雙方 Tick 1 常態令繼續（紅軍主力續推 x=21；藍軍依 T1 令「T2 全休」原地）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, orbat, hourstate as hs, command

s = of.load()
ROUTES = {k: [tuple(p) for p in v] for k, v in s.get("standing_routes", {}).items()}

RED_T2 = [("L1", "軍長於 (22,8) 架設前進指揮所並進駐（RED-2 掩護），主指揮所 (29,8) 保留"),
          ("L1", "RED-3 停止前推、原地戰備休整、北翼警戒，不進森林"),
          ("L1", "RED-2 停止前推、原地戰備休整、維持與 RED-AD 相鄰支援"),
          ("L1", "RED-1 停止前推、原地戰備休整、南翼警戒"),
          ("L1", "RED-AD 固守 (20,9) 戰備休整，作為前進指揮所中央預備，不主動離格"),
          ("L1", "RED-SF 於 (19,15) 停止前推、隱蔽休整監視，夜間不主動接戰")]
BLUE_T2 = [("L2", "新集結線 BLU-1→(15,9)、BLU-2→(15,10)、BLU-3→(15,11)、BLU-AD→(14,10)；T2 全休、T3 夜行4hr+休2hr、T4/T5 白天全程行軍；抵達後挖滿工事固守"),
           ("L2", "偵察幕前推 BLU-1-rcn→(16,3)、BLU-AD-rcn→(16,8)、BLU-3-rcn→(16,14)；T2 全休、T3 夜行4hr+休2hr"),
           ("L2", "BLU-2-rcn 解除巡邏、進駐 (5,15) 設靜止觀測所"),
           ("L2", "BLU-SF 續向東滲透，最終 (25,8) 森林；航路 (12,2)→(18,3)→(22,5)，T6 夜切 (24,7)→(25,8)"),
           ("L1", "BLU-2-1-r4/2-r4/3-r4 維持 (4,10) 固守、工事挖滿、不得離格"),
           ("L2", "砲兵不拆分、隨母編隊機動；依裁示 9 接受友軍觀測指示越視距射擊")]

for lvl, txt in RED_T2:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=1)
for lvl, txt in BLUE_T2:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=1)

# 裁示 4：指揮所架設令不吃通訊延遲，只吃 2hr 架設 → gh14 生效、軍長進駐
command.establish_cp(s, "axis", "fwd", (22, 8))

RED_STOP = ["RED-1", "RED-2", "RED-3", "RED-AD", "RED-SF"]
NEW_BLUE = {"BLU-1": [(15, 9)], "BLU-2": [(15, 10)], "BLU-3": [(15, 11)], "BLU-AD": [(14, 10)],
            "BLU-SF": [(12, 2), (18, 3), (22, 5)]}
NEW_BLUE_DET = {"BLU-1-rcn": [(16, 3)], "BLU-AD-rcn": [(16, 8)], "BLU-3-rcn": [(16, 14)],
                "BLU-2-rcn": [(5, 15)]}
BLUE_REST_THIS_TICK = True          # 藍軍 T1 常態令與 T2 新令皆規定 T2 全休
HOLD = set()

log = []
for gh in range(12, 18):
    fired = command.activate_due_cps(s)
    br = hs.hour_brief(s)
    ev = []
    for side, kind, pos in fired:
        ev.append((None, f"{'紅' if side=='axis' else '藍'}軍{kind}指揮所於 {tuple(pos)} 架設完成、軍長進駐"))
    if gh == 14:        # 紅軍 L1 生效 → 全線停止前推、原地休整
        for uid in RED_STOP:
            ROUTES.pop(uid, None)
            HOLD.add(uid)
        ev.append((None, "紅軍停止前推令生效：全編隊轉入原地戰備休整"))
    if gh == 15:        # 藍軍 L2 生效（但本 tick 仍規定全休 → 只換目標、不移動）
        ROUTES.update({k: [tuple(p) for p in v] for k, v in NEW_BLUE.items()})
        ROUTES.update({k: [tuple(p) for p in v] for k, v in NEW_BLUE_DET.items()})
        HOLD -= set(NEW_BLUE) | set(NEW_BLUE_DET)
        ev.append((None, "藍軍新集結線令生效（x=15 線），惟本 tick 仍依令全休不移動"))
    for uid in list(ROUTES):
        wps = ROUTES[uid]
        if uid not in s["units"] or not wps or uid in HOLD:
            continue
        u = s["units"][uid]
        # 藍軍本 tick 全休（T1/T2 令都規定）；唯 BLU-2-3-r4 仍在赴 (4,10) 途中（警衛任務未達位）
        if u["side"] == "allies" and BLUE_REST_THIS_TICK and uid != "BLU-2-3-r4":
            continue
        tgt = wps[0]
        moved, msg = of.advance(s, uid, tgt)
        if list(u["pos"]) == list(tgt):
            if len(wps) > 1:
                wps.pop(0)
            else:
                HOLD.add(uid)
                ev.append((uid, f"{uid} 抵達 {tuple(tgt)}，依命令轉入原地"))
        if moved:
            ev.append((uid, msg))
    # 消耗：移動=L1；原地=L0。休整降疲勞（完全休整 -10、戰備休整 -3）
    for uid, u in s["units"].items():
        if u["flags"].get("moved"):
            of.consume(s, uid, "L1")
        else:
            of.consume(s, uid, "L0")
            rest = 10 if u["side"] == "allies" else 3      # 藍=完全休整、紅=戰備休整（各自命令所寫）
            u["fatigue"] = max(0, u.get("fatigue", 0) - rest)
    of.refresh_visibility(s)
    newly = of.spot(s)
    for side, lst in newly.items():
        for uid in lst:
            ev.append((None, f"★{'藍軍' if side=='allies' else '紅軍'}偵獲 {uid} 於 {tuple(s['units'][uid]['pos'])}"))
    of.push_log(s, ev, gh_label=f"[gh{gh}] ")
    summary = f"[gh{gh} {hs.game_time_str(gh)} {hs.daynight(gh)}] " + ("；".join(t for _, t in ev) if ev else "雙方無動作（休整／延遲中）")
    log.append(summary)
    of.clear_flags(s)
    hs.end_hour(s, summary)

sup = of.resupply(s)
dec = command.decapitation(s)
s["standing_routes"] = {k: [list(p) for p in v] for k, v in ROUTES.items() if k not in HOLD and v}
of.save(s)
print("\n".join(log))
print("\n=== 補給 ===", {k: v for k, v in sup.items() if v != "intact"} or "全部 intact")
print("=== 斬首 ===", dec)
print("=== 紅軍指揮所守備 ===", of.cp_garrison(s, "axis"))
print("=== 藍軍指揮所守備 ===", of.cp_garrison(s, "allies"))
print("=== 偵獲 ===", "藍:", s["fog_of_war"]["allies_spotted"], "紅:", s["fog_of_war"]["axis_spotted"])
print("\n" + of.ascii_map(s, "god"))
