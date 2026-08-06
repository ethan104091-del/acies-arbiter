#!/usr/bin/env python3
"""Run 7 — Tick 3 解算（gh18–gh23，1944-08-26 00:00–05:00，全程夜間／黎明）。

## 兩軍第一次同時改命令，而且改的是同一件事：停下來挖

- **紅軍**引用裁示 55 停止全線前推：「主力已進入疲勞八十以上的失能區間，
  夜間不再以一格地形交換機動力。」三個師就地構工休整，兩支偵察隊改推至 x=13 並偽裝。
- **藍軍**只改 BLU-AD 的目標（(12,5)→(13,5)，理由是讓 54 門 SP105 射程涵蓋到 x=18），
  其餘維持原命令。它指出這個延遲是免費的：L2 於 gh21 生效，而東進段本來就要 gh24 才啟動。

雙方 L2 命令皆 **+1 級 → 3 小時 → gh21 生效**。

## 紅軍的前進指揮所已失格（引擎自動判定，非裁判裁量）

`fwd_cp_is_forward` 要求前進指揮所位於本方**整編編隊 x 中位數之前**。
紅軍整編編隊 x = [18, 20, 21, 21, 21] → 中位數 **21**，而前進指揮所在 **x=22**。
紅軍須 x ≤ 中位數 → **不通過**。

後果：紅軍付出了斬首風險（軍長前移 7 格至 (22,9)），卻**拿不到任何延遲上的好處**——
全軍仍為 +1 級，與只有主指揮所完全相同。**這是它自己的部隊推過了指揮所造成的。**

`cp_line` 原本只印「命令延遲加成 +見說明」，看不出驗算結果；已改為明白列出
驗算通過與否、中位數、以及實際階梯。這對雙方對稱（藍軍未建前進指揮所，故只見 +1 級）。

## 構築工事的適用對象（判例 §二十一：逐一列舉並註明命令出處）

| 編隊 | 命令出處 | 生效 |
|---|---|---|
| BLU-1／2／3／SF、兩支 rcn、(6,4) 四營 | 藍 T0 第 2–8、T1 第 1 條 | 續行中 |
| BLU-AD | 藍 T3 第 1 條（整條改寫，取代原命令） | gh21 |
| RED-2-1-r4／2-r4 | 紅 T1 第 2 條、T3 第 5–6 條 | 續行中 |
| RED-1／RED-2／RED-3／RED-AD | **紅 T3 第 1–4 條** | **gh21** |

紅軍偵察隊為**偽裝作業**（T3 第 7–8 條「抵達後偽裝作業至完成」），不是構築工事。
RED-SF 至今未獲任何構工或偽裝令，僅固守 (18,15)。
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
assert s["global_hour"] == 18, f"t3.py 只能從 gh18 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)
ZH = {"allies": "藍軍", "axis": "紅軍"}

NEW = [
    ("allies", "L2", "BLU-AD 常設命令整條改寫：續構工至 08-26 06:00，"
                     "自該時起 → (13,5)（原 (12,5) 作廢），抵達後構工三小時、偽裝、續構工"),
    ("axis", "L2", "RED-1 停止前推，就地構工至有頂蓋級並固守"),
    ("axis", "L2", "RED-2 停止前推，就地構工至散兵壕級並固守"),
    ("axis", "L2", "RED-3 停止前推，就地構工至有頂蓋級並固守"),
    ("axis", "L2", "RED-AD 於 (20,10) 構工至有頂蓋級"),
    ("axis", "L2", "RED-2-1-r4 於 (29,8) 構工至有頂蓋級並固守"),
    ("axis", "L2", "RED-2-2-r4 於 (22,9) 構工至有頂蓋級並固守"),
    ("axis", "L2", "RED-2-rcn → (13,8) 前進偵察，抵達後偽裝作業至完成"),
    ("axis", "L2", "RED-3-rcn → (13,3) 前進偵察，抵達後偽裝作業至完成"),
]
for side, lv, txt in NEW:
    hs.enqueue_order(s, side, lv, txt,
                     extra_delay=command.delay_tier_adjust(s, side, [0, 0]))

NEW_GH = 18 + 2 + 1          # L2 於 gh21 生效（雙方皆 +1 級）

# gh18–gh20：舊常設命令
OLD_DEST = {
    "RED-1": (20, 12), "RED-2": (20, 9), "RED-3": (20, 3),
    "RED-AD": (20, 10), "RED-SF": (18, 15),
    "RED-2-rcn": (16, 8), "RED-3-rcn": (16, 3),
    "RED-2-1-r4": (29, 8), "RED-2-2-r4": (22, 9),
    "BLU-1": (7, 2), "BLU-2": (7, 5), "BLU-3": (7, 10), "BLU-AD": (8, 7),
    "BLU-SF": (11, 1), "BLU-2-rcn": (13, 6), "BLU-3-rcn": (9, 13),
    "BLU-2-3-r6": (6, 4), "BLU-2-1-r6": (6, 4), "BLU-2-2-r6": (6, 4),
    "BLU-2-3-r5": (6, 4),
}
OLD_DIG = {"BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-SF", "BLU-2-rcn", "BLU-3-rcn",
           "BLU-2-3-r6", "BLU-2-1-r6", "BLU-2-2-r6", "BLU-2-3-r5",
           "RED-2", "RED-2-1-r4", "RED-2-2-r4"}

# gh21 起：新命令覆寫。紅軍三個師與裝甲師改為就地構工（目的地＝生效時所在格）。
HALT_AND_DIG = ("RED-1", "RED-2", "RED-3", "RED-AD")
NEW_DEST = {"RED-2-rcn": (13, 8), "RED-3-rcn": (13, 3)}
NEW_CAMO = {"RED-2-rcn", "RED-3-rcn"}      # 紅 T3 第 7–8 條：抵達後偽裝，非構工
frozen_pos = {}                             # 生效時各師的所在格


def resolve(s, gh):
    ev = []
    if gh == NEW_GH:
        for uid in HALT_AND_DIG:
            u = s["units"].get(uid)
            if u:
                frozen_pos[uid] = list(u["pos"])
                ev.append((uid, f"{uid} 新令生效：停止前推，於 {tuple(u['pos'])} "
                                f"就地構築工事並固守"))
        ev.append(("allies", "BLU-AD 新令生效：目標改為 (13,5)（原 (12,5) 作廢），"
                             "08-26 06:00 起行軍；在此之前續於 (8,7) 構築工事"))
        for uid, dst in NEW_DEST.items():
            ev.append((uid, f"{uid} 新令生效：前進偵察 → {tuple(dst)}，抵達後偽裝作業"))

    after = gh >= NEW_GH
    dest = dict(OLD_DEST)
    dig = set(OLD_DIG)
    if after:
        dest.update(NEW_DEST)
        for uid in HALT_AND_DIG:
            if uid in frozen_pos:
                dest[uid] = tuple(frozen_pos[uid])
        dig |= set(HALT_AND_DIG)

    for uid, dst in dest.items():
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid):
            continue
        if list(u["pos"]) == list(dst):
            if after and uid in NEW_CAMO:
                m = tk.try_camouflage(s, uid)
            elif uid in dig:
                m = tk.try_dig(s, uid)
            else:
                m = None
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
        per = w / max(u.get("personnel", 1), 1)
        camo = "偽裝完成" if u.get("camouflaged") else (
            f"偽裝{u.get('camo_hours',0):.1f}" if u.get("camo_hours") else "")
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 疲勞 {u.get('fatigue',0):>3}"
              f" {ar.fort_tier(u.get('fortification',0.0))[3]:4} ({per:5.2f}hr/人)"
              f" {u['visibility_state']:12} {camo}")
    print(f"  指揮：{ar.cp_line(s, side)}")
print()
print("偵獲：藍→", s["fog_of_war"].get("allies_spotted"))
print("　　　紅→", s["fog_of_war"].get("axis_spotted"))

snap = HERE / "snap_T4start.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 快照 {snap}")
