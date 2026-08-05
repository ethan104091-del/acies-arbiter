#!/usr/bin/env python3
"""Run 7 — Tick 0 解算（gh0–gh5，1944-08-25 06:00–11:00，全程白天）。

## 本 tick 的時序骨架

雙方開局皆無指揮所 → 命令延遲 +2 級（`command.delay_tier_adjust` 於下令當下取值）。
層級認定見裁示 49（裁判依 `rules_v2.md` 分級表核定，不採信自標）：

    gh0–gh2   兩軍毫無動作。命令還在傳達途中。
    gh3       L1 生效 → 雙方「建立主指揮所」開始架設（CP_SETUP_HOURS=2）
    gh4       L2 生效 → 雙方全部編隊機動命令開始執行（機動第 1 小時）
    gh5       主指揮所啟用（gh3+2）；機動第 2 小時
    → T0 結束時雙方各只走了 2 小時。

**本局第一個教訓：開局沒有指揮所，前三小時等於不存在。**

## 命令來源（定稿，已存檔備查）

- 藍：`命令_T0_藍軍_定稿.md`
- 紅：`命令_T0_紅軍_定稿.md`

## 裁判紀律

- 不對敵佔格呼叫 `advance`（裁示 47）——本 tick 兩軍相距 20 格以上，無此情形。
- 解算後跑 `_audit.require_clean()`，稽核通過才印計分（P6-14）。
- 事件的 target 一律指明 uid／陣營／both，不用 None（push_log 的防洩漏約定）。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # runs/ → _tickkit, _audit
sys.path.insert(0, str(HERE.parents[1]))      # repo 根 → arbiter
import arbiter as ar          # noqa: E402
import command                # noqa: E402
import hourstate as hs        # noqa: E402
import _tickkit as tk         # noqa: E402
import _audit                 # noqa: E402

s = ar.load()
assert s["global_hour"] == 0, f"t0.py 只能從 gh0 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)

ZH = {"allies": "藍軍", "axis": "紅軍"}

# ── 命令佇列 ────────────────────────────────────────────────────
# extra_delay 取自 command.delay_tier_adjust：下令當下雙方皆無指揮所 → +2。
ORDERS = [
    ("allies", "L1", "建立主指揮所 (6,4)"),
    ("allies", "L2", "BLU-1 行軍縱隊 → (7,2)，抵達後構築工事"),
    ("allies", "L2", "BLU-2 行軍縱隊 → (7,5)，抵達後構築工事"),
    ("allies", "L2", "BLU-AD 行軍縱隊 → (8,7)，抵達後構築工事"),
    ("allies", "L2", "BLU-3 行軍縱隊 → (7,10)，抵達後構築工事"),
    ("allies", "L2", "BLU-SF 滲透行軍經 (7,1) → (11,1)，抵達後偽裝作業"),
    ("allies", "L2", "抽離 BLU-2-rcn → (13,6)、BLU-3-rcn → (9,13)"),
    ("allies", "L2", "抽離 BLU-2 之 3-r6 → (6,4) 警衛主指揮所"),
    ("axis", "L1", "建立主指揮所 (29,8)"),
    ("axis", "L2", "RED-3 戰備推進 → (20,3)"),
    ("axis", "L2", "RED-2 經 (25,10) 戰備推進 → (20,9)"),
    ("axis", "L2", "RED-1 戰備推進 → (20,12)"),
    ("axis", "L2", "RED-AD 經 (25,10) 行軍縱隊 → (20,10)"),
    ("axis", "L2", "RED-SF 隱蔽滲透 → (18,15)"),
    ("axis", "L2", "抽離 RED-3-rcn → (16,3)"),
    ("axis", "L2", "抽離 RED-2-rcn 經 (26,7) → (16,8)"),
]
for side, lv, txt in ORDERS:
    tier = command.delay_tier_adjust(s, side, [0, 0])      # 無指揮所 → 2
    hs.enqueue_order(s, side, lv, txt, extra_delay=tier)

# ── 目的地、航路、抽離 ──────────────────────────────────────────
DEST = {
    "BLU-1": (7, 2), "BLU-2": (7, 5), "BLU-AD": (8, 7), "BLU-3": (7, 10),
    "BLU-SF": (11, 1),
    "RED-3": (20, 3), "RED-1": (20, 12), "RED-SF": (18, 15),
    "RED-2": (20, 9), "RED-AD": (20, 10),
}
ROUTE = {                       # 命令中明文指定的中途點
    "RED-2": [(25, 10), (20, 9)],
    "RED-AD": [(25, 10), (20, 10)],
    "BLU-SF": [(7, 1), (11, 1)],
    "RED-2-rcn": [(26, 7), (16, 8)],
}
DET = {   # (母編隊, 營碼, 目的地)
    "allies": [("BLU-2", "rcn", (13, 6)), ("BLU-3", "rcn", (9, 13)),
               ("BLU-2", "3-r6", (6, 4))],
    "axis":   [("RED-3", "rcn", (16, 3)), ("RED-2", "rcn", (16, 8))],
}
CP_ORDER = {"allies": (6, 4), "axis": (29, 8)}
CAMO_ON_ARRIVAL = {"BLU-SF"}    # 藍軍第 6 條：抵達後先偽裝作業

L1_GH = hs.LEVEL_DELAY["L1"] + 2
L2_GH = hs.LEVEL_DELAY["L2"] + 2
done = {"cp": set(), "det": set(), "cp_live": set()}
IDX = {}


def resolve(s, gh):
    ev = []

    # 指揮所：run_tick 已在本 hour 開頭呼叫過 activate_due_cps，故此處只做「新啟用」通報
    for side in ("allies", "axis"):
        if side in done["cp_live"]:
            continue
        cps = command.cp_hexes(s, side)
        if "main" in cps:
            done["cp_live"].add(side)
            ev.append((side, f"主指揮所於 {tuple(cps['main'])} 架設完成並啟用，"
                             f"軍長進駐；命令延遲由 +2 級降為 +1 級"))

    # gh3：L1 生效 → 開始架設
    if gh >= L1_GH:
        for side, pos in CP_ORDER.items():
            if side in done["cp"]:
                continue
            eff = command.establish_cp(s, side, "main", list(pos))
            done["cp"].add(side)
            ev.append((side, f"命令生效：於 {tuple(pos)} 開始架設主指揮所"
                             f"（{command.CP_SETUP_HOURS}hr，gh{eff} 完成）"))

    # gh4 之前，機動命令尚未生效
    if gh < L2_GH:
        if gh < L1_GH:
            ev.append(("both", "（雙方命令均在傳達途中，全線無動作）"))
        return ev

    # 抽離（只做一次）
    for side, items in DET.items():
        for parent, code, dest in items:
            key = f"{parent}-{code}"
            if key in done["det"] or parent not in s["units"]:
                continue
            # detach_bn 回傳 (uid, 棋子 dict)，不是訊息——訊息由此處自行組。
            uid, det = ar.detach_bn(s, parent, code, list(s["units"][parent]["pos"]))
            done["det"].add(key)
            DEST[uid] = dest
            p = s["units"][parent]
            ev.append((parent, f"{parent} 抽離 {uid}（{det.get('type')}，"
                               f"{det.get('personnel',0)} 人、戰車 {det['equip']['tanks']}、"
                               f"火砲 {det['equip']['guns']}）於 {tuple(det['pos'])}，"
                               f"任務目標 {tuple(dest)}；母編隊餘 {p.get('personnel',0)} 人、"
                               f"戰車 {p['equip']['tanks']}、火砲 {p['equip']['guns']}"))

    # 機動
    for uid, dest in list(DEST.items()):
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid):
            continue
        if list(u["pos"]) == list(dest):
            m = (tk.try_camouflage(s, uid) if uid in CAMO_ON_ARRIVAL
                 else tk.try_dig(s, uid))
            if m:
                ev.append((uid, m))
            continue
        route = ROUTE.get(uid)
        if route:
            IDX.setdefault(uid, 0)
            for m in tk.route_advance(s, uid, [list(p) for p in route], IDX):
                ev.append((uid, m))
        else:
            _, m = ar.advance(s, uid, list(dest))
            ev.append((uid, m))
    return ev


lines = ar.run_tick(s, resolve, hours=6)   # log 參數是「額外收集用的 list」，不是開關
ar.save(s)

for l in lines:
    print(l)
print()
_audit.require_clean(s, before)

sc = ar.score(s)
print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}"
      f"（本 tick 兩軍未接觸，無傷亡）\n")
for side in ("allies", "axis"):
    print(f"── {ZH[side]} ──")
    for uid, u in sorted(ar.own(s, side).items()):
        w = ar.hex_works(s, u["pos"])
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 疲勞 {u.get('fatigue',0):>2}"
              f"  工事 {u.get('fortification',0):.3f}"
              f"  本格 {w:>6.0f}mh  {u['visibility_state']}")
    print(f"  指揮：{ar.cp_line(s, side)}")
print()
print("偵獲：藍→", s["fog_of_war"].get("allies_spotted"))
print("　　　紅→", s["fog_of_war"].get("axis_spotted"))

snap = HERE / "snap_T1start.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 快照 {snap}")
