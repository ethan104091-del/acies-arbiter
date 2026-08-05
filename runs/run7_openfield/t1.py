#!/usr/bin/env python3
"""Run 7 — Tick 1 解算（gh6–gh11，1944-08-25 12:00–17:00，全程白天）。

## 與 T0 的差別：雙方都有主指揮所了

命令延遲階梯降為 **+1 級**（`delay_tier_adjust` 回傳 1）：

    L1 → 2hr（gh8 生效）　L2 → 3hr（gh9）　L3 → 4hr（gh10）

**T0 的常設命令不重下就繼續執行，零延遲**（裁示 44／46）。
兩軍本 tick 都選擇讓主力的機動命令續行，只對局部下新令。

## 層級認定（裁示 49：裁判依 rules_v2.md 分級表核定，不採信自標）

| 命令 | 自標 | 認定 | 說明 |
|---|---|---|---|
| 藍 抽離三個營赴 (6,4) | L2 | **L2** | 抽離營級並賦予任務 |
| 藍 BLU-SF 改後段 | L2 | **L2** | 編隊機動任務 |
| 紅 建立前進指揮所 (22,9) | L1 | **L1** | 指揮所 |
| 紅 抽離 1-r4／2-r4 赴兩處指揮所 | L3 | **L2** | 抽離營級並賦予任務；非「跨軸調師」 |

**紅軍那條的修正方向對紅軍有利（L3→L2，快一小時）。** 裁示 49 說裁判依動作性質核定，
若只在對某方不利時才修正、對其有利時就默認自標，那條規則本身就不對稱了。

## 紅軍前進指揮所的兩個後果（引擎自動處理，不需裁判介入）

1. `activate_due_cps` 於啟用時把 `commander_at` 設為 `fwd`——**軍長自動前移至 (22,9)**，
   斬首目標隨之前移（裁示 42）。
2. `fwd_cp_is_forward` 每次取用時動態驗算「x ≤ 本方整編編隊 x 的中位數」。
   不滿足時自動退回 +1 級，不需裁判判斷。

## 資訊差之記載（判例 §二十）

紅軍的 T1 初稿成於裁示 50–57 公告之前。裁判已將完整裁示集送達並給予修改機會，
紅軍選擇不修改。雙方均在完整資訊下定稿。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1]))
import arbiter as ar          # noqa: E402
import command                # noqa: E402
import hourstate as hs        # noqa: E402
import _tickkit as tk         # noqa: E402
import _audit                 # noqa: E402

s = ar.load()
assert s["global_hour"] == 6, f"t1.py 只能從 gh6 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)
ZH = {"allies": "藍軍", "axis": "紅軍"}

# ── T1 新命令（延遲 = 基準 + 現行階梯）──────────────────────────
NEW = [
    ("allies", "L2", "自 BLU-2 抽離 2-r6、1-r6、3-r5 三營 → (6,4) 警衛主指揮所"),
    ("allies", "L2", "BLU-SF 第二段改為 08-26 06:00 起 → (15,1)，偽裝暫緩"),
    ("axis", "L1", "建立前進指揮所 (22,9)，啟用後軍長進駐"),
    ("axis", "L2", "RED-2 抽離 1-r4 → (29,8)、2-r4 → (22,9) 守備並構工"),
]
for side, lv, txt in NEW:
    hs.enqueue_order(s, side, lv, txt,
                     extra_delay=command.delay_tier_adjust(s, side, [0, 0]))

# ── 常設命令：T0 下達、未被取代者，本 tick 零延遲續行 ──────────────
DEST = {
    "BLU-1": (7, 2), "BLU-2": (7, 5), "BLU-AD": (8, 7), "BLU-3": (7, 10),
    "BLU-2-rcn": (13, 6), "BLU-3-rcn": (9, 13), "BLU-2-3-r6": (6, 4),
    "RED-1": (20, 12), "RED-3": (20, 3), "RED-SF": (18, 15),
    "RED-3-rcn": (16, 3), "RED-2": (20, 9), "RED-AD": (20, 10),
    "RED-2-rcn": (16, 8), "BLU-SF": (11, 1),
}
DIG_ON_ARRIVAL = set(DEST)          # 兩軍的常設命令皆為「抵達後構築工事」

NEW_DET = {          # gh9 生效：(母編隊, 營碼, 目的地)
    "allies": [("BLU-2", "2-r6", (6, 4)), ("BLU-2", "1-r6", (6, 4)),
               ("BLU-2", "3-r5", (6, 4))],
    "axis":   [("RED-2", "1-r4", (29, 8)), ("RED-2", "2-r4", (22, 9))],
}
FWD_CP = {"axis": (22, 9)}

TIER = 1                              # 雙方皆有主指揮所
L1_GH, L2_GH = 6 + 1 + TIER, 6 + 2 + TIER      # gh8 / gh9
done = {"cp": set(), "det": set(), "fwd_live": set()}
halted = {}                           # 應變觸發：就地停止並構工的編隊


def contingency(s, gh, ev):
    """雙方的應變條款。本 tick 兩軍相距甚遠，預期不觸發；仍逐條檢查。

    藍軍第一條：整編師遭砲擊、或 ≤3 格內偵獲敵師級 → 就地停止並構工，
                連續 2 小時解除後恢復常設命令。
    紅軍前兩條：指揮所守備營 ≤3 格內偵獲敵戰鬥編隊 → 停止構築、固守、回報。
    """
    for side in ("allies", "axis"):
        seen = tk.spotted(s, side)
        for uid, u in ar.own(s, side).items():
            if u.get("is_detachment") or uid not in DEST:
                continue
            near = [e for e in seen
                    if e in s["units"] and tk.is_division(s["units"][e])
                    and ar.dist(u["pos"], s["units"][e]["pos"]) <= 3]
            hit = u["flags"].get("hit")
            if (near or hit) and uid not in halted:
                halted[uid] = gh
                ev.append((uid, f"{uid} 應變觸發：{'遭砲擊' if hit else '≤3 格內偵獲敵師級 ' + near[0]}"
                                f"，就地停止行軍並構築工事"))
            elif uid in halted and not near and not hit and gh - halted[uid] >= 2:
                halted.pop(uid)
                ev.append((uid, f"{uid} 連續 2 小時無接觸，恢復執行常設命令"))


def resolve(s, gh):
    ev = []

    # 前進指揮所啟用通報（run_tick 已在本 hour 開頭呼叫過 activate_due_cps）
    for side, pos in FWD_CP.items():
        if side in done["fwd_live"]:
            continue
        if "fwd" in command.cp_hexes(s, side):
            done["fwd_live"].add(side)
            fwd_ok = command.fwd_cp_is_forward(s, side)
            ev.append((side, f"前進指揮所於 {tuple(pos)} 啟用，**軍長已前移進駐**"
                             f"（裁示 42：斬首目標隨之前移）；"
                             f"「真的在前」驗算 = {'通過，其 6 格內編隊享 0 級延遲' if fwd_ok else '未通過，退回 +1 級'}"))

    # L1：開始架設前進指揮所
    if gh >= L1_GH:
        for side, pos in FWD_CP.items():
            if side in done["cp"]:
                continue
            eff = command.establish_cp(s, side, "fwd", list(pos))
            done["cp"].add(side)
            ev.append((side, f"命令生效：於 {tuple(pos)} 開始架設前進指揮所"
                             f"（{command.CP_SETUP_HOURS}hr，gh{eff} 完成）"))

    # L2：新抽離
    if gh >= L2_GH:
        for side, items in NEW_DET.items():
            for parent, code, dst in items:
                key = f"{parent}-{code}"
                if key in done["det"] or parent not in s["units"]:
                    continue
                uid, det = ar.detach_bn(s, parent, code, list(s["units"][parent]["pos"]))
                done["det"].add(key)
                DEST[uid] = dst
                DIG_ON_ARRIVAL.add(uid)
                p = s["units"][parent]
                ev.append((parent, f"{parent} 抽離 {uid}（{det.get('personnel',0)} 人）"
                                   f"於 {tuple(det['pos'])}，任務目標 {tuple(dst)}；"
                                   f"母編隊餘 {p.get('personnel',0)} 人"))

    contingency(s, gh, ev)

    # 機動（常設命令持續執行；被應變停住者改為構工）
    for uid, dst in list(DEST.items()):
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid):
            continue
        if uid in halted or list(u["pos"]) == list(dst):
            if uid in DIG_ON_ARRIVAL:
                m = tk.try_dig(s, uid)
                if m:
                    ev.append((uid, m))
            continue
        _, m = ar.advance(s, uid, list(dst))
        ev.append((uid, m))
    return ev


lines = ar.run_tick(s, resolve, hours=6)
ar.save(s)
for l in lines:
    print(l)
print()
_audit.require_clean(s, before)

sc = ar.score(s)
print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}\n")
for side in ("allies", "axis"):
    print(f"── {ZH[side]} ──")
    for uid, u in sorted(ar.own(s, side).items()):
        w = ar.hex_works(s, u["pos"])
        r = u.get("resources", {})
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 疲勞 {u.get('fatigue',0):>2}"
              f" 工事 {u.get('fortification',0):.3f} 本格 {w:>6.0f}mh"
              f" POL {r.get('POL',0):>5.1f} {u['visibility_state']}")
    print(f"  指揮：{ar.cp_line(s, side)}")
print()
print("偵獲：藍→", s["fog_of_war"].get("allies_spotted"))
print("　　　紅→", s["fog_of_war"].get("axis_spotted"))

snap = HERE / "snap_T2start.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 快照 {snap}")
