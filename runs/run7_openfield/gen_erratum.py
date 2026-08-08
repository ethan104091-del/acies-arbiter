#!/usr/bin/env python3
"""Run 7 終局戰報勘誤第一號 — 協同倍率（發雙方，逐位元組相同）。

## 為什麼要發

手冊 §8 告訴雙方「兵種協同 3 種以上 ＝ 1.5」，而引擎對 4 種以上用的是 **1.7**。
兩份手冊逐位元組相同、錯得一樣，但**只有一方實際觸發過 4 兵種**——
資訊上對稱，效果上不對稱。這種情形已於 `law/precedents.md` §二十二 附記
被定性為瑕疵（「對稱的程序不保證對稱的結果」），故必須告知。

## 所有數字自 final_state.json 的日誌抽取，不手抄

手抄過的東西這一局已經錯了十二次。gh48／gh50 的兩行日誌是引擎當時寫下的原文，
本檔只解析它、重算替代兵力比，不重新輸入任何數字。
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import arbiter as ar          # noqa: E402

DEST = {"allies": Path.home() / "Desktop" / "料鋒_Run7_藍軍指揮部",
        "axis": Path.home() / ".acies" / "run7_red_hq"}
ZH = {"allies": "藍軍", "axis": "紅軍"}

s = ar.load(HERE / "final_state.json")

# ── 自日誌抽出所有 4 兵種以上的近戰解算 ─────────────────────────────
LINE = re.compile(
    r"攻方 CP ([\d.]+)（(\d+) 兵種、協同 ([\d.]+)）"
    r" vs 守方 CP ([\d.]+)（(\d+) 兵種")
GH = re.compile(r"\[gh(\d+)")


def scan():
    """回傳 {(gh, a_cp): (...)}，去重。

    同一場解算在**雙方日誌各記一次**、另有一份 summary，故必須以 (gh, 攻方CP)
    為鍵去重——★ 2026-08-08 的第一版勘誤稿曾以 grep 原始日誌行數計次，
    因此把 2 場報成 12 次。計數也要自 state 產生，不能用 grep。

    日誌是累積的（不逐 tick 清空），故 final_state 已含全局；
    仍併掃快照以防某個 tick 的日誌被裁剪。"""
    out = {}
    logs = list(s["hour_log_side"].values()) + [s.get("hour_log", [])]
    for f in sorted(HERE.glob("snap_T*start.json")):
        _s = json.loads(f.read_text())
        logs += list(_s.get("hour_log_side", {}).values()) + [_s.get("hour_log", [])]
    for lst in logs:
        for ev in lst:
            txt = ev if isinstance(ev, str) else json.dumps(ev, ensure_ascii=False)
            m, g = LINE.search(txt), GH.search(txt)
            if not (m and g):
                continue
            a_cp, a_arms, a_mult, d_cp, d_arms = m.groups()
            out[(int(g.group(1)), a_cp)] = (float(a_cp), int(a_arms), float(a_mult),
                                            float(d_cp), int(d_arms))
    return out


ALL = scan()
BIG = {k: v for k, v in sorted(ALL.items()) if v[1] >= 4}
if not BIG:
    sys.exit("找不到 4 兵種以上的解算——勘誤無標的，請先確認日誌格式")

DOC_MULT = 1.5          # 手冊 §8 所載「3 種以上」的值


def fr_band(fr):
    """回傳該兵力比落在 FR_TABLE 的哪一列（astr, aorg, dstr, dorg, push）。"""
    for cap, astr, aorg, dstr, dorg, push in ar.FR_TABLE:
        if fr < cap:
            return astr, aorg, dstr, dorg, push
    raise AssertionError


def band_row(fr):
    astr, aorg, dstr, dorg, push = fr_band(fr)
    return (f"攻方 −{astr}% 戰力／−{aorg} 組織、守方 −{dstr}% 戰力／−{dorg} 組織、"
            + (f"**逼退 {push} 格**" if push > 0 else
               "**攻方被逼退**" if push < 0 else "**不逼退**"))


def t_engine_vs_doc():
    rows = ["| 兵種數 | 引擎（實際解算所用） | 手冊 §8 與規格書 §XI（更正前） |",
            "|---:|---:|---:|"]
    for n in range(1, 6):
        eng = ar.COMBINED.get(n, 1.7)
        doc = ar.COMBINED.get(n, DOC_MULT)
        mark = "" if abs(eng - doc) < 1e-9 else "　← **不符**"
        rows.append(f"| {n} | **{eng}** | {doc}{mark} |")
    return "\n".join(rows)


def t_occurrences():
    rows = ["| gh | 攻方 CP | 攻方兵種 | 守方 CP | 守方兵種 | 兵力比 |",
            "|---:|---:|---:|---:|---:|---:|"]
    for (gh, _), (a, aa, am, d, da) in BIG.items():
        rows.append(f"| {gh} | {a:.1f} | {aa} 種 ×{am} | {d:.1f} | {da} 種 | {a/d:.2f} |")
    return "\n".join(rows)


def t_recompute():
    """對每一場 4 兵種解算，重算「若引擎照手冊的 1.5」會落在哪一列。"""
    rows = ["| gh | 讀法 | 攻方 CP | 兵力比 | 對照表 |", "|---:|---|---:|---:|---|"]
    for (gh, _), (a, aa, am, d, da) in BIG.items():
        fr0 = a / d
        a1 = a * DOC_MULT / am
        fr1 = a1 / d
        rows.append(f"| {gh} | 實際（×{am}） | {a:.1f} | **{fr0:.2f}** | {band_row(fr0)} |")
        rows.append(f"| {gh} | 若照手冊（×{DOC_MULT}） | {a1:.1f} | **{fr1:.2f}** | {band_row(fr1)} |")
    return "\n".join(rows)


def changed_ghs():
    """哪幾場的「對照表那一列」會因讀法不同而改變。"""
    out = []
    for (gh, _), (a, aa, am, d, da) in BIG.items():
        if fr_band(a / d) != fr_band(a * DOC_MULT / am / d):
            out.append(gh)
    return out


CHANGED = changed_ghs()

TPL = """# Run 7 終局戰報　勘誤第一號

