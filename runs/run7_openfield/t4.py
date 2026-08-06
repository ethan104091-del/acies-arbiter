#!/usr/bin/env python3
"""Run 7 — Tick 4 解算（gh24–gh29，1944-08-26 06:00–11:00，白天）。

## 藍軍的行程表在 gh24 啟動 —— 全軍離開有頂蓋工事東進

T0／T1／T3 的常設命令都寫著「自 1944-08-26 06:00 起續行」，那就是 gh24。
四個師與特戰旅同時開拔，**離開的那一刻工事歸零**（`abandon_works`：人不在洞裡），
且開闊地行軍為 EXPOSED、彈著覆蓋率是靜止的三倍。它拿全軍有頂蓋＋疲勞 0 去換十二格。

## 兩軍的新命令與生效時刻

| 方 | 命令 | 級別 | 階梯 | 生效 |
|---|---|---|---|---|
| 紅 | 前進指揮所前移至 (20,9)（RED-2 所在格） | L1 | +1 | gh26 下令生效 → **gh28 啟用** |
| 藍 | 五個編隊常設命令整條改寫＋抽離五個砲兵營 | L2 | +1 | **gh27** |

**紅軍此舉修掉了它自己的失格問題。** 舊前進指揮所 (22,9) 的 x=22 大於其整編編隊
x 中位數 20，`fwd_cp_is_forward` 不通過 → 全軍仍 +1 級（付了斬首風險、零收益）。
新址 (20,9) x=20 ≤ 20 通過，且該格有 **RED-2 整編師**駐守（非一個營）。
裁判於 T3 把 `cp_line` 由「+見說明」改為明列驗算結果——紅軍據此修正，資訊來自
程式產生的戰報，雙方對稱。

**前進指揮所遷址期間的處理：** `establish_cp` 於 gh26 排入、`CP_SETUP_HOURS=2` 後於 gh28
啟用並覆寫 `fwd_cp`。故 gh24–27 舊址 (22,9) 仍為現行前進指揮所、軍長仍在該處；
gh28 起新址生效、軍長進駐。那兩小時的架設期即代表軍長與通信班的移動（裁示 42）。
遷址後 RED-2-2-r4 仍依其常設命令固守 (22,9)，但該格已不再是指揮所。

## 藍軍的作業順序改為「先偽裝後挖」

新命令（gh27）把抵達後的順序由「先挖後偽裝」改為「**先偽裝至完成，再構築工事**」。
依裁示 62，師級偽裝為**編隊工時 3 小時**（不按人數）。各師約 gh33 才抵達（T5），
故本 tick 不會執行到偽裝段。

## 構築工事／偽裝的適用對象（判例 §二十一：逐一列舉並註明命令出處）

| 編隊 | 作業 | 命令出處 |
|---|---|---|
| BLU-2 之 1-r6／2-r6／3-r5／3-r6（(6,4)） | 構工 | 藍 T0 第 8、T1 第 1 條 |
| BLU-2-rcn (13,6)／BLU-3-rcn (9,13) | 構工 | 藍 T0 第 7 條 |
| BLU-1／2／3／AD／SF（抵達後） | gh27 起改**先偽裝** | 藍 T4 第 1–5 條 |
| 藍軍新抽離的五個砲兵營 | 構工 | 藍 T4 第 1、3、4 條 |
| RED-1／2／3／AD | 構工 | 紅 T3 第 1–4 條 |
| RED-2-1-r4 (29,8)／RED-2-2-r4 (22,9) | 構工 | 紅 T3 第 5–6 條 |
| RED-2-rcn／RED-3-rcn（抵達後） | **偽裝** | 紅 T3 第 7–8 條 |

RED-SF 至今未獲任何構工或偽裝令，僅固守 (18,15)（其 CAMOUFLAGED 來自特戰兵種加成，非作業）。
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
assert s["global_hour"] == 24, f"t4.py 只能從 gh24 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)
ZH = {"allies": "藍軍", "axis": "紅軍"}

NEW = [
    ("axis", "L1", "建立前進指揮所 (20,9)（RED-2 所在格），啟用後軍長進駐"),
    ("allies", "L2", "BLU-1 整條改寫：→ (13,3)，抵達後先偽裝至完成再構工；抽離 a1、a2 同駐"),
    ("allies", "L2", "BLU-2 整條改寫：→ (13,3) 與 BLU-1 同駐，抵達後先偽裝再構工"),
    ("allies", "L2", "BLU-AD 整條改寫：→ (13,5)，抵達後先偽裝再構工；抽離 sp1 同駐"),
    ("allies", "L2", "BLU-3 整條改寫：→ (13,8)，抵達後先偽裝再構工；抽離 a1、a2 同駐"),
    ("allies", "L2", "BLU-SF 整條改寫：→ (15,1)，抵達後先偽裝再構工，固守觀測"),
]
for side, lv, txt in NEW:
    hs.enqueue_order(s, side, lv, txt,
                     extra_delay=command.delay_tier_adjust(s, side, [0, 0]))

RED_CP_GH = 24 + 1 + 1        # gh26：紅軍 L1 生效 → 開始架設
BLU_NEW_GH = 24 + 2 + 1       # gh27：藍軍 L2 生效

DEST = {
    # 藍軍：常設命令的 08-26 06:00 段落自 gh24 起啟動
    "BLU-1": (13, 3), "BLU-2": (13, 3), "BLU-AD": (13, 5), "BLU-3": (13, 8),
    "BLU-SF": (15, 1),
    "BLU-2-rcn": (13, 6), "BLU-3-rcn": (9, 13),
    "BLU-2-3-r6": (6, 4), "BLU-2-1-r6": (6, 4), "BLU-2-2-r6": (6, 4),
    "BLU-2-3-r5": (6, 4),
    # 紅軍：全部就地（T3 命令），偵察隊續推
    "RED-1": (20, 12), "RED-2": (20, 9), "RED-3": (20, 3), "RED-AD": (20, 10),
    "RED-SF": (18, 15), "RED-2-rcn": (13, 8), "RED-3-rcn": (13, 3),
    "RED-2-1-r4": (29, 8), "RED-2-2-r4": (22, 9),
}
DIG = {   # 明確下令構築工事者
    "BLU-2-3-r6", "BLU-2-1-r6", "BLU-2-2-r6", "BLU-2-3-r5",
    "BLU-2-rcn", "BLU-3-rcn",
    "RED-1", "RED-2", "RED-3", "RED-AD", "RED-2-1-r4", "RED-2-2-r4",
}
CAMO = {"RED-2-rcn", "RED-3-rcn"}          # 紅 T3 第 7–8 條
# gh24–26：舊命令為「抵達後構築工事」；gh27 起改為「先偽裝至完成，再構工」
BLU_MAIN = ("BLU-1", "BLU-2", "BLU-AD", "BLU-3", "BLU-SF")
BLU_DET = [("BLU-1", "a1"), ("BLU-1", "a2"), ("BLU-3", "a1"), ("BLU-3", "a2"),
           ("BLU-AD", "sp1")]
DET_DEST = {"BLU-1": (13, 3), "BLU-3": (13, 8), "BLU-AD": (13, 5)}
done = {"red_cp": False, "det": set(), "red_cp_live": False}


def resolve(s, gh):
    ev = []

    # 紅軍前進指揮所遷址
    if gh >= RED_CP_GH and not done["red_cp"]:
        eff = command.establish_cp(s, "axis", "fwd", [20, 9])
        done["red_cp"] = True
        ev.append(("axis", f"命令生效：於 (20, 9) 開始架設前進指揮所"
                           f"（{command.CP_SETUP_HOURS}hr，gh{eff} 啟用）。"
                           f"該址 x=20 ≤ 本方整編編隊 x 中位數，驗算可通過；"
                           f"啟用前 (22, 9) 仍為現行前進指揮所"))
    if not done["red_cp_live"] and list(s["command"]["axis"].get("fwd_cp") or []) == [20, 9]:
        done["red_cp_live"] = True
        ok = command.fwd_cp_is_forward(s, "axis")
        ev.append(("axis", f"前進指揮所遷至 (20, 9) 並啟用，軍長進駐（該格由 RED-2 整編師掩護）；"
                           f"「真的在前」驗算 {'✅ 通過 → 其 6 格內編隊享 0 級延遲' if ok else '❌ 未通過'}；"
                           f"舊址 (22, 9) 已不再是指揮所"))

    # 藍軍新命令生效：抽離五個砲兵營
    if gh >= BLU_NEW_GH:
        for parent, code in BLU_DET:
            key = f"{parent}-{code}"
            if key in done["det"] or parent not in s["units"]:
                continue
            uid, det = ar.detach_bn(s, parent, code, list(s["units"][parent]["pos"]))
            done["det"].add(key)
            DEST[uid] = DET_DEST[parent]
            DIG.add(uid)
            p = s["units"][parent]
            ev.append((parent, f"{parent} 抽離 {uid}（{det.get('personnel',0)} 人、"
                               f"火砲 {det['equip']['guns']}）於 {tuple(det['pos'])}，"
                               f"任務：隨母師至 {tuple(DET_DEST[parent])} 同駐、構工待命；"
                               f"母師餘火砲 {p['equip']['guns']}"))

    camo_first = gh >= BLU_NEW_GH        # gh27 起藍軍主力抵達後先偽裝

    for uid, dst in list(DEST.items()):
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid):
            continue
        if list(u["pos"]) != list(dst):
            _, m = ar.advance(s, uid, list(dst))
            ev.append((uid, m))
            continue
        # 已在目的地 → 依命令執行作業
        m = None
        if uid in CAMO:
            m = tk.try_camouflage(s, uid)
        elif uid in BLU_MAIN and camo_first and not u.get("camouflaged"):
            m = tk.try_camouflage(s, uid)
        elif uid in DIG or uid in BLU_MAIN:
            m = tk.try_dig(s, uid)
        if m:
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
        camo = "偽裝✓" if u.get("camouflaged") else (
            f"偽{u.get('camo_hours',0):.1f}" if u.get("camo_hours") else "")
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 疲{u.get('fatigue',0):>3}"
              f" {ar.fort_tier(u.get('fortification',0.0))[3]:4}({per:5.2f})"
              f" 砲{u['equip']['guns']:>3} {u['visibility_state']:12} {camo}")
    print(f"  指揮：{ar.cp_line(s, side)}")
print()
print("偵獲：藍→", s["fog_of_war"].get("allies_spotted"))
print("　　　紅→", s["fog_of_war"].get("axis_spotted"))

snap = HERE / "snap_T5start.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 快照 {snap}")
