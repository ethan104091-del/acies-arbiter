#!/usr/bin/env python3
"""Run 6 Tick 3 解算（gh18-23，1944-08-26 00:00-05:00，全程夜間）。

夜間：移動 ×0.5、行軍疲勞 +8/hr、視距縮短（師 2、特戰 3、偵察 3）。

雙方本 tick 的下令（新令一律 +1 級，主指揮所已啟用）：

  藍軍 [L1] BLU-SF 進 (6,4) 森林靜止隱蔽並構築工事，解除尾隨改固守   → gh20 生效
       [L1] BLU-3 續行 (9,14) 抵達即構築工事至有頂蓋               → gh20 生效
       BLU-1 / BLU-2 / BLU-AD 維持既有命令                          → 零延遲

  紅軍 [L1] RED-1/2/3 取消朝 (20,x) 的機動，就地構築工事並完全休整   → gh20 生效
       （未標等級）RED-SF 沿 (18,15)→(16,14)→(16,16)→(18,15) 循環巡邏 → 裁判定為 L2 → gh21 生效
       其餘維持

裁判解讀（已另以《裁判解讀_T3.md》單獨通知紅軍，不對藍軍公開）：

  (甲) 紅軍新令寫「自 gh18 至 gh23」。命令延遲是規則而非選項（手冊 §5），
       主指揮所 +1 級 → L1 於 gh20 生效、L2 於 gh21 生效。gh18-gh19 兩小時內
       RED-1/2/3 仍執行其既有的「向 (20,x) 戰備推進、抵達後原地構築工事」。
       其結果是三個師會在 gh19 抵達 (20,x)，新令於 gh20 生效時「現位置」即為 (20,x)，
       就地構築工事並完全休整——與其意圖一致，只是位置往西一格。

  (乙) RED-SF 那條命令未標 [L1]/[L2]/[L3]。裁判依手冊 §5 之定義，
       將「新設循環巡邏路線」認定為**標準機動 L2**，於 gh21 生效。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 18, f"必須從 gh18 起始，現在 gh={s['global_hour']}"

NEW_ORDERS = [
    ("allies", "L1", "BLU-SF", "進 (6,4) 森林靜止隱蔽並構築工事，解除尾隨、改固守"),
    ("allies", "L1", "BLU-3", "續行 (9,14)，抵達即構築工事至有頂蓋，抵達後不再東進"),
    ("axis", "L1", "RED-1", "取消朝 (20,12) 的機動，就地構築工事並完全休整，不移動不交火"),
    ("axis", "L1", "RED-2", "取消朝 (20,9) 的機動，就地構築工事並完全休整，不移動不交火"),
    ("axis", "L1", "RED-3", "取消朝 (20,3) 的機動，就地構築工事並完全休整，不移動不交火"),
    ("axis", "L2", "RED-SF", "沿 (18,15)→(16,14)→(16,16)→(18,15) 循環巡邏，僅偵察不交戰"),
]
EFF = {}
for side, lvl, uid, txt in NEW_ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    EFF[uid] = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                                extra_delay=extra)["effective_global_hour"]

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
    "RED-2-1-r4": [(29, 8)],
}
PATROL = [(16, 14), (16, 16), (18, 15)]     # RED-SF 的循環巡邏航點（gh21 起）
SHADOW = {"BLU-SF": ("BLU-1", 2)}           # gh20 起 BLU-SF 解除尾隨

# 抵達即築防：uid -> (目的地, 生效 gh；0=常設已生效)
DIG_ON_ARRIVE = {
    "BLU-AD": ((10, 9), 0), "BLU-1": ((9, 4), 0), "BLU-2": ((11, 9), 0),
    "BLU-3": ((9, 14), EFF["BLU-3"]), "BLU-SF": ((6, 4), EFF["BLU-SF"]),
    "RED-AD": ((20, 10), 0), "RED-2-1-r4": ((29, 8), 0),
}
# 紅軍 RED-1/2/3：gh20 起「就地」構築工事（位置由當時決定，故不預先寫死）
RED_HOLD = ("RED-1", "RED-2", "RED-3")

IDX = {}
for uid, route in ROUTE.items():
    u = s["units"].get(uid)
    if not u:
        continue
    hit = [i for i, p in enumerate(route) if list(p) == list(u["pos"])]
    IDX[uid] = hit[0] + 1 if hit else 0
    assert hit or len(route) == 1, f"{uid} 不在其航路上：{tuple(u['pos'])}"

patrol_i = [0]
hold_pos = {}          # RED-1/2/3 於新令生效當下的「現位置」
halted = set()
retreated = set()


def spotted(s, side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def is_big(u):
    return not u.get("is_detachment")


def route_step(s, uid, route):
    u = s["units"][uid]
    i = IDX.get(uid, 0)
    while i < len(route) and list(u["pos"]) == list(route[i]):
        i += 1
    IDX[uid] = i
    return route[i] if i < len(route) else None


def route_advance(s, uid, route):
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


def try_dig(s, uid, ev, note="構築工事"):
    u = s["units"].get(uid)
    if not u or u["flags"].get("moved") or u.get("dig_hours", 0.0) >= 8.0:
        return
    r = ar.dig(s, uid)
    if r:
        ev.append((uid, f"{uid} {note} → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))


def resolve(s, gh):
    ev = []

    # ① 紅軍新令生效：RED-1/2/3 取消機動，記下「現位置」
    if gh >= EFF["RED-1"]:
        for uid in RED_HOLD:
            if uid not in hold_pos:
                hold_pos[uid] = list(s["units"][uid]["pos"])
                halted.add(uid)
                ev.append((uid, f"{uid} 新令生效：取消機動，於現位置 "
                                f"{tuple(hold_pos[uid])} 構築工事並完全休整"))

    # ② 藍軍新令生效：BLU-SF 解除尾隨、改進 (6,4) 森林
    if gh >= EFF["BLU-SF"] and "BLU-SF" in SHADOW:
        SHADOW.pop("BLU-SF")
        ROUTE["BLU-SF"] = [(6, 4)]
        IDX["BLU-SF"] = 0
        ev.append(("BLU-SF", "BLU-SF 新令生效：解除尾隨 BLU-1，改進 (6,4) 森林格"
                             "靜止隱蔽並構築工事"))

    # ③ 應變：紅軍偵察營、RED-SF；藍軍應變 1
    for uid in ("RED-3-rcn", "RED-2-rcn"):
        if uid in halted or uid not in s["units"]:
            continue
        near = [e for e in spotted(s, "axis") if is_big(s["units"][e])]
        if near:
            halted.add(uid)
            ev.append((uid, f"{uid} 依應變停止前推、原地隱蔽觀察（已偵獲 {', '.join(near)}）"))

    u = s["units"].get("RED-SF")
    if u and "RED-SF" not in halted:
        near = [e for e in spotted(s, "axis") if is_big(s["units"][e])]
        if near:
            halted.add("RED-SF")
            ev.append(("RED-SF", f"RED-SF 依應變中止巡邏、就地隱蔽觀測並回報"
                                 f"（已偵獲 {', '.join(near)}），不交戰"))

    for uid in ("BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-SF"):
        u = s["units"].get(uid)
        if not u or uid in retreated:
            continue
        threat = [e for e in spotted(s, "allies")
                  if is_big(s["units"][e]) and ar.dist(s["units"][e]["pos"], u["pos"]) <= 3]
        if threat:
            retreated.add(uid)
            halted.add(uid)
            _, m = ar.advance(s, uid, [max(0, u["pos"][0] - 2), u["pos"][1]])
            ev.append((uid, f"{uid} 依應變 1 向西後撤 2 格"
                            f"（敵 {', '.join(threat)} 已在 3 格內）：{m}"))

    # ④ 沿既有航路續行
    for uid, route in ROUTE.items():
        u = s["units"].get(uid)
        if not u or uid in halted or uid in retreated:
            continue
        for msg in route_advance(s, uid, route):
            ev.append((uid, msg))

    # ⑤ RED-SF 循環巡邏（gh21 起）
    u = s["units"].get("RED-SF")
    if u and "RED-SF" not in halted and gh >= EFF["RED-SF"]:
        tgt = PATROL[patrol_i[0] % len(PATROL)]
        if list(u["pos"]) == list(tgt):
            patrol_i[0] += 1
            tgt = PATROL[patrol_i[0] % len(PATROL)]
        _, m = ar.advance(s, "RED-SF", list(tgt))
        ev.append(("RED-SF", f"{m}（循環巡邏，下一航點 {tuple(tgt)}）"))

    # ⑥ 尾隨（gh20 前仍有效）
    for uid, (lead, back) in list(SHADOW.items()):
        u = s["units"].get(uid)
        if not u or uid in halted or uid in retreated:
            continue
        cur = [i for i, p in enumerate(ROUTE[lead])
               if list(p) == list(s["units"][lead]["pos"])]
        k = cur[0] if cur else 0
        tgt = ROUTE[lead][max(0, k - back)]
        if list(u["pos"]) == list(tgt):
            continue
        _, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, f"{msg}（尾隨 {lead} 後方 {back} 格）"))

    # ⑦ 抵達即築防
    for uid, (pos, eff) in DIG_ON_ARRIVE.items():
        u = s["units"].get(uid)
        if not u or gh < eff or list(u["pos"]) != list(pos):
            continue
        try_dig(s, uid, ev)

    # ⑧ 紅軍 RED-1/2/3：就地構築工事（新令生效後）
    for uid in RED_HOLD:
        if uid in hold_pos:
            try_dig(s, uid, ev, "就地構築工事")

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
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>5} {'工事':>6} {'工時':>5} "
      f"{'暴露':>6} {'能見':>12}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel', 0):6} "
          f"{u.get('fatigue', 0):4} {u.get('org', 0):5} {u.get('fortification', 0):6.2f} "
          f"{u.get('dig_hours', 0):5.1f} {ar.exposure_factor(u, ar.terr(s, u['pos'])):6} "
          f"{u.get('visibility_state', '?'):>12}")
