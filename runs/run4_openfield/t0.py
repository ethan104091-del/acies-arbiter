#!/usr/bin/env python3
"""Tick 0 解算 — 依雙方 Tick 0 命令逐小時執行。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, orbat, hourstate as hs, command

s = of.load()

# ── 1. 命令入佇列（雙方開局皆無指揮所 → extra_delay=2）────────────
RED_ORDERS = [
    ("L1", "RED-3 向西朝 (25,3) 戰備推進，保持與 RED-2 聯絡，不進入森林"),
    ("L1", "RED-2 向西朝 (25,8) 戰備推進，作為中央屏衛"),
    ("L1", "RED-1 向西朝 (25,13) 戰備推進，保持南翼隊形"),
    ("L1", "RED-AD 向西朝 (24,8) 行軍縱隊推進；遇敵即轉戰鬥行進"),
    ("L1", "RED-SF 向西朝 (23,15) 隱蔽滲透偵察，搜索 (20,14)-(15,14) 敵補給走廊徵候"),
]
BLUE_ORDERS = [
    ("L1", "BLU-2 拉出 1-r4、2-r4 兩個步兵營進駐 (4,10) 固守並構築工事（指揮所警衛）"),
    ("L1", "拉出 BLU-1/BLU-AD/BLU-3/BLU-2 四個偵察營展開偵察幕，只觀測不接戰"),
    ("L2", "BLU-1 行軍縱隊 (1,4)→(4,6)→(8,8)，日行夜宿，抵達後構築工事固守"),
    ("L2", "BLU-2 行軍縱隊 (1,9)→(3,8)→(6,8)→(8,9)，抵達後構築工事固守"),
    ("L2", "BLU-3 行軍縱隊 (1,14)→(5,12)→(8,10)，抵達後構築工事固守"),
    ("L2", "BLU-AD 沿 y=8 東進至 (7,9) 戰備待命；節油令每 tick 行軍≤4hr、POL≥70%"),
    ("L2", "BLU-SF 北緣滲透 (2,2)→(8,1)→(16,1)→(22,2)，T5 前抵 (23,4) 待機"),
]
for lvl, txt in RED_ORDERS:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=2)
for lvl, txt in BLUE_ORDERS:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=2)

# ── 2. 指揮所（裁示：架設令不吃通訊延遲，只吃 2hr 架設）──────────
command.establish_cp(s, "axis", "main", (29, 8))
command.establish_cp(s, "allies", "main", (4, 10))

# ── 3. 路線表（waypoint）──────────────────────────────────────────
ROUTES = {
    "RED-3":  [(25, 3)],
    "RED-2":  [(25, 8)],
    "RED-1":  [(25, 13)],
    "RED-AD": [(24, 9)],            # 裁量：原目標 (24,8) 為森林、戰車不可入 → 繞南緊鄰格
    "RED-SF": [(23, 15)],
    "BLU-1":  [(4, 6), (8, 8)],
    "BLU-2":  [(3, 8), (6, 8), (8, 9)],
    "BLU-3":  [(5, 12), (8, 10)],
    "BLU-AD": [(5, 8), (7, 9)],
    "BLU-SF": [(8, 1), (16, 1), (22, 2)],
}
DET_ROUTES = {
    "BLU-1-rcn":  [(6, 3), (12, 3)],
    "BLU-AD-rcn": [(7, 8), (13, 8)],
    "BLU-3-rcn":  [(6, 14), (12, 14)],
    "BLU-2-rcn":  [(3, 5), (3, 9), (3, 13), (6, 13), (6, 5)],
    "BLU-2-1-r4": [(4, 10)],
    "BLU-2-2-r4": [(4, 10)],
}

log = []
for gh in range(6):
    fired = command.activate_due_cps(s)
    br = hs.hour_brief(s)
    ev = []
    for side, kind, pos in fired:
        ev.append(f"{side} {kind} 指揮所於 {tuple(pos)} 架設完成、軍長進駐")
    # 命令生效時點：紅軍全 L1(+2)=gh3；藍軍 L1=gh3、L2=gh4
    if gh == 3:
        for div, code in (("BLU-1", "rcn"), ("BLU-AD", "rcn"), ("BLU-3", "rcn"),
                          ("BLU-2", "rcn"), ("BLU-2", "1-r4"), ("BLU-2", "2-r4")):
            uid, det = orbat.detach(s, div, code, s["units"][div]["pos"])
            det.setdefault("equip", {"tanks": 0, "guns": 0})
            det.setdefault("losses", {"personnel": 0, "tanks": 0, "guns": 0})
            det.setdefault("static_hours", 0); det.setdefault("move_progress", 0.0)
            det.setdefault("flags", {}); det.setdefault("resources", dict(of.load.__defaults__ and {} or {}))
            det["resources"] = {k: 100 for k in ("POL", "SA", "HE", "AT", "RAT", "MED", "PARTS")}
            ev.append(f"{uid} 由 {div} 拉出（{det['name']}, 兵 {det['personnel']}）")
    active = [o["text"] for o in br["active_orders"]]
    for uid, wps in list(ROUTES.items()) + list(DET_ROUTES.items()):
        if uid not in s["units"] or not wps:
            continue
        u = s["units"][uid]
        side = u["side"]
        # 生效判定
        if uid.startswith("RED"):
            ok = gh >= 3
        elif uid in DET_ROUTES:
            ok = gh >= 3
        else:
            ok = gh >= 4
        if not ok:
            continue
        tgt = wps[0]
        moved, msg = of.advance(s, uid, tgt)
        if list(u["pos"]) == list(tgt) and len(wps) > 1:
            wps.pop(0)
        if moved:
            ev.append(msg)
    for uid, u in s["units"].items():
        of.consume(s, uid, "L1" if u["flags"].get("moved") else "L0")
    of.refresh_visibility(s)
    newly = of.spot(s)
    if any(newly.values()):
        ev.append(f"★偵獲: {newly}")
    summary = f"[gh{gh} {hs.game_time_str(gh)}] " + ("；".join(ev) if ev else "雙方無動作（命令延遲中）")
    log.append(summary)
    of.clear_flags(s)
    hs.end_hour(s, summary)

# ── tick 結束：補給 + 勝負檢查 ──────────────────────────────────
sup = of.resupply(s)
dec = command.decapitation(s)
of.save(s)
print("\n".join(log))
print("\n=== 補給狀態 ===", sup)
print("=== 斬首檢查 ===", dec)
print("\n" + of.ascii_map(s, "god"))
for side in ("allies", "axis"):
    print(f"\n--- {side} ---")
    print(of.unit_lines(s, side))
