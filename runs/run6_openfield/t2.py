#!/usr/bin/env python3
"""Run 6 Tick 2 解算（gh12-17，1944-08-25 18:00-23:00）。

gh12 黃昏（引擎判定仍為白天），gh13-17 夜間 → 移動 ×0.5、行軍疲勞 +8/hr、視距縮短。

雙方本 tick 的下令情形：
  藍軍 [L1]（gh14 生效）BLU-1/2/3 抵達目的地即構築工事至有頂蓋、抵達後不再東進；
                        BLU-SF 於 BLU-1 停止築防時同步就地構築工事。其餘維持。
  紅軍 明示「維持 T0/T1 全部既有命令與應變，本 tick 不下新令」→ 零延遲，全數續行。

裁判對紅軍 RED-SF 之解讀（記入本檔備查）：
  其 T0 命令為「向 (18,15) 隱蔽滲透，搜索南翼 x=20~15、y=13~16 的敵軍活動與補給走廊
  徵候；未經再次命令不得切斷補給線或攻擊」。抵達 (18,15) 後「搜索」未指定巡邏路線，
  裁判採**最小解讀**：於 (18,15) 就地隱蔽觀測該區域，不再自行移動。
  理由是該命令同時載明「未經再次命令不得…」，顯示其意在克制而非擴張活動半徑；
  且自訂巡邏路線等同裁判代為下令。此解讀於本檔公開，如紅軍認為有誤可於下一 tick 明令更正。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 12, f"必須從 gh12 起始，現在 gh={s['global_hour']}"

NEW_ORDERS = [
    ("allies", "L1", "BLU-1", "抵達 (9,4) 即就地構築工事至有頂蓋，抵達後不再東進"),
    ("allies", "L1", "BLU-2", "抵達 (11,9) 即就地構築工事至有頂蓋，抵達後不再東進"),
    ("allies", "L1", "BLU-3", "抵達 (9,14) 即就地構築工事至有頂蓋，抵達後不再東進"),
    ("allies", "L1", "BLU-SF", "BLU-1 停止並築防時，於其後方兩格就地構築工事並維持隱蔽"),
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
SHADOW = {"BLU-SF": ("BLU-1", 2)}
# 抵達即築防：uid -> (目的地, 命令生效 gh)。0 表示常設命令、已生效。
DIG_ON_ARRIVE = {
    "BLU-AD": ((10, 9), 0), "BLU-1": ((9, 4), None), "BLU-2": ((11, 9), None),
    "BLU-3": ((9, 14), None),
    "RED-AD": ((20, 10), 0), "RED-1": ((20, 12), 0), "RED-2": ((20, 9), 0),
    "RED-3": ((20, 3), 0), "RED-2-1-r4": ((29, 8), 0),
}
for k in ("BLU-1", "BLU-2", "BLU-3"):
    DIG_ON_ARRIVE[k] = (DIG_ON_ARRIVE[k][0], EFF[k])

IDX = {}
for uid, route in ROUTE.items():
    u = s["units"].get(uid)
    if not u:
        continue
    hit = [i for i, p in enumerate(route) if list(p) == list(u["pos"])]
    IDX[uid] = hit[0] + 1 if hit else 0
    # 單點航路（只給終點、由 plan_path 尋路者）本來就不會命中，屬正常
    assert hit or len(route) == 1, f"{uid} 不在其航路上：{tuple(u['pos'])}"

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


def resolve(s, gh):
    ev = []

    # ① 紅軍應變：偵察營偵獲敵戰鬥編隊即停止前推、原地隱蔽觀察
    for uid in ("RED-3-rcn", "RED-2-rcn"):
        if uid in halted or uid not in s["units"]:
            continue
        near = [e for e in spotted(s, "axis") if is_big(s["units"][e])]
        if near:
            halted.add(uid)
            ev.append((uid, f"{uid} 依應變停止前推、原地隱蔽觀察（已偵獲 {', '.join(near)}）"))

    # ② 紅軍應變：RED-SF 偵獲敵戰鬥編隊於 3 格內 → 向 (20,17) 隱蔽撤離，不交戰
    u = s["units"].get("RED-SF")
    if u and "RED-SF" not in retreated:
        near = [e for e in spotted(s, "axis")
                if is_big(s["units"][e]) and ar.dist(s["units"][e]["pos"], u["pos"]) <= 3]
        if near:
            retreated.add("RED-SF")
            halted.add("RED-SF")
            _, m = ar.advance(s, "RED-SF", [20, 17])
            ev.append(("RED-SF", f"RED-SF 依應變向 (20,17) 隱蔽撤離、不交戰"
                                 f"（3 格內 {', '.join(near)}）：{m}"))

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

    # ⑤ 尾隨編隊（BLU-1 已停止築防時，尾隨目標即為其後方兩格 → 自然停住）
    for uid, (lead, back) in SHADOW.items():
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

    # ⑥ 抵達即築防（該小時未移動才算動土；工事上限 8hr 有頂蓋）
    for uid, (pos, eff) in DIG_ON_ARRIVE.items():
        u = s["units"].get(uid)
        if not u or (eff is not None and gh < eff):
            continue
        if list(u["pos"]) != list(pos) or u["flags"].get("moved"):
            continue
        if u.get("dig_hours", 0.0) >= 8.0:
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))

    # ⑦ BLU-SF：BLU-1 已停止築防時，本旅亦就地構築工事
    sf = s["units"].get("BLU-SF")
    b1 = s["units"].get("BLU-1")
    if (sf and b1 and gh >= EFF["BLU-SF"] and list(b1["pos"]) == [9, 4]
            and not sf["flags"].get("moved") and sf.get("dig_hours", 0.0) < 8.0):
        r = ar.dig(s, "BLU-SF")
        if r:
            ev.append(("BLU-SF", f"BLU-SF 隨 BLU-1 停止而就地構築工事 → {r[0]}"
                                 f"（{sf['dig_hours']:.2f}hr，暴露 {r[2]}）"))

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
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>5} {'工事':>6} {'工時':>5} {'暴露':>6}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel', 0):6} "
          f"{u.get('fatigue', 0):4} {u.get('org', 0):5} {u.get('fortification', 0):6.2f} "
          f"{u.get('dig_hours', 0):5.1f} {ar.exposure_factor(u, ar.terr(s, u['pos'])):6}")
