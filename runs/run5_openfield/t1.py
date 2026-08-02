#!/usr/bin/env python3
"""Run 5 Tick 1 解算（gh6-11，1944-08-25 12:00-18:00，全程白天）。

雙方主指揮所皆已於 gh5 啟用 → 延遲階梯 +1。L1 → gh8 生效、L2 → gh9 生效。
藍軍另下令於 (4,10) 加設前進指揮所：命令 gh8 生效，再架設 2hr → gh10 啟用，
自此軍長改駐前進指揮所，(4,10) 六格內的藍軍編隊降為 0 級延遲、半徑外仍 +1。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 6, f"必須從 gh6 起始，現在 gh={s['global_hour']}"

RED_ORDERS = [
    ("L1", "RED-2 拉出 1-r4 前往 (29,8) 固守主指揮所，抵達後構築工事，不隨主力前推"),
    ("L2", "RED-3 向 (22,3) 戰備推進，避開森林"),
    ("L2", "RED-2 向 (23,9) 戰備推進，保持與 RED-AD 可相互支援"),
    ("L2", "RED-1 向 (23,12) 戰備推進，保持南翼與 RED-2 聯絡"),
    ("L2", "RED-AD 向 (23,10) 行軍縱隊推進；不入森林、不越過 RED-2 向西追擊"),
    ("L2", "RED-SF 向 (19,15) 隱蔽滲透偵察"),
    ("L2", "RED-3-rcn 向 (20,3) 前進偵察，發現敵軍即原地隱蔽觀察"),
    ("L2", "RED-2-rcn 向 (20,8) 前進偵察，發現敵軍即原地隱蔽觀察"),
]
BLUE_ORDERS = [
    ("L1", "於 (4,10) 建立前進指揮所並由軍長進駐；主指揮所不撤除。"
           "BLU-2-1-r4 續行進駐 (4,10) 守備，抵達後構築工事至有頂蓋"),
    ("L2", "BLU-1 經 (4,7)、(6,8) 推進至 (8,8)，抵達後構築工事至有頂蓋"),
    ("L2", "BLU-2 經 (3,8)、(5,8)、(7,9) 繞森林推進至 (8,9)；拉出 rcn 至 (5,15) 後方警戒"),
    ("L2", "BLU-3 經 (4,11)、(6,10) 推進至 (8,10)；拉出 1-r7 至 (4,10) 增援指揮所守備"),
    ("L1", "BLU-AD 推進至 (7,9) 任中央預備隊，抵達後停止機動節油並構築工事（含戰車掩壕）"),
    ("L2", "BLU-1-rcn 前推至 (13,6) 森林格靜止隱蔽觀測"),
    ("L2", "BLU-3-rcn 前推至 (16,11) 森林格靜止隱蔽觀測"),
    ("L1", "BLU-SF 續沿北緣東進，航路 (13,2)→(22,2)→(25,5)；拉出 rcn 超前 4-5 格前導偵察"),
]
for side, orders in (("axis", RED_ORDERS), ("allies", BLUE_ORDERS)):
    for lvl, txt in orders:
        pos = s["units"]["RED-2" if side == "axis" else "BLU-2"]["pos"]
        extra = command.delay_tier_adjust(s, side, pos)      # 雙方皆 +1（僅主指揮所）
        hs.enqueue_order(s, side, lvl, txt, extra_delay=extra)

MOVE = {
    "RED-3":  dict(eff=9, route=[(22, 3)],  posture="戰備推進", dig=False),
    "RED-2":  dict(eff=9, route=[(23, 9)],  posture="戰備推進", dig=False),
    "RED-1":  dict(eff=9, route=[(23, 12)], posture="戰備推進", dig=False),
    "RED-AD": dict(eff=9, route=[(23, 10)], posture="行軍縱隊", dig=False),
    "RED-SF": dict(eff=9, route=[(19, 15)], posture="隱蔽滲透", dig=False),
    "RED-3-rcn": dict(eff=9, route=[(20, 3)], posture="前進偵察", dig=False),
    "RED-2-rcn": dict(eff=9, route=[(20, 8)], posture="前進偵察", dig=False),
    "BLU-1":  dict(eff=9, route=[(4, 7), (6, 8), (8, 8)],  posture="行軍縱隊→戰備", dig=True),
    "BLU-2":  dict(eff=9, route=[(3, 8), (5, 8), (7, 9), (8, 9)], posture="行軍縱隊→戰備", dig=True),
    "BLU-3":  dict(eff=9, route=[(4, 11), (6, 10), (8, 10)], posture="行軍縱隊→戰備", dig=True),
    "BLU-AD": dict(eff=8, route=[(7, 9)],   posture="行軍縱隊", dig=True),
    "BLU-SF": dict(eff=8, route=[(13, 2), (22, 2), (25, 5)], posture="隱蔽行進", dig=False),
    "BLU-1-rcn": dict(eff=9, route=[(13, 6)], posture="前進偵察", dig=False),
    "BLU-3-rcn": dict(eff=9, route=[(16, 11)], posture="前進偵察", dig=False),
    "BLU-2-1-r4": dict(eff=8, route=[(4, 10)], posture="進駐守備", dig=True),
}
DETACH = [
    ("RED-2", "1-r4", 8, (29, 8), True),
    ("BLU-2", "rcn", 9, (5, 15), False),
    ("BLU-3", "1-r7", 9, (4, 10), True),
    ("BLU-SF", "rcn", 8, (13, 2), False),
]
# 藍軍前進指揮所：命令 gh8 生效 → 架設 2hr → gh10 啟用，軍長改駐 fwd
CP_ORDER = {"allies": (8, "fwd", (4, 10))}

det_targets = {}
done_detach = set()
halted = set()          # 應變 3 觸發後就地停止的師


def route_target(u, route):
    for pt in route:
        if list(u["pos"]) != list(pt):
            return pt
    return None


def spotted_enemy_within(s, uid, rng):
    u = s["units"][uid]
    seen = s.get("fog_of_war", {}).get(f"{u['side']}_spotted", [])
    return [e for e in seen if ar.dist(s["units"][e]["pos"], u["pos"]) <= rng]


def resolve(s, gh):
    ev = []

    for side, (eff, kind, pos) in CP_ORDER.items():
        if gh == eff:
            live = command.establish_cp(s, side, kind, pos)
            ev.append((side, f"開始架設前進指揮所於 {pos}，{command.CP_SETUP_HOURS}hr 後"
                             f"（gh{live}）啟用；主指揮所不撤除"))

    for parent, code, eff, tgt, dig_after in DETACH:
        if gh != eff or (parent, code) in done_detach:
            continue
        p = s["units"][parent]
        uid, _ = ar.detach_bn(s, parent, code, list(p["pos"]))
        done_detach.add((parent, code))
        det_targets[uid] = (tgt, dig_after)
        ev.append((s["units"][uid]["side"],
                   f"{parent} 抽離 {code} → {uid}（攜行裝備 {s['units'][uid]['equip']}，"
                   f"母編隊等量扣除；裁示 42），抽離點 {tuple(p['pos'])}，前往 {tgt}"))

    # 藍軍應變 3：師級在抵達目標前於 5 格內偵獲敵編隊 → 就地停止並構築工事
    for uid in ("BLU-1", "BLU-2", "BLU-3"):
        if uid in halted:
            continue
        near = spotted_enemy_within(s, uid, 5)
        if near and route_target(s["units"][uid], MOVE[uid]["route"]) is not None:
            halted.add(uid)
            ev.append((uid, f"{uid} 依應變 3 就地停止（5 格內偵獲 {', '.join(near)}），改構築工事"))

    for uid, plan in list(MOVE.items()) + [(k, dict(eff=0, route=[v[0]], posture="",
                                                   dig=v[1])) for k, v in det_targets.items()]:
        u = s["units"].get(uid)
        if not u or gh < plan["eff"]:
            continue
        tgt = None if uid in halted else route_target(u, plan["route"])
        if tgt is None:
            if plan["dig"]:
                r = ar.dig(s, uid)
                if r:
                    ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，"
                                    f"砲擊暴露 {r[2]}）"))
            continue
        moved, msg = ar.advance(s, uid, list(tgt))
        ev.append((uid, f"{uid}（{plan['posture']}）{msg}" if plan["posture"] else f"{uid} {msg}"))
    return ev


log = []
lines = ar.run_tick(s, resolve, hours=6, log=log)
ar.save(s)

print("=" * 78)
for line in lines:
    print(line)
print("=" * 78)
sc = ar.score(s)
print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}｜斬首：{command.decapitation(s)}")
print(f"事實紀錄：{len(s.get('record', []))} 筆")
for side in ("allies", "axis"):
    cmd = s.get("command", {}).get(side, {})
    print(f"{side:7} 主CP={cmd.get('main_cp')} 前CP={cmd.get('fwd_cp')} 軍長={cmd.get('commander_at')}"
          f" → 該方 L1 令下一 tick 延遲 {command.command_delay(s, side, 'L1', [8, 9])}hr（以 (8,9) 為例）")
print()
print(f"{'編隊':13} {'位置':10} {'疲勞':>4} {'org':>6} {'工事':>6} {'補給':10} {'偵獲':>4}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    seen = len(s.get("fog_of_war", {}).get(f"{u['side']}_spotted", []))
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('fatigue',0):4} {u.get('org',0):6} "
          f"{u.get('fortification',0):6.2f} {str(u.get('supply_status')):10} {seen:4}")
