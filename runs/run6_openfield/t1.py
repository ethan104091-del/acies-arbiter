#!/usr/bin/env python3
"""Run 6 Tick 1 解算（gh6-11，1944-08-25 12:00-17:00，全程白天）。

雙方主指揮所皆於 gh5 啟用 → 新命令延遲降為 +1 級（L1=2hr、L2=3hr）。
依裁示_02（常設命令），兩軍的 T0 命令與應變**全部仍然有效**，本 tick 各自只加一道新令：

  藍軍 [L1] BLU-AD 抵達 (10,9) 後就地構築工事，等 BLU-2 跟上，之前不再東進 → gh8 生效
  紅軍 [L2] RED-2 拉出 1-r4 步兵營進駐主指揮所 (29,8) 並構築工事    → gh9 生效

其餘編隊沿 T0 既有航路繼續行進，不吃任何延遲，自 gh6 起即動。

航路索引以各編隊的**現在位置**初始化（缺陷 18 的修正在跨 tick 時同樣必須成立，
否則 route_step 會從航路起點重新比對而把部隊往回送）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 6, f"必須從 gh6 起始，現在 gh={s['global_hour']}"

# ── 本 tick 的新命令（舊命令為常設，不重下、不計延遲）──────────────────────
NEW_ORDERS = [
    ("allies", "L1", "BLU-AD", "抵達 (10,9) 後就地構築工事，等待 BLU-2 跟上，之前不再東進"),
    ("axis", "L2", "RED-2", "拉出 1-r4 步兵營進駐主指揮所 (29,8) 並構築工事，不得離格"),
]
EFF = {}
for side, lvl, uid, txt in NEW_ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    EFF[uid] = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                                extra_delay=extra)["effective_global_hour"]

# ── T0 既有航路（常設命令，續行）────────────────────────────────────────
ROUTE = {
    "BLU-1":  [(1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 5), (7, 4), (8, 4), (9, 4)],
    "BLU-AD": [(2, 9), (3, 8), (4, 7), (5, 7), (6, 7), (7, 7), (8, 8), (9, 9), (10, 9)],
    "BLU-2":  [(1, 9), (2, 8), (3, 8), (4, 7), (5, 7), (6, 7), (7, 7), (8, 8), (9, 9),
               (10, 9), (11, 9)],
    "BLU-3":  [(1, 14), (2, 14), (3, 14), (4, 14), (5, 14), (6, 14), (7, 14), (8, 14),
               (9, 14)],
    "RED-3":  [(28, 3), (27, 3), (26, 3), (25, 3), (24, 3), (23, 3), (22, 3), (21, 3),
               (20, 3)],
    "RED-2":  [(28, 8), (27, 9), (26, 9), (25, 9), (24, 9), (23, 9), (22, 9), (21, 9),
               (20, 9)],
    "RED-AD": [(27, 8), (26, 9), (25, 9), (24, 9), (23, 9), (22, 10), (21, 10), (20, 10)],
    "RED-1":  [(28, 13), (27, 13), (26, 13), (25, 13), (24, 13), (23, 12), (22, 12),
               (21, 12), (20, 12)],
    "RED-SF": [(27, 15), (26, 15), (25, 15), (24, 15), (23, 15), (22, 15), (21, 15),
               (20, 15), (19, 15), (18, 15)],
    "RED-3-rcn": [(28, 3), (27, 3), (26, 3), (25, 3), (24, 3), (23, 3), (22, 3), (21, 3),
                  (20, 3), (19, 3), (18, 3), (17, 3), (16, 3)],
    "RED-2-rcn": [(28, 8), (27, 9), (26, 9), (25, 9), (24, 9), (23, 8), (22, 8), (21, 8),
                  (20, 8), (19, 8), (18, 8), (17, 8), (16, 8)],
    # 新增：紅軍指揮所守備營。只給終點，由 plan_path 自現位置尋路——
    # 寫死起點會在抽離位置與航路首點不同時造成來回振盪（本 tick 首次解算的腳本瑕疵）。
    "RED-2-1-r4": [(29, 8)],
}
SHADOW = {"BLU-SF": ("BLU-1", 2)}
DIG_ON_ARRIVE = {"BLU-AD": (10, 9), "RED-2-1-r4": (29, 8)}
DIG_ON_ARRIVE_EFF = {"BLU-AD": lambda: EFF["BLU-AD"], "RED-2-1-r4": lambda: EFF["RED-2"]}

# 跨 tick 續行：航路索引以現在位置初始化
IDX = {}
for uid, route in ROUTE.items():
    u = s["units"].get(uid)
    if not u:
        continue
    hit = [i for i, p in enumerate(route) if list(p) == list(u["pos"])]
    IDX[uid] = hit[0] + 1 if hit else 0
    assert hit or uid not in s["units"], f"{uid} 不在其航路上：{tuple(u['pos'])}"

detached = [False]
halted = set()          # 依各自應變「偵獲敵軍即停止前推」
retreated = set()       # 藍軍應變 1：已執行過後撤者本 tick 不重複


def spotted(s, side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def is_big(u):
    """師級或旅級整編隊（非抽離營）。"""
    return not u.get("is_detachment")


def route_step(s, uid, route):
    u = s["units"][uid]
    i = IDX.get(uid, 0)
    while i < len(route) and list(u["pos"]) == list(route[i]):
        i += 1
    IDX[uid] = i
    return route[i] if i < len(route) else None


def route_advance(s, uid, route):
    """本小時沿航路盡量前進（缺陷 20 修正後可安全連呼）。"""
    msgs = []
    for _ in range(4):
        tgt = route_step(s, uid, route)
        if tgt is None:
            break
        _, m = ar.advance(s, uid, list(tgt))
        msgs.append(m)
        u = s["units"][uid]
        if list(u["pos"]) != list(tgt) or u.get("move_progress", 0.0) < 1.0:
            break
    return msgs


def resolve(s, gh):
    ev = []

    # ① 紅軍新令：抽離 1-r4 進駐主指揮所
    if gh >= EFF["RED-2"] and not detached[0]:
        uid, _ = ar.detach_bn(s, "RED-2", "1-r4", list(s["units"]["RED-2"]["pos"]))
        detached[0] = True
        IDX[uid] = 0
        ev.append(("RED-2", f"RED-2 拉出 1-r4 步兵營 → {uid} 於 "
                            f"{tuple(s['units'][uid]['pos'])}，奉命進駐主指揮所 (29,8)"))

    # ② 應變：偵獲敵軍即停止前推（紅軍兩個偵察營、RED-SF 3 格內遇敵則撤）
    for uid in ("RED-3-rcn", "RED-2-rcn"):
        u = s["units"].get(uid)
        if not u or uid in halted:
            continue
        near = [e for e in spotted(s, "axis") if is_big(s["units"][e])]
        if near:
            halted.add(uid)
            ev.append((uid, f"{uid} 依應變停止前推、原地隱蔽觀察（已偵獲 {', '.join(near)}）"))

    # ③ 藍軍應變 1：任一師遭敵師級/旅級進入 3 格以內 → 向西後撤 2 格
    for uid in ("BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-SF"):
        u = s["units"].get(uid)
        if not u or uid in retreated:
            continue
        threat = [e for e in spotted(s, "allies")
                  if is_big(s["units"][e]) and ar.dist(s["units"][e]["pos"], u["pos"]) <= 3]
        if threat:
            retreated.add(uid)
            halted.add(uid)
            dest = [max(0, u["pos"][0] - 2), u["pos"][1]]
            _, m = ar.advance(s, uid, dest)
            ev.append((uid, f"{uid} 依應變 1 向西後撤 2 格（敵 {', '.join(threat)} 已在 3 格內）：{m}"))

    # ④ 沿既有航路續行
    for uid, route in ROUTE.items():
        u = s["units"].get(uid)
        if not u or uid in halted or uid in retreated:
            continue
        if uid == "RED-2-1-r4" and not detached[0]:
            continue
        for msg in route_advance(s, uid, route):
            ev.append((uid, msg))

    # ⑤ 尾隨編隊
    for uid, (lead, back) in SHADOW.items():
        u = s["units"].get(uid)
        if not u or uid in halted or uid in retreated:
            continue
        # 用 lead 的實際現位置在航路上的索引，不用 IDX——IDX 指向「下一個」航點，
        # 且在該小時尚未重新計算時會慢一拍，使尾隨距離多出一格。
        cur = [i for i, p in enumerate(ROUTE[lead])
               if list(p) == list(s["units"][lead]["pos"])]
        k = cur[0] if cur else 0
        tgt = ROUTE[lead][max(0, k - back)]
        if list(u["pos"]) == list(tgt):
            continue
        _, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, f"{msg}（尾隨 {lead} 後方 {back} 格）"))

    # ⑥ 抵達後構築工事（該小時未移動才算得上動土）
    for uid, pos in DIG_ON_ARRIVE.items():
        u = s["units"].get(uid)
        if not u or gh < DIG_ON_ARRIVE_EFF[uid]():
            continue
        if list(u["pos"]) != list(pos) or u["flags"].get("moved"):
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 抵達後構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))

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
    print(f"{side:7} 已偵獲敵編隊：{spotted(s, side) or '（無）'}"
          f"｜指揮所 {command.cp_hexes(s, side)}")
print()
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>5} {'工事':>6} {'暴露':>6}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel', 0):6} "
          f"{u.get('fatigue', 0):4} {u.get('org', 0):5} {u.get('fortification', 0):6.2f} "
          f"{ar.exposure_factor(u, ar.terr(s, u['pos'])):6}")
