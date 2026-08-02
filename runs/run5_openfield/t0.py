#!/usr/bin/env python3
"""Run 5 Tick 0 解算（gh0-5，1944-08-25 06:00-12:00，白天）。

雙方開局皆無指揮所 → 命令延遲 +2 級。L1 → gh3 生效、L2 → gh4 生效。
指揮所本身還要架設 CP_SETUP_HOURS=2 小時，故兩方主指揮所皆於 gh5 啟用。

裁判的裁示以資料表達（下方 RED_PLAN / BLUE_PLAN），resolve() 只負責執行。
這樣「我對命令的解讀」是可讀、可重播、可被指摘的，而不是散在一堆 if 裡。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402
import orbat                  # noqa: E402

s = ar.load()
assert s["global_hour"] == 0 and s["tick"] == 0, f"必須從 T0 起始，現在 gh={s['global_hour']}"

# ── 下令（extra_delay 依指揮所階梯；開局皆無指揮所 → +2）─────────────
RED_ORDERS = [
    ("L1", "軍長：於 (29,8) 建立主指揮所，完成後進駐並保持；不前推"),
    ("L2", "RED-3 向 (23,3) 戰備推進，避開森林；未接敵前不主動攻擊"),
    ("L2", "RED-2 經 (27,9) 向 (24,9) 戰備推進，保持可與 RED-AD 協同"),
    ("L2", "RED-1 向 (23,12) 戰備推進，保持南翼與中央聯絡"),
    ("L2", "RED-AD 經 (26,9)、(25,10) 向 (23,10) 行軍縱隊；不入森林；不脫離 RED-2 支援"),
    ("L2", "RED-SF 向 (20,15) 隱蔽滲透偵察，搜索 x=20→15 / y=13→15"),
    ("L2", "RED-3 拉出偵察隊向 (20,3) 前進偵察，遇敵原地隱蔽觀察"),
    ("L2", "RED-2 拉出偵察隊向 (20,8) 前進偵察，遇敵原地隱蔽觀察"),
]
BLUE_ORDERS = [
    ("L1", "建立主指揮所於 (4,10) 森林格，軍長架設完成後進駐"),
    ("L1", "BLU-2 拉出 1 步兵營進駐 (4,10) 擔任指揮所守備，抵達後構築工事至有頂蓋"),
    ("L2", "BLU-1 經 (4,6) 推進至 (7,8)，抵達後構築工事至有頂蓋；拉出偵察營前推 (11,5)"),
    ("L2", "BLU-2 推進至 (7,9)，抵達後構築工事至有頂蓋"),
    ("L2", "BLU-3 經 (4,12) 推進至 (7,10)，抵達後構築工事至有頂蓋；拉出偵察營前推 (11,13)"),
    ("L2", "BLU-AD 推進至 (6,9) 任中央預備隊，抵達後停止機動節油並構築工事（含戰車掩壕）"),
    ("L1", "BLU-SF 沿北緣 y=1 隱蔽東進，航路 (12,1)→(20,1)→(24,4)→(25,7)/(24,8) 搜索接觸"),
]
for side, orders in (("axis", RED_ORDERS), ("allies", BLUE_ORDERS)):
    for lvl, txt in orders:
        # 開局雙方皆無指揮所，階梯調整對雙方相同：+2
        hs.enqueue_order(s, side, lvl, txt, extra_delay=2)

# ── 裁判對命令的解讀，以資料表達 ───────────────────────────────────
# eff：該命令生效的 global_hour（L1=gh3、L2=gh4，已含 +2 階梯）
# route：航路點清單，依序推進；到達最後一點後若 dig=True 則開始構築工事
MOVE = {
    # 紅軍
    "RED-3":  dict(side="axis",   eff=4, route=[(23, 3)],            posture="戰備推進", dig=False),
    "RED-2":  dict(side="axis",   eff=4, route=[(27, 9), (24, 9)],   posture="戰備推進", dig=False),
    "RED-1":  dict(side="axis",   eff=4, route=[(23, 12)],           posture="戰備推進", dig=False),
    "RED-AD": dict(side="axis",   eff=4, route=[(26, 9), (25, 10), (23, 10)],
                   posture="行軍縱隊", dig=False),
    "RED-SF": dict(side="axis",   eff=4, route=[(20, 15)],           posture="隱蔽滲透", dig=False),
    # 藍軍
    "BLU-1":  dict(side="allies", eff=4, route=[(4, 6), (7, 8)],     posture="行軍縱隊→戰備", dig=True),
    "BLU-2":  dict(side="allies", eff=4, route=[(7, 9)],             posture="行軍縱隊→戰備", dig=True),
    "BLU-3":  dict(side="allies", eff=4, route=[(4, 12), (7, 10)],   posture="行軍縱隊→戰備", dig=True),
    "BLU-AD": dict(side="allies", eff=4, route=[(6, 9)],             posture="行軍縱隊", dig=True),
    "BLU-SF": dict(side="allies", eff=3, route=[(12, 1), (20, 1), (24, 4), (25, 7)],
                   posture="隱蔽行進", dig=False),
}
# 抽離：(母編隊, orbat 代號, 生效 gh, 目標, 是否抵達後構築工事)
# 裁示 40：抽離於生效那個 hour 的**開始**執行，抽離點＝母編隊當時位置
# 裁示 41：命令寫的 "i1" 不存在（手冊只公佈到師級，營代號從未發給任一方），
# 兵種與數量明確 → 取該師 ORBAT 第一個步兵營 1-r4。
DETACH = [
    ("BLU-2", "1-r4", 3, (4, 10), True),   # 指揮所守備營（命令原文寫 i1）
    ("BLU-1", "rcn", 4, (11, 5), False),
    ("BLU-3", "rcn", 4, (11, 13), False),
    ("RED-3", "rcn", 4, (20, 3), False),
    ("RED-2", "rcn", 4, (20, 8), False),
]
CP_ORDER = {"axis": (3, "main", (29, 8)), "allies": (3, "main", (4, 10))}

det_uids = {}          # (母編隊, 代號) -> 抽離後的 uid
det_targets = {}       # 抽離 uid -> (目標, dig)


def route_target(u, route):
    """回傳航路上第一個還沒到達的點；全部到達則回 None。"""
    for pt in route:
        if list(u["pos"]) != list(pt):
            return pt
    return None


def resolve(s, gh):
    ev = []

    # 指揮所：命令生效的那個 hour 才開始架設
    for side, (eff, kind, pos) in CP_ORDER.items():
        if gh == eff:
            live = command.establish_cp(s, side, kind, pos)
            ev.append((side, f"開始架設{'主' if kind == 'main' else '前進'}指揮所於 "
                             f"{pos}，{command.CP_SETUP_HOURS}hr 後（gh{live}）啟用"))

    # 抽離（裁示 40：於生效 hour 的開始執行，抽離點為母編隊當時位置）
    for parent, code, eff, tgt, dig_after in DETACH:
        if gh != eff or (parent, code) in det_uids:
            continue
        p = s["units"][parent]
        # detach_bn：依 ORBAT 決定該營攜行裝備並從母師等量扣除（缺陷 15/16），
        # 同時補齊引擎必需欄位與補給狀態（缺陷 12）
        uid, _det = ar.detach_bn(s, parent, code, list(p["pos"]))
        det_uids[(parent, code)] = uid
        det_targets[uid] = (tgt, dig_after)
        ev.append((s["units"][uid]["side"],
                   f"{parent} 抽離 {code} → {uid}，抽離點 {tuple(p['pos'])}"
                   f"（裁示 40：母編隊本 hour 的機動不改變抽離點），前往 {tgt}"))

    # 主力移動
    for uid, plan in MOVE.items():
        if gh < plan["eff"]:
            continue
        u = s["units"][uid]
        tgt = route_target(u, plan["route"])
        if tgt is None:
            if plan["dig"]:
                r = ar.dig(s, uid)
                if r:
                    ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，"
                                    f"砲擊暴露 {r[2]}）"))
            continue
        moved, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, f"{uid}（{plan['posture']}）{msg}"))

    # 抽離單位移動
    for uid, (tgt, dig_after) in det_targets.items():
        u = s["units"].get(uid)
        if not u:
            continue
        if list(u["pos"]) == list(tgt):
            if dig_after:
                r = ar.dig(s, uid)
                if r:
                    ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr）"))
            continue
        moved, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, msg))

    # 藍軍應變 1（照字面執行）：任一編隊停止機動超過 1 hour → 立即構築工事
    # 裁判註：本 tick 藍軍主力於 gh0-3 尚未收到機動令而處於原地，字面上滿足此條件。
    # 依「命令逐條照字面執行」的紀律仍予執行；其工事會在 gh4 起移動時依規棄置，
    # 本 tick 淨效果為零（疲勞 0 起算，輕度活動 -1 與完全休整 -10 無差別）。
    for uid, u in ar.own(s, "allies").items():
        if u["flags"].get("moved") or u.get("static_hours", 0) < 1:
            continue
        plan = MOVE.get(uid)
        if plan and gh >= plan["eff"] and route_target(u, plan["route"]) is not None:
            continue                          # 正在執行機動令，不算「停止機動」
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 依應變 1 就地構築工事 → {r[0]}（{u['dig_hours']:.2f}hr）"))
    return ev


log = []
lines = ar.run_tick(s, resolve, hours=6, log=log)
ar.save(s)

print("=" * 78)
for line in lines:
    print(line)
print("=" * 78)
sc = ar.score(s)
print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}")
print(f"斬首：{command.decapitation(s)}")
print(f"事實紀錄：{len(s.get('record', []))} 筆")
print()
for side in ("allies", "axis"):
    cmd = s.get("command", {}).get(side, {})
    print(f"{side:7} 主CP={cmd.get('main_cp')} 前CP={cmd.get('fwd_cp')} 軍長={cmd.get('commander_at')}")
print()
print(f"{'編隊':12} {'位置':10} {'疲勞':>4} {'org':>6} {'工事':>6} {'補給':10} {'狀態'}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:12} {str(tuple(u['pos'])):10} {u.get('fatigue',0):4} "
          f"{u.get('org',0):6} {u.get('fortification',0):6.2f} "
          f"{str(u.get('supply_status')):10} {ar.status_of(u)}")
