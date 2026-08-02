#!/usr/bin/env python3
"""Run 6 Tick 0 解算（gh0-5，1944-08-25 全程白天）。

開局兩軍相距約 26 格，本 tick 不可能接觸。真正的內容是「命令延遲的代價」：
雙方都沒有指揮所 → 一律 +2 級。
  L1（建指揮所）→ 3hr → gh3 下達，再架設 CP_SETUP_HOURS=2 → gh5 才啟用
  L2（機動）    → 4hr → gh4 生效 → 本 tick 只剩 gh4、gh5 兩小時可動

兩軍的開局姿態（雙方互不知情，此處僅為裁判記錄）：
  藍軍 三線平推：北翼 y=4、中線 y=9（裝甲在前）、南翼 y=14；主指揮所 (5,9) 森林格。
       未拉出任何偵察營。
  紅軍 三線推至 x=20 一線後就地構築工事；主指揮所 (29,8) 東緣深遠後方；
       拉出兩個偵察營前出至 x=16 建立觀測幕。

航路一律避開該兵種不可通行的地形；本 tick 所有繞行的切比雪夫距離都與直線相同
（繞行不花額外時間），故不構成對任一方的裁判裁量。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 0, f"必須從 gh0 起始，現在 gh={s['global_hour']}"

# ── 下令：逐編隊依其發令時位置計算延遲（裁示 57）。開局雙方皆無指揮所 → 一律 +2 ──
ORDERS = [
    # 藍軍
    ("allies", "L1", "BLU-AD", "軍長：於 (5,9) 架設主指揮所並進駐"),
    ("allies", "L2", "BLU-1", "沿 y=4 軸線東進至 (9,4)，經 (6,5) 繞過 (6,4) 森林格"),
    ("allies", "L2", "BLU-SF", "隨 BLU-1 行進，保持於其後方兩格，行進間維持最大偵測"),
    ("allies", "L2", "BLU-AD", "經 (3,8)(4,7)(6,7)(8,8) 北繞森林，推進至 (10,9)"),
    ("allies", "L2", "BLU-2", "跟隨 BLU-AD 後方，循同一北繞航路推進至 (11,9)"),
    ("allies", "L2", "BLU-3", "沿 y=14 軸線東進至 (9,14)"),
    # 紅軍
    ("axis", "L1", "RED-2", "軍長：於 (29,8) 建立主指揮所，啟用後進駐，不前推"),
    ("axis", "L2", "RED-SF", "向 (18,15) 隱蔽滲透，搜索南翼；不切補給線、不攻擊"),
    ("axis", "L2", "RED-3", "向 (20,3) 戰備推進，避開森林，抵達後原地構築工事"),
    ("axis", "L2", "RED-2", "向 (20,9) 戰備推進，與 RED-AD 保持相鄰，抵達後構築工事"),
    ("axis", "L2", "RED-1", "向 (20,12) 戰備推進，維持與 RED-2 聯絡，抵達後構築工事"),
    ("axis", "L2", "RED-AD", "經開闊地向 (20,10) 行軍縱隊推進，不入森林，抵達後構築工事"),
    ("axis", "L2", "RED-3-rcn", "RED-3 拉出偵察隊，向 (16,3) 前進偵察，偵獲敵軍即停止前推"),
    ("axis", "L2", "RED-2-rcn", "RED-2 拉出偵察隊，向 (16,8) 前進偵察，偵獲敵主力即停止前推"),
]
EFF = {}
for side, lvl, uid, txt in ORDERS:
    # 偵察營尚未抽離，以母編隊位置計算延遲
    ref = uid if uid in s["units"] else uid.rsplit("-", 1)[0]
    extra = command.delay_tier_adjust(s, side, s["units"][ref]["pos"])
    key = f"{side}:{lvl}:{uid}:{txt[:12]}"
    o = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}", extra_delay=extra)
    EFF[key] = o["effective_global_hour"]

EFF_CP_BLU = EFF[[k for k in EFF if k.startswith("allies:L1")][0]]
EFF_CP_RED = EFF[[k for k in EFF if k.startswith("axis:L1")][0]]
EFF_MOVE = {k.split(":")[2]: v for k, v in EFF.items() if ":L2:" in k}

# ── 航路（全部驗過：不含該兵種不可通行的格；繞行不增加切比雪夫距離）──────────
ROUTE = {
    # 藍軍
    "BLU-1":  [(1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 5), (7, 4), (8, 4), (9, 4)],
    "BLU-AD": [(2, 9), (3, 8), (4, 7), (5, 7), (6, 7), (7, 7), (8, 8), (9, 9), (10, 9)],
    "BLU-2":  [(1, 9), (2, 8), (3, 8), (4, 7), (5, 7), (6, 7), (7, 7), (8, 8), (9, 9),
               (10, 9), (11, 9)],
    "BLU-3":  [(1, 14), (2, 14), (3, 14), (4, 14), (5, 14), (6, 14), (7, 14), (8, 14),
               (9, 14)],
    # 紅軍
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
}
SHADOW = {"BLU-SF": ("BLU-1", 2)}          # 尾隨：跟在誰後方幾格（沿其航路）
DETACH = {"RED-3-rcn": ("RED-3", "rcn"), "RED-2-rcn": ("RED-2", "rcn")}

cp_done = {"allies": False, "axis": False}
detached = set()
IDX = {}                                   # 缺陷 18 的修正：逐編隊記住航路進度


def route_step(s, uid, route):
    """回傳該編隊沿航路的下一個目的地；已到終點回 None。"""
    u = s["units"][uid]
    i = IDX.get(uid, 0)
    while i < len(route) and list(u["pos"]) == list(route[i]):
        i += 1
    IDX[uid] = i
    return route[i] if i < len(route) else None


def route_advance(s, uid, route):
    """本小時沿航路盡量前進：抵達航點後若移動進度仍 ≥1.0 就續走下一航點。

    航點是逐格相鄰的，而 advance() 一次只走到給定目標為止。若不在此處續走，
    速度 >1.0 格/hr 的兵種（偵察營 1.5）會被硬卡成 1 格/hr——這是 Run 6 T0
    首次解算時的腳本瑕疵。疲勞不會重複計算（缺陷 20 已在引擎端修正）。
    """
    msgs = []
    for _ in range(4):                        # 一小時最多 4 格，純防呆
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

    # ① 指揮所：命令生效時才「下令架設」，再過 CP_SETUP_HOURS 小時由 run_tick 啟用
    for side, eff, pos in (("allies", EFF_CP_BLU, (5, 9)), ("axis", EFF_CP_RED, (29, 8))):
        if gh >= eff and not cp_done[side]:
            a = command.establish_cp(s, side, "main", pos)
            cp_done[side] = True
            ev.append((side, f"主指揮所開始架設於 {tuple(pos)}，{a - gh} 小時後啟用（gh{a}）"))

    # ② 抽離偵察營
    for uid, (parent, code) in DETACH.items():
        if uid in detached or gh < EFF_MOVE.get(uid, 99):
            continue
        new_uid, _ = ar.detach_bn(s, parent, code, list(s["units"][parent]["pos"]))
        detached.add(uid)
        assert new_uid == uid, f"抽離代號不符：{new_uid} != {uid}"
        ev.append((parent, f"{parent} 拉出偵察營 → {uid} 於 {tuple(s['units'][uid]['pos'])}"))

    # ③ 沿航路行進
    for uid, route in ROUTE.items():
        u = s["units"].get(uid)
        if not u or gh < EFF_MOVE.get(uid, 99):
            continue
        for msg in route_advance(s, uid, route):
            ev.append((uid, msg))

    # ④ 尾隨編隊：目標為被跟隨者航路上「後方 N 格」的那一點
    for uid, (lead, back) in SHADOW.items():
        u = s["units"].get(uid)
        if not u or gh < EFF_MOVE.get(uid, 99):
            continue
        k = max(0, IDX.get(lead, 0) - 1)      # IDX 指向「下一個」航點，現位置索引為 IDX-1
        tgt = ROUTE[lead][max(0, k - back)]
        if list(u["pos"]) == list(tgt):
            continue
        _, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, f"{msg}（尾隨 {lead} 後方 {back} 格）"))

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
    fo = s.get("fog_of_war", {}).get(f"{side}_spotted", [])
    print(f"{side:7} 已偵獲敵編隊：{fo or '（無）'}")
    print(f"{'':7} 指揮所：{command.cp_hexes(s, side) or '（無）'}")
print()
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>5} {'工事':>6} {'暴露':>6}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel', 0):6} "
          f"{u.get('fatigue', 0):4} {u.get('org', 0):5} {u.get('fortification', 0):6.2f} "
          f"{ar.exposure_factor(u, ar.terr(s, u['pos'])):6}")
