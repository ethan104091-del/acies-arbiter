#!/usr/bin/env python3
"""Run 5 Tick 2 解算（gh12-17，1944-08-25 18:00-24:00，全程夜間）。

延遲：藍軍前進指揮所 (4,10) 已於 gh10 啟用且軍長進駐 → 6 格內編隊 0 級（L1 → gh13）、
半徑外 +1（L1 → gh14）。紅軍僅主指揮所 → 全軍 +1（L1 → gh14）。

★ 節奏差的實際後果：紅軍 T1 命令沒有夜間條款，休整令 gh14 才到，
  故 gh12-13 仍依 T1 既有命令**夜行軍兩小時**（裁示 13：新命令才解除既有命令）。
  藍軍 T1 命令自己寫了「18:00 就地停止」，故 18:00 即停。

[判例] 命令中的「夜間半速續進」與規則的夜間 ×0.5 指同一件事，**不疊加**。
  否則會變成四分之一速，那不是指揮官的意思。對雙方同一標準。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 12, f"必須從 gh12 起始，現在 gh={s['global_hour']}"

ar.ruling(s, what="命令中的「夜間半速續進」不與規則的夜間 ×0.5 疊加",
          basis="movement_v1 已將夜間移動減半；再折一次＝1/4 速，非指揮官原意。雙方同一標準",
          applied="move_rate 的夜間 ×0.5 照舊，不另外折半",
          precedent=True)

RED_ORDERS = [
    ("L1", "軍長於 (24,9) 建立前進指揮所並進駐；主指揮所 (29,8) 保留"),
    ("L1", "RED-2 拉出 2-r4 前往 (24,9) 固守前進指揮所，抵達後構築工事"),
    ("L1", "RED-2-1-r4 留 (29,8) 續構築工事至散兵壕級，不移動"),
    ("L1", "RED-3 在 (25,3) 完全休整"), ("L1", "RED-2 在 (25,9) 完全休整"),
    ("L1", "RED-1 在 (25,13) 完全休整"), ("L1", "RED-AD 在 (23,10) 完全休整"),
    ("L1", "RED-SF 在 (22,15) 完全休整並保持隱蔽"),
]
BLUE_ORDERS = [
    ("L1", "BLU-1/2/3 本夜 18:00-20:00 完全休整、20:00-06:00 構築工事，06:00 起續行至 x=8"),
    ("L1", "BLU-1 拉出 1-r1 進駐 (5,9) 森林格並構築工事至有頂蓋"),
    ("L1", "BLU-AD 留 (7,9) 續構築工事（含戰車掩壕）至有頂蓋"),
    ("L1", "BLU-2-1-r4 與 BLU-3-1-r7 於 (4,10) 構築工事至有頂蓋，固守不得離格"),
    ("L1", "BLU-AD 拉出 rcn 前往 (10,13) 森林格設第三觀測哨"),
    ("L1", "三個既有偵察哨續行進駐 (13,6)/(16,11)/(5,15)，靜止隱蔽觀測"),
    ("L1", "BLU-SF 本夜 18:00-22:00 續進、22:00-06:00 隱蔽休整；BLU-SF-rcn 同"),
]
for side, orders in (("axis", RED_ORDERS), ("allies", BLUE_ORDERS)):
    ref = s["units"]["RED-2" if side == "axis" else "BLU-2"]["pos"]
    for lvl, txt in orders:
        hs.enqueue_order(s, side, lvl, txt,
                         extra_delay=command.delay_tier_adjust(s, side, ref))


def tier_eff(side, uid, base=1):
    """該編隊的 L1 命令生效 gh：12 + base + 指揮所階梯（逐編隊算，反映前進指揮所半徑）。"""
    return 12 + base + command.delay_tier_adjust(s, side, s["units"][uid]["pos"])


# 藍軍：0 級者 gh13 生效；半徑外（BLU-SF 系列）gh14
EFF_B = {u: tier_eff("allies", u) for u in
         ("BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-2-1-r4", "BLU-3-1-r7",
          "BLU-1-rcn", "BLU-3-rcn", "BLU-2-rcn", "BLU-SF", "BLU-SF-rcn")}
EFF_R = {u: tier_eff("axis", u) for u in
         ("RED-1", "RED-2", "RED-3", "RED-AD", "RED-SF", "RED-2-1-r4",
          "RED-2-rcn", "RED-3-rcn")}

# T1 既有命令的續行目標（新命令生效前照舊執行）
OLD_TARGET = {"RED-3": (22, 3), "RED-2": (23, 9), "RED-1": (23, 12),
              "RED-AD": (23, 10), "RED-SF": (19, 15)}
# 偵察哨與特戰的目標（T1、T2 一致，續行）
GOING = {"BLU-1-rcn": (13, 6), "BLU-3-rcn": (16, 11), "BLU-2-rcn": (5, 15),
         "BLU-SF": (13, 2), "BLU-SF-rcn": (13, 2),
         "RED-2-rcn": (20, 8), "RED-3-rcn": (20, 3)}
DIG_HOLD = ["BLU-AD", "BLU-2-1-r4", "RED-2-1-r4"]
DETACH = [("BLU-1", "1-r1", None, (5, 9)), ("BLU-AD", "rcn", None, (10, 13)),
          ("RED-2", "2-r4", None, (24, 9))]
det_targets, done = {}, set()


def resolve(s, gh):
    ev = []
    # 紅軍前進指揮所：命令 gh14 生效 → 架設 2hr → gh16 啟用
    if gh == EFF_R["RED-2"]:
        live = command.establish_cp(s, "axis", "fwd", (24, 9))
        ev.append(("axis", f"開始架設前進指揮所於 (24, 9)，gh{live} 啟用；主指揮所保留"))

    for parent, code, _e, tgt in DETACH:
        eff = (EFF_B if parent.startswith("BLU") else EFF_R)[parent]
        if gh != eff or (parent, code) in done:
            continue
        p = s["units"][parent]
        uid, _ = ar.detach_bn(s, parent, code, list(p["pos"]))
        done.add((parent, code))
        det_targets[uid] = tgt
        ev.append((s["units"][uid]["side"],
                   f"{parent} 抽離 {code} → {uid}（裝備 {s['units'][uid]['equip']}），"
                   f"抽離點 {tuple(p['pos'])}，前往 {tgt}"))

    # 紅軍主力：新命令生效前照 T1 既有命令續行（夜行軍），生效後完全休整
    for uid, tgt in OLD_TARGET.items():
        u = s["units"][uid]
        if gh < EFF_R[uid]:
            if list(u["pos"]) != list(tgt):
                _, msg = ar.advance(s, uid, list(tgt))
                ev.append((uid, f"{uid}（依 T1 既有命令夜行軍）{msg}"))
        # 生效後：完全休整＝不動不戰不挖，管線自動 -10 疲勞

    # 藍軍三個師：gh12 依 T1 既有命令就地構築；gh13 完全休整；gh14 起構築
    for uid in ("BLU-1", "BLU-2", "BLU-3"):
        if gh == EFF_B[uid]:
            ev.append((uid, f"{uid} 依 T2 命令完全休整一小時（18:00-20:00 段）"))
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 就地構築工事 → {r[0]}（{s['units'][uid]['dig_hours']:.2f}hr，"
                            f"砲擊暴露 {r[2]}）"))

    for uid in DIG_HOLD:
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{s['units'][uid]['dig_hours']:.2f}hr，"
                            f"砲擊暴露 {r[2]}）"))

    # 移動中的偵察哨、特戰；BLU-SF 系列 22:00(gh16) 起休整
    for uid, tgt in GOING.items():
        u = s["units"].get(uid)
        if not u:
            continue
        if uid.startswith("BLU-SF") and gh >= 16:
            continue                       # 22:00-06:00 隱蔽休整
        if list(u["pos"]) != list(tgt):
            _, msg = ar.advance(s, uid, list(tgt))
            ev.append((uid, msg))

    for uid, tgt in det_targets.items():
        u = s["units"].get(uid)
        if not u:
            continue
        if list(u["pos"]) != list(tgt):
            _, msg = ar.advance(s, uid, list(tgt))
            ev.append((uid, msg))
        else:
            r = ar.dig(s, uid)
            if r:
                ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr）"))
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
print(f"事實紀錄：{len(s.get('record', []))} 筆（含裁示）")
for side in ("allies", "axis"):
    c = s.get("command", {}).get(side, {})
    print(f"{side:7} 主CP={c.get('main_cp')} 前CP={c.get('fwd_cp')} 軍長={c.get('commander_at')}")
print()
print(f"{'編隊':13} {'位置':10} {'疲勞':>4} {'org':>6} {'工事':>6} {'暴露':>5} {'補給':10}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('fatigue',0):4} {u.get('org',0):6} "
          f"{u.get('fortification',0):6.2f} {ar.exposure_factor(u, ar.terr(s,u['pos'])):5} "
          f"{str(u.get('supply_status')):10}")
