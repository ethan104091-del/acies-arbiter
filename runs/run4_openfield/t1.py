#!/usr/bin/env python3
"""Tick 1 解算（gh6-11, 12:00-18:00 白天）。

延遲：雙方皆有主指揮所 → +1 級。紅軍全 L1 → gh8 生效；藍軍 L1 → gh8、L2 → gh9 生效。
生效前，雙方 Tick 0 的常態令繼續執行（這是「多 tick 連續令」的合法效果）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, orbat, hourstate as hs, command

s = of.load()
ROUTES = {k: [tuple(p) for p in v] for k, v in s.get("standing_routes", {}).items()}

RED_T1 = [("L1", t) for t in [
    "RED-3-rcn 拉出、向西朝 (20,3) 前進偵察",
    "RED-2-rcn 拉出、向西朝 (20,8) 前進偵察（搜索中央敵裝甲徵候）",
    "RED-1-rcn 拉出、向西朝 (20,13) 前進偵察（搜索南翼與補給走廊）",
    "RED-3 續向 (21,3) 戰備推進，不進森林",
    "RED-2 續向 (21,8) 戰備推進，中央支點",
    "RED-1 續向 (21,13) 戰備推進，保持與 RED-2 砲兵協同",
    "RED-AD 向 (20,9) 戰鬥行進，維持在 RED-2 一格內",
    "RED-SF 續向 (15,15) 隱蔽滲透偵察",
]]
BLUE_T1 = [("L2", "BLU-1/2/3 續向 (8,8)/(8,9)/(8,10) 集結，日行夜宿，抵達後挖滿工事固守"),
           ("L2", "全軍行軍姿態：距已偵獲敵軍 >8 格用行軍縱隊、≤8 格改戰備推進"),
           ("L1", "BLU-AD 抵 (7,9) 後原地休整待命，非應變不動，POL≥90%"),
           ("L2", "BLU-SF 沿北帶 T1 前抵 (10,1)，T2/T3 夜休，T4→(16,3)，T5→(20,4) 森林隱蔽"),
           ("L2", "偵察幕 BLU-1-rcn→(12,3)、BLU-AD-rcn→(13,8)、BLU-3-rcn→(12,14) 設觀測所，對敵師級維持≥6格"),
           ("L1", "BLU-2-1-r4、BLU-2-2-r4 抵 (4,10) 後挖滿工事固守（指揮所警衛）"),
           ("L2", "BLU-2 拉出 3-r4 進駐 (4,10) 挖工事固守"),
           ("L2", "BLU-2-rcn 改任後方警戒環 (5,13)→(8,10)→(5,6)→(3,10) 循環巡邏")]

for lvl, txt in RED_T1:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=1)
for lvl, txt in BLUE_T1:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=1)

NEW_RED = {"RED-3": [(21, 3)], "RED-2": [(21, 8)], "RED-1": [(21, 13)],
           "RED-AD": [(20, 9)], "RED-SF": [(15, 15)]}
NEW_RED_DET = {"RED-3-rcn": [(20, 3)], "RED-2-rcn": [(20, 8)], "RED-1-rcn": [(20, 13)]}
NEW_BLUE = {"BLU-SF": [(10, 1)]}
NEW_BLUE_DET = {"BLU-2-rcn": [(5, 13), (8, 10), (5, 6), (3, 10)], "BLU-2-3-r4": [(4, 10)]}
HOLD = set()          # 抵達目標後轉入原地（休整/構工事）

log = []
for gh in range(6, 12):
    fired = command.activate_due_cps(s)
    br = hs.hour_brief(s)
    ev = []
    if gh == 8:       # 紅軍 L1 生效
        for div, code in (("RED-3", "rcn"), ("RED-2", "rcn"), ("RED-1", "rcn")):
            uid, det = orbat.detach(s, div, code, s["units"][div]["pos"])
            det.update({"equip": {"tanks": 0, "guns": 0},
                        "losses": {"personnel": 0, "tanks": 0, "guns": 0},
                        "static_hours": 0, "move_progress": 0.0, "flags": {},
                        "resources": {k: 100 for k in ("POL", "SA", "HE", "AT", "RAT", "MED", "PARTS")}})
            ev.append((uid, f"{uid} 由 {div} 拉出（{det['name']}, 兵 {det['personnel']}）"))
        ROUTES.update(NEW_RED)
        ROUTES.update(NEW_RED_DET)
        HOLD -= set(NEW_RED) | set(NEW_RED_DET)   # ★修正：新命令解除舊目標的原地待命
    if gh == 9:       # 藍軍 L2 生效
        uid, det = orbat.detach(s, "BLU-2", "3-r4", s["units"]["BLU-2"]["pos"])
        det.update({"equip": {"tanks": 0, "guns": 0},
                    "losses": {"personnel": 0, "tanks": 0, "guns": 0},
                    "static_hours": 0, "move_progress": 0.0, "flags": {},
                    "resources": {k: 100 for k in ("POL", "SA", "HE", "AT", "RAT", "MED", "PARTS")}})
        ev.append((uid, f"{uid} 由 BLU-2 拉出（{det['name']}, 兵 {det['personnel']}）"))
        ROUTES.update(NEW_BLUE)
        ROUTES.update(NEW_BLUE_DET)
        HOLD -= set(NEW_BLUE) | set(NEW_BLUE_DET)   # ★同一修正，對稱適用
    for uid in list(ROUTES):
        wps = ROUTES[uid]
        if uid not in s["units"] or not wps or uid in HOLD:
            continue
        tgt = wps[0]
        moved, msg = of.advance(s, uid, tgt)
        if list(s["units"][uid]["pos"]) == list(tgt):
            if len(wps) > 1:
                wps.pop(0)
            else:
                HOLD.add(uid)
                ev.append((uid, f"{uid} 抵達 {tuple(tgt)}，依命令轉入原地（休整／構築工事）"))
        if moved:
            ev.append((uid, msg))
    for uid, u in s["units"].items():
        of.consume(s, uid, "L1" if u["flags"].get("moved") else "L0")
    of.refresh_visibility(s)
    newly = of.spot(s)
    for side, lst in newly.items():
        for uid in lst:
            ev.append((None, f"★{'藍軍' if side=='allies' else '紅軍'}偵獲 {uid} 於 {tuple(s['units'][uid]['pos'])}"))
    of.push_log(s, ev, gh_label=f"[gh{gh}] ")
    summary = f"[gh{gh} {hs.game_time_str(gh)}] " + ("；".join(t for _, t in ev) if ev else "無事件")
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
print("=== 偵獲 ===", "藍:", s["fog_of_war"]["allies_spotted"], "紅:", s["fog_of_war"]["axis_spotted"])
print("\n" + of.ascii_map(s, "god"))