**協同倍率：手冊 §8 所載的數字與引擎實際使用的不符。**

> 本勘誤對紅藍兩軍**逐位元組相同**（除陣營字樣），由程式自終局狀態的日誌產生。
> 發布於 2026-08-08，Run 7 終局之後、Run 8 開局之前。

---

## 一、事實

{T_EVD}

**根因**：`COMBINED` 這個常數表**只有三個鍵**，第四級住在 `unit_cp` 的
`COMBINED.get(n, 1.7)` 預設值裡。手冊產生器 `gen_handbook.py` 是自引擎取值的
（這正是它存在的理由），但它取得到的就只有三級——**而「3 種以上」這四個字是手寫的。**

## 二、4 兵種不是罕見情況，這是本次錯誤真正的重量

協同依**編制內營種**計算（手冊 §8、規格書 §XI）：

- 裝甲師 ＝ {{戰車, 裝步, 砲兵}}
- 步兵師 ＝ {{戰車, 步兵, 砲兵}}
- 兩者聯合 ＝ {{戰車, 裝步, 步兵, 砲兵}} ＝ **四種**

**一個裝甲師與一個步兵師聯合攻擊即自動成立**，不需要工兵、不需要任何特殊編組。
手冊等於告訴雙方「裝甲配步兵，協同上不會比單獨一個師更好」——差 13%。

## 三、實際發生過幾次、在哪裡

**全局共 {N_ALL} 場近戰解算，其中 {N_BIG} 場為 4 兵種：**

{T_OCC}

戰霧已於終局解除，故上表對雙方完整顯示。

（全局近戰場數之所以只有 {N_ALL} 場：T0–T4 雙方未接觸；T6–T7 無地面戰；
且 T8 的逼退把守方逐出該格後，同一場近戰不再逐小時重複——那正是判例 §二十五
更正後的行為。）

## 四、可驗算的重算

把攻方的協同倍率換成手冊所載的 {DOC}，其餘一切不變：

{T_RE}

{CHANGED_NOTE}

## 五、認定：不追溯改判

**引擎的行為即為本局實際適用的規則。**

這與判例 §二十五（「守方後退 N 格」被實作成行軍）不同，必須說清楚差別：

