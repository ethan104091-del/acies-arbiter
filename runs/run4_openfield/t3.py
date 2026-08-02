#!/usr/bin/env python3
"""Tick 3 解算（gh18-23, 1944-08-26 00:00-06:00，全程夜間／gh23 黎明）。

延遲：紅軍有前進指揮所 (22,8)，RED-2 在其 6 格內 → 基準；L1 → gh19 生效。
     藍軍僅主指揮所 → +1；L1 → gh19、L2 → gh21 生效。
藍軍 T2 常態令：本 tick 夜行 4hr（gh18-21）＋ 休整 2hr（gh22-23）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, orbat, hourstate as hs, command

s = of.load()
ROUTES = {k: [tuple(p) for p in v] for k, v in s.get("standing_routes", {}).items()}

for lvl, txt in [("L1", "RED-2 拉出 1-r4 至 (22,8) 固守前進指揮所並構築簡易防禦；RED-2 本隊留 (22,7) 戰備休整")]:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=0)      # 前進指揮所罩內 → 基準
for lvl, txt in [("L2", "BLU-AD 拉出 eng 同格進駐 (14,10)：第四兵種＋以×1.5 速度構工事，不得單獨脫離"),
                 ("L2", "三個步兵師 eng 留師內，抵達後以×1.5 速度挖滿工事轉固守"),
                 ("L2", "條件令：主力抵 x=15 線且 (14,10) 工事挖滿後，於 (14,10) 架前進指揮所、軍長進駐；敵近 3 格內則取消"),
                 ("L1", "射擊紀律：只打敵師級編隊／站上我補給走廊的敵單位／已確認敵指揮所"),
                 ("L2", "BLU-SF 紀律補充：目標有護衛則不突襲，改坐死補給走廊觀測；並自我約束不進入洩漏座標及其相鄰 8 格")]:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=1)

BLUE_MARCH_HOURS = (18, 19, 20, 21)          # 夜行 4hr，之後休整
INF_NIGHT_CAP = True                          # 藍軍「寧慢不脫節」：裝甲師配合步兵速度
HOLD = set()
log = []

for gh in range(18, 24):
    fired = command.activate_due_cps(s)
    br = hs.hour_brief(s)
    ev = []
    for side, kind, pos in fired:
        ev.append((side, f"我方{kind}指揮所於 {tuple(pos)} 架設完成、軍長進駐"))
    if gh == 19:      # 紅軍守備營拉出
        uid, det = orbat.detach(s, "RED-2", "1-r4", s["units"]["RED-2"]["pos"])
        det.update({"equip": {"tanks": 0, "guns": 0},
                    "losses": {"personnel": 0, "tanks": 0, "guns": 0},
                    "static_hours": 0, "move_progress": 0.0, "flags": {},
                    "resources": {k: 100 for k in ("POL", "SA", "HE", "AT", "RAT", "MED", "PARTS")}})
        ev.append((uid, f"{uid} 由 RED-2 拉出（{det['name']}, 兵 {det['personnel']}）→ 前往 (22,8) 固守指揮所"))
        ROUTES["RED-2-1-r4"] = [(22, 8)]
    if gh == 21:      # 藍軍 L2 生效：拉出裝甲工兵營
        uid, det = orbat.detach(s, "BLU-AD", "eng", s["units"]["BLU-AD"]["pos"])
        det.update({"equip": {"tanks": 0, "guns": 0},
                    "losses": {"personnel": 0, "tanks": 0, "guns": 0},
                    "static_hours": 0, "move_progress": 0.0, "flags": {},
                    "resources": {k: 100 for k in ("POL", "SA", "HE", "AT", "RAT", "MED", "PARTS")}})
        ev.append((uid, f"{uid} 由 BLU-AD 拉出（{det['name']}, 兵 {det['personnel']}）→ 隨裝甲師同行、第四兵種"))
        ROUTES["BLU-AD-eng"] = [(14, 10)]
    for uid in list(ROUTES):
        wps = ROUTES[uid]
        if uid not in s["units"] or not wps or uid in HOLD:
            continue
        u = s["units"][uid]
        if u["side"] == "allies" and gh not in BLUE_MARCH_HOURS:
            continue                     # 藍軍夜行 4hr 之後休整
        # 藍軍「寧慢不脫節」：裝甲師與其工兵營以步兵速度前進
        cap = None
        if INF_NIGHT_CAP and uid in ("BLU-AD", "BLU-AD-eng"):
            cap = of.RATE["infantry"]["."] * 0.5
        tgt = wps[0]
        before = list(u["pos"])
        if cap is not None:
            saved = of.RATE[u["type"]]["."]
            of.RATE[u["type"]]["."] = of.RATE["infantry"]["."]      # 暫時降速
            moved, msg = of.advance(s, uid, tgt)
            of.RATE[u["type"]]["."] = saved
        else:
            moved, msg = of.advance(s, uid, tgt)
        if list(u["pos"]) == list(tgt):
            if len(wps) > 1:
                wps.pop(0)
            else:
                HOLD.add(uid)
                ev.append((uid, f"{uid} 抵達 {tuple(tgt)}，依命令轉入原地"))
        if moved:
            ev.append((uid, msg))
    for uid, u in s["units"].items():
        if u["flags"].get("moved"):
            of.consume(s, uid, "L1")
        else:
            of.consume(s, uid, "L0")
            rest = 10 if u["side"] == "allies" else 3
            u["fatigue"] = max(0, u.get("fatigue", 0) - rest)
    of.refresh_visibility(s)
    newly = of.spot(s)
    # ── 應變條件檢查（依雙方書面條件逐條檢查，裁判不放寬也不收緊）──
    # 紅軍應變：「若 RED-SF 偵獲敵軍接近至 3 格內，則向南方或東方脫離一格並保持隱蔽，不交戰」
    sf = s["units"].get("RED-SF")
    if sf and "RED-SF" not in HOLD:
        near = [u for u in s["units"].values() if u["side"] == "allies"
                and of.dist(u["pos"], sf["pos"]) <= 3]
        if near and ROUTES.get("RED-SF") != [(sf["pos"][0], min(17, sf["pos"][1] + 1))]:
            esc = (sf["pos"][0], sf["pos"][1] + 1)          # 命令寫「南方或東方」→ 取先列的南方
            if esc[1] > 17 or of.RATE["ranger"].get(of.terr(s, esc), 0) == 0:
                esc = (sf["pos"][0] + 1, sf["pos"][1])      # 南方不可行 → 東方
            ROUTES["RED-SF"] = [esc]
            HOLD.discard("RED-SF")
            ev.append(("axis", f"★應變觸發：RED-SF 偵獲敵軍於 {of.dist(near[0]['pos'], sf['pos'])} 格內 → 依命令向南脫離至 {esc}，不交戰"))
    # 藍軍現行應變 4：「偵察營遭敵砲擊，或敵**裝甲**進到 3 格內 → 後撤」
    # → RED-SF 非裝甲、無砲擊 → 不觸發，BLU-3-rcn 依命令留在觀測所保持接觸。
    for side, lst in newly.items():
        for uid in lst:
            ev.append((side, f"★我方偵獲敵 {uid} 於 {tuple(s['units'][uid]['pos'])}"))
    of.push_log(s, ev, gh_label=f"[gh{gh}] ")
    summary = f"[gh{gh} {hs.game_time_str(gh)} {hs.daynight(gh)}] " + ("；".join(t for _, t in ev) if ev else "雙方無動作")
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
print("=== 紅軍指揮所 ===", of.cp_garrison(s, "axis"))
print("=== 藍軍指揮所 ===", of.cp_garrison(s, "allies"))
print("=== 偵獲 ===", "藍:", s["fog_of_war"]["allies_spotted"], "紅:", s["fog_of_war"]["axis_spotted"])
print("\n" + of.ascii_map(s, "god"))
