#!/usr/bin/env python3
"""Run 6 Tick 4 解算（gh24-29，1944-08-26 06:00-11:00，全程白天）。

白天：移動全速、行軍疲勞 +5/hr、視距恢復（師 3、特戰 4、偵察 5）。

  藍軍 明示維持 T0～T3 全部命令與應變，本 tick 不下新令 → 零延遲。
       BLU-2 續行 (11,9) 抵達即築防；BLU-1/BLU-3/BLU-SF 續築；BLU-AD 工事已滿改完全休整。

  紅軍 [L1] RED-1/2/3 留在 (21,12)(21,9)(21,3) 續築至有頂蓋並完全休整，
            不得機動或主動交火，僅遭直接攻擊時自衛                      → gh26
       [L1] RED-AD 留 (20,10) 有頂蓋工事內完全休整，作中央機動預備隊     → gh26
       [L1] RED-2-1-r4 固守 (29,8) 續築至有頂蓋後完全休整                → gh26
       [L2] RED-2-rcn 自 (16,8) 沿 (13,8)→(10,8)→(13,8) 循環偵察         → gh27
       [L2] RED-3-rcn 自 (16,3) 沿 (13,3)→(10,3)→(13,3) 循環偵察         → gh27
       [L2] RED-SF 取消既有巡邏，改沿 (15,14)→(12,14)→(12,16)→(15,16) 循環 → gh27

裁判就紅軍「是否開火」的認定（已另以《裁判解讀_T4.md》通知紅軍）：
  紅軍 T0 之應變 4 曾授權 RED-1/2/3 對已偵獲目標實施砲兵壓制。但其 T4 命令 1、2
  明文「不得機動或主動交火，僅在遭受直接攻擊時就地自衛」，且 T4 應變 1 明文
  「主力與裝甲師在未接獲新命令前繼續固守」。依裁示_02，新命令取代其所涵蓋的舊命令，
  故 T0 應變 4 之砲擊授權於本 tick **已被自己的新命令撤銷**。紅軍本 tick 不主動開火。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 24, f"必須從 gh24 起始，現在 gh={s['global_hour']}"

NEW_ORDERS = [
    ("axis", "L1", "RED-1", "留 (21,12) 續築至有頂蓋並完全休整，不機動不主動交火"),
    ("axis", "L1", "RED-2", "留 (21,9) 續築至有頂蓋並完全休整，不機動不主動交火"),
    ("axis", "L1", "RED-3", "留 (21,3) 續築至有頂蓋並完全休整，不機動不主動交火"),
    ("axis", "L1", "RED-AD", "留 (20,10) 有頂蓋工事內完全休整，作中央機動預備隊"),
    ("axis", "L1", "RED-2-1-r4", "固守 (29,8)，續築至有頂蓋後完全休整"),
    ("axis", "L2", "RED-2-rcn", "沿 (13,8)→(10,8)→(13,8) 循環偵察，觀測不交戰"),
    ("axis", "L2", "RED-3-rcn", "沿 (13,3)→(10,3)→(13,3) 循環偵察，觀測不交戰"),
    ("axis", "L2", "RED-SF", "取消既有巡邏，改沿 (15,14)→(12,14)→(12,16)→(15,16) 循環搜索"),
]
EFF = {}
for side, lvl, uid, txt in NEW_ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    EFF[uid] = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                                extra_delay=extra)["effective_global_hour"]

BLU2_ROUTE = [(9, 9), (10, 9), (11, 9)]
PATROL_OLD_SF = [(16, 14), (16, 16), (18, 15)]
PATROL_NEW_SF = [(15, 14), (12, 14), (12, 16), (15, 16)]
PATROL_R2 = [(13, 8), (10, 8), (13, 8), (16, 8)]
PATROL_R3 = [(13, 3), (10, 3), (13, 3), (16, 3)]

# 靜止構築工事者（含已達 8hr 者——try_dig 會自動跳過，改由管線給完全休整）
DIG_HOLD = ["BLU-1", "BLU-3", "BLU-SF", "BLU-AD",
            "RED-1", "RED-2", "RED-3", "RED-AD", "RED-2-1-r4"]

idx = {"BLU-2": 0, "RED-SF": 0, "RED-2-rcn": 0, "RED-3-rcn": 0}
halted = set()
retreated = set()
sf_switched = [False]


def spotted(s, side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def is_big(u):
    return not u.get("is_detachment")


def cycle_move(s, uid, ring, ev, note):
    """沿環狀航點巡邏一小時。"""
    u = s["units"][uid]
    t = ring[idx[uid] % len(ring)]
    if list(u["pos"]) == list(t):
        idx[uid] += 1
        t = ring[idx[uid] % len(ring)]
    _, m = ar.advance(s, uid, list(t))
    ev.append((uid, f"{m}（{note}，下一航點 {tuple(t)}）"))


def try_dig(s, uid, ev):
    u = s["units"].get(uid)
    if not u or u["flags"].get("moved") or u.get("dig_hours", 0.0) >= 8.0:
        return
    r = ar.dig(s, uid)
    if r:
        ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))


def resolve(s, gh):
    ev = []

    # ① 藍軍應變 1（敵師級/旅級入 3 格 → 向西後撤 2 格）
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

    # ② BLU-2 續行 (11,9)
    u = s["units"].get("BLU-2")
    if u and "BLU-2" not in halted and "BLU-2" not in retreated:
        if list(u["pos"]) != [11, 9]:
            _, m = ar.advance(s, "BLU-2", [11, 9])
            ev.append(("BLU-2", m))

    # ③ 紅軍偵察營巡邏（gh27 起；在此之前它們已抵達 (16,x) 靜止）
    for uid, ring in (("RED-2-rcn", PATROL_R2), ("RED-3-rcn", PATROL_R3)):
        if uid in halted or gh < EFF[uid]:
            continue
        cycle_move(s, uid, ring, ev, "循環偵察")

    # ④ RED-SF：gh27 前續行舊巡邏，gh27 起改新環
    u = s["units"].get("RED-SF")
    if u and "RED-SF" not in halted:
        if gh >= EFF["RED-SF"] and not sf_switched[0]:
            sf_switched[0] = True
            idx["RED-SF"] = 0
            ev.append(("RED-SF", "RED-SF 新令生效：取消既有循環巡邏，改行新巡邏環"))
        ring = PATROL_NEW_SF if sf_switched[0] else PATROL_OLD_SF
        cycle_move(s, "RED-SF", ring, ev, "循環搜索南翼")

    # ⑤ 靜止構築工事（該小時未移動者；已達 8hr 者由管線自動給完全休整）
    for uid in DIG_HOLD:
        try_dig(s, uid, ev)
    if s["units"]["BLU-2"]["flags"].get("moved") is not True \
            and list(s["units"]["BLU-2"]["pos"]) == [11, 9]:
        try_dig(s, "BLU-2", ev)

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
