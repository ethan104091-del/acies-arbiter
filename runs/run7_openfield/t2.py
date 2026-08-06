#!/usr/bin/env python3
"""Run 7 — Tick 2 解算（gh12–gh17，1944-08-25 18:00–23:00）。

## 第一個跨進夜間的 tick

    gh12 18:00 黃昏 ── gh13 19:00 起入夜
    夜間效應：行軍疲勞 +8/hr（白天 +5）、移動 ×0.5、視距縮短
              （師 3→2、特戰 4→3、偵察 5→3）、落彈分析可 flash-to-bang 測距 ±1 格

## 雙方的 T2 命令都是「維持原命令」

- **紅軍**：明文「維持命令_T0.md 與命令_T1.md 的所有常設命令」。不重下＝零延遲。
- **藍軍**：機動一條都不重下（理由是夜間行軍會讓四個師帶著高疲勞抵達戰場）；
  唯一新增的是**射擊准駁的時段規則**，寫在應變欄，本 tick 不觸發（見下）。

**兩軍本 tick 皆無火力任務**，因為射程不足：
已偵獲的 RED-2-rcn (16,8)、RED-3-rcn (16,3) 距藍軍最近的有砲編隊逾 8 格，
而火砲最大射程 4 格（155mm）。紅軍的偵獲清單為空，其應變的射擊條件不成立。
故本 tick 不會有任何 `bombard` 呼叫，裁示 58／59 尚無適用機會。

## 構築工事的適用對象（判例 §二十一：必須逐一列舉並註明命令出處）

| 編隊 | 命令出處 |
|---|---|
| BLU-1／2／3／AD／SF | 藍 T0 第 2–6 條「抵達後…構築工事」 |
| BLU-2-rcn／BLU-3-rcn | 藍 T0 第 7 條「抵達後構築工事、就地不動」 |
| BLU-2-3-r6 | 藍 T0 第 8 條「抵達後固守該格並構築工事」 |
| BLU-2-1-r6／2-r6／3-r5 | 藍 T1 第 1 條「抵達後固守該格並構築工事」 |
| RED-2 | 紅 T1 第 2 條「抵達後構築至散兵壕」 |
| RED-2-1-r4 | 紅 T1 第 2 條「固守並構築工事至有頂蓋級」 |
| RED-2-2-r4 | 紅 T1 第 2 條「固守並構築工事至散兵壕級」 |

**不在此表者一律不挖**——紅軍 T0 全部使用「戰備推進／行軍縱隊／隱蔽滲透／前進偵察」，
未下構工令（RED-AD、RED-1、RED-3、RED-SF、兩支 rcn）。
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
assert s["global_hour"] == 12, f"t2.py 只能從 gh12 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)
ZH = {"allies": "藍軍", "axis": "紅軍"}

# ── T2 無新命令（雙方皆「維持原命令」）→ 不入佇列、不吃延遲 ──────────

DEST = {   # 常設命令的目的地（T0／T1 下達，未被取代）
    "BLU-1": (7, 2), "BLU-2": (7, 5), "BLU-3": (7, 10), "BLU-AD": (8, 7),
    "BLU-SF": (11, 1), "BLU-2-rcn": (13, 6), "BLU-3-rcn": (9, 13),
    "BLU-2-3-r6": (6, 4), "BLU-2-1-r6": (6, 4), "BLU-2-2-r6": (6, 4),
    "BLU-2-3-r5": (6, 4),
    "RED-1": (20, 12), "RED-2": (20, 9), "RED-3": (20, 3), "RED-AD": (20, 10),
    "RED-SF": (18, 15), "RED-2-rcn": (16, 8), "RED-3-rcn": (16, 3),
    "RED-2-1-r4": (29, 8), "RED-2-2-r4": (22, 9),
}
DIG = {    # 判例 §二十一：逐一列舉，不得由 DEST 推導
    "BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-SF",
    "BLU-2-rcn", "BLU-3-rcn", "BLU-2-3-r6",
    "BLU-2-1-r6", "BLU-2-2-r6", "BLU-2-3-r5",
    "RED-2", "RED-2-1-r4", "RED-2-2-r4",
}
halted = {}


def contingency(s, gh, ev):
    """雙方應變條款。本 tick 預期不觸發，仍逐條檢查。

    藍軍第一條：整編師遭砲擊或 ≤3 格內偵獲敵師級 → 就地停止並構工。
    藍軍最後一條（前進觀測所）：已在森林格者不撤離、就地固守續構工。
    紅軍前兩條：HQ 守備營 ≤3 格內偵獲敵戰鬥編隊 → 停止構築、固守、回報。
    紅軍第三條：RED-AD 偵獲敵裝甲師在 4 格內 → 停止行軍、向 RED-2 靠攏。
    """
    for side in ("allies", "axis"):
        seen = tk.spotted(s, side)
        for uid, u in ar.own(s, side).items():
            if uid not in DEST or u.get("is_detachment"):
                continue
            near = [e for e in seen
                    if e in s["units"] and tk.is_division(s["units"][e])
                    and ar.dist(u["pos"], s["units"][e]["pos"]) <= 3]
            hit = u["flags"].get("hit")
            if (near or hit) and uid not in halted:
                halted[uid] = gh
                ev.append((uid, f"{uid} 應變觸發："
                                f"{'遭砲擊' if hit else '≤3 格內偵獲敵師級 ' + near[0]}"
                                f"，就地停止行軍並構築工事"))
            elif uid in halted and not near and not hit and gh - halted[uid] >= 2:
                halted.pop(uid)
                ev.append((uid, f"{uid} 連續 2 小時無接觸，恢復執行常設命令"))


def resolve(s, gh):
    ev = []
    if gh == 13:
        ev.append(("both", "★ 日落。自本小時起為夜間：行軍疲勞 +8/hr、移動 ×0.5、"
                           "視距縮短（師 3→2、特戰 4→3、偵察 5→3）；"
                           "落彈分析可由 flash-to-bang 測距至 ±1 格"))
    contingency(s, gh, ev)
    for uid, dst in list(DEST.items()):
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid):
            continue
        if uid in halted or list(u["pos"]) == list(dst):
            if uid in DIG:
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
        per = w / max(u.get("personnel", 1), 1)
        tier = ar.fort_tier(u.get("fortification", 0.0))[3]
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 疲勞 {u.get('fatigue',0):>3}"
              f" {tier:4} ({per:.2f}hr/人) POL {u.get('resources',{}).get('POL',0):>5.1f}"
              f" {u['visibility_state']}")
    print(f"  指揮：{ar.cp_line(s, side)}")
    print(f"  守備：{ar.cp_garrison(s, side)}")
print()
print("偵獲：藍→", s["fog_of_war"].get("allies_spotted"))
print("　　　紅→", s["fog_of_war"].get("axis_spotted"))

snap = HERE / "snap_T3start.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 快照 {snap}")