| | §二十五 | 本項 |
|---|---|---|
| 性質 | **執行錯誤** —— 規則寫的是強制位移，裁判用了行軍函式 | **文件錯誤** —— 引擎四局未變，是規格書與手冊寫錯 |
| 處置 | 自快照重跑 T5–T8，計分由 2800:1400 更正為 1714:1116 | **不重跑、不改分** |
| 理由 | 引擎沒有照規則做 | 引擎一直照自己做的做；改判等於以文件推翻既成事實 |

## 六、必須一併說明的不對稱

兩份手冊逐位元組相同，**錯得完全一樣**。但實際觸發 4 兵種的只有一方——
另一方全局未曾以 4 兵種發起攻擊。**資訊上對稱，效果上不對稱。**

這與判例 §二十二 附記的「裁判主動查證的服務不對等」是同一類問題：
**對稱的程序不保證對稱的結果。** 裁判不主張本次錯誤是中立的，只主張它不是偏心的。

## 七、Run 8 之前已經做的事

1. `rules/arbiter_v2.md` §XI／§XII 已更正，並標明第四級住在 `.get` 預設值裡。
2. `rules/combined_arms_v1.md` §II 的「五兵種 1.85」判定不成立——引擎封頂 {CAP}，
   與判例 §四 G2「工兵投入→{CAP}（上限）」一致。5 兵種與 4 兵種同倍率。
3. 一致性測試已改為**解析規格書的表格逐級比對**（含 4、5、6 種），並驗證過
   它會抓到更正前的版本。原本寫的是「規格書裡出現過 1.5 這個字串嗎」——
   所以「3 以上 → 1.5」照樣通過。**逐字比對不是一致性檢查。**
4. 已列為兩局之間的待辦：凡以 `.get(k, 預設)` 表達的規則，
   該預設值必須在某個**可列舉**的常數裡有名字，否則手冊產生器永遠看不到它。

## 八、可自行驗證之處

- 判例：`law/precedents.md` §二十六
- 規格書：`rules/arbiter_v2.md` §XI
- 本勘誤的每個數字：由 `runs/run7_openfield/gen_erratum.py` 自
  `final_state.json` 的 `hour_log_side` 解析產生，可重跑比對

---

**{ZH_SELF}指揮官，這是裁判的錯，不是你的。一併致意。**
"""


def render(side):
    if CHANGED:
        note = ("> **上表有 " + str(len(CHANGED)) + " 場的「對照表那一列」因讀法不同而改變"
                "（gh " + "、".join(str(g) for g in CHANGED) + "）。**\n>\n"
                "> 也就是說：依手冊公布的數字計算，這幾場的兵力比會落在不同的區間，"
                "傷亡百分比與是否逼退都不同。\n"
                "> 而「逼退」正是判例 §二十五 之後 T8 追擊得以繼續的前提。")
    else:
        note = ("> 上表每一場的「對照表那一列」都相同——兩種讀法雖然兵力比不同，"
                "但落在同一個區間，故本次錯誤未改變任何一場的解算結果。")
    return TPL.format(
        T_EVD=t_engine_vs_doc(), T_OCC=t_occurrences(), T_RE=t_recompute(),
        N_ALL=len(ALL), N_BIG=len(BIG), DOC=DOC_MULT, CAP=ar.COMBINED.get(9, 1.7), CHANGED_NOTE=note,
        ZH_SELF=ZH[side])


def norm(t):
    for a, b in (("藍", "§"), ("紅", "§"), ("BLU", "¤"), ("RED", "¤")):
        t = t.replace(a, b)
    return t


out = {}
for side, d in DEST.items():
    d.mkdir(parents=True, exist_ok=True)
    txt = render(side)
    (d / "終局戰報_勘誤第一號.md").write_text(txt)
    out[side] = txt
    print(f"  {ZH[side]} → {d / '終局戰報_勘誤第一號.md'}（{len(txt.splitlines())} 行）")

if norm(out["allies"]) == norm(out["axis"]):
    print("\n✅ 兩份勘誤正規化後逐位元組相同")
else:
    import difflib
    dif = [l for l in difflib.unified_diff(norm(out["allies"]).split("\n"),
                                           norm(out["axis"]).split("\n"),
                                           lineterm="", n=0)
           if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    print(f"\n❌ 有 {len(dif)} 行差異：" + " / ".join(x[:70] for x in dif[:5]))
    sys.exit(1)
