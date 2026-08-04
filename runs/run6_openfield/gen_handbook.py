#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════════════════
# ⚠️  這支腳本產生的是 **Run 6** 的手冊，屬歷史工具。**不得直接沿用於 Run 7。**
#
# 其內容自 Run 6 結束後已有多處失效：
#   · §11 工事 —— 仍寫「移動或潰散即棄工事，挖好的洞帶不走」。
#     Run 7 起工事記在**格子**上，離開再回來即完整取用；該句現在只對偽裝成立。
#     另新增砲擊摧毀工事（22.6 man-hr／殺傷單位）與 man-hours 制。
#   · 彈藥 —— 舊制為百分比、永遠打不完。Run 7 起為實數發數，一個基數約一個 tick。
#   · 未載入的裁示：17 偽裝作業、18 行軍中不得砲擊、25 落彈分析、32 戰術狀態逐時判定。
#
# **Run 7 的手冊須依 `rules/arbiter_v2.md` 重新撰寫**（該檔為上列全部機制的規範住址，
# 且與引擎的一致性由 tests/test_status_machine.py 的 L 段驗證）。
#
# 本檔保留不改，因為它是 Run 6 玩家實際依據之手冊的產生器——
# 改它會使 hq_allies/ 與 hq_axis/ 裡的手冊無法被重新產出、也就無法被稽核。
# ══════════════════════════════════════════════════════════════════════════
"""Run 6 雙方指揮官手冊 — 單一模板產出，程式驗證兩份正規化後一字不差。

沿用 Run 4 的本體（_tpl_head/_tpl_tail）＋ Run 5 的新增規則（_new.txt）
＋ 本檔的 Run 6 修正段。依 law_of_war.md §0.1，本手冊即禁令表的公佈，T0 前送達雙方。

★ Run 6 的差別：藍軍由**人類指揮官**執掌，紅軍由 AI agent 執掌。
  規則兩邊一字不差；裁判對雙方的資訊紀律完全相同。
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEAD = (HERE / "_tpl_head.txt").read_text()
RUN5 = (HERE / "_new.txt").read_text()
TAIL = (HERE / "_tpl_tail.txt").read_text()
PROC = (HERE / "_proc.txt").read_text()
ORDER_TPL = (HERE / "_order.txt").read_text()

RUN6 = """
---

# ★★ Run 6 規則修正（依 Run 5 的判例，T0 前公佈，其後凍結）

Run 5 終局 **紅軍 237 : 藍軍 171**，54 小時、雙方主力零接觸、零地面戰、零戰車損失，
408 分全部來自彼此的偵察幕。覆盤查出的三項缺陷已修正如下。
Run 5 的完整戰史（終局總結、事實紀錄、敗方覆盤）已同時放進雙方資料夾，兩份相同。

## 修正 A — 抽離的營級單位現在會計算補給走廊

`compute_supply` 原本跳過所有抽離的營級單位，使其補給狀態永遠沿用「完整」。
與 W1 要件 C（補給走廊切斷）相乘的結果是：**任何營級單位都不可能滿足 W1**，
不論它被摧毀得多徹底。「禁止在屍體上收割殺傷分數」恰好對最容易變成屍體的
那一類單位失效。**現已修正：抽離營與師級一樣逐格計算走廊。**

**W1 的三要件本身不變**（維持 A 且 B 且 C）。Run 5 敗方在覆盤中主張要件 C 是對的：
W1 的合法替代是「停火並維持包圍」，其正當性正是該編隊**無法脫離**；
一個能撤走的單位不是屍體。裁判接受此論證，故不放寬要件 C。

## 修正 B — 前進指揮所必須「真的在前」

原本只檢查「軍長是否進駐」與「距離 ≤ 6 格」，**沒有任何位置要求**。
Run 5 有一方因此把前進指揮所設在自己**後方縱深的森林格**（重兵守備），
零斬首風險取得 0 級延遲——使「節奏優勢 ↔ 斬首風險」完全脫鉤。

**新判準**：前進指揮所須位於**本方各作戰編隊 x 座標的中位數之前**（朝敵方補給源的方向）。
藍軍補給源在西緣 x=0，故「前」＝ x 較大；紅軍相反。不滿足者不給 0 級，退回 +1 級。

用「自己部隊的中位數」而非「距敵方多近」，是因為後者依賴戰霧
（雙方看到的敵情不同 → 判準不對稱）；中位數是雙方都能自行驗算的客觀量。

## 修正 C — 新增「攔阻射擊」：可以對格面開火，不需偵獲

Run 5 的裁示 58 是「完全未偵獲者不得射擊」，因為引擎只能對「目標編隊」開火。
後果是**打掉對方的眼睛比打對方主力更有效率**（Run 5 勝方 237 分全來自此機制）。
但史實上 1944 年砲兵確實會對疑似位置實施攔阻與擾亂射擊，所以那是引擎缺陷。

**新規則**：可以指定**一個格子**實施攔阻射擊，不需該格有已偵獲的敵編隊。

| | |
|---|---|
| 命令寫法 | `攔阻射擊 (x,y) BY <編隊>`（可多個編隊，逗號分隔） |
| 效果 | 若該格確有敵編隊 → 照常解算，但**每發殺傷力 ×0.30**（無觀測校射） |
| 該格無敵編隊 | 效果為零，**彈藥與暴露照付** |
| 代價 | 開火方該小時一律標記為**已開火 → EXPOSED**（暴露自己的位置） |

所以攔阻射擊適合壓制與擾亂，不適合當主要殲敵手段；而且它會讓你的砲兵被看見。

**對戰爭法的影響**：裁示 58 的「本局無盲目彈幕」自 Run 6 起**失效**。
但 W1／W2 的**明知**要件不變——你若主張對手違法，仍須證明戰報向其顯示過該狀態。
反面：對一個你**未偵獲**的編隊實施攔阻射擊而恰好命中，因為你不明知，**不構成 W1**。

---
"""

SIDES = [
    dict(SIDE="allies", ZH="藍", EZH="紅", P="BLU", EP="RED",
         MY_EDGE="西緣 x=0", out="藍軍指揮官手冊.md", proc="00_讀我.md",
         order="命令_T0.md", diary="藍軍作戰日誌.md"),
    dict(SIDE="axis", ZH="紅", EZH="藍", P="RED", EP="BLU",
         MY_EDGE="東緣 x=29", out="紅軍指揮官手冊.md", proc="00_讀我.md",
         order="命令_T0.md", diary="紅軍作戰日誌.md"),
]
DEST = {
    "allies": Path.home() / "Desktop" / "料鋒_Run6_藍軍指揮部",
    # 紅軍由使用者自己的 codex 執掌，故必須在 codex 讀寫得到的路徑；
    # 刻意**不放桌面**——藍軍指揮官（人類）就在桌面工作，放桌面等於天天看見敵方資料夾。
    "axis": Path.home() / ".acies" / "run6_red_hq",
}

if __name__ == "__main__":
    tpl = HEAD + RUN5 + RUN6 + TAIL
    outs, procs, orders = {}, {}, {}
    for cfg in SIDES:
        d = DEST[cfg["SIDE"]]
        d.mkdir(parents=True, exist_ok=True)
        outs[cfg["SIDE"]] = tpl.format(**cfg)
        (d / cfg["out"]).write_text(outs[cfg["SIDE"]])
        procs[cfg["SIDE"]] = PROC.format(**cfg)
        (d / cfg["proc"]).write_text(procs[cfg["SIDE"]])
        orders[cfg["SIDE"]] = ORDER_TPL.format(**cfg)
        if not (d / cfg["order"]).exists():
            (d / cfg["order"]).write_text(orders[cfg["SIDE"]])
        if not (d / cfg["diary"]).exists():
            (d / cfg["diary"]).write_text(f"# {cfg['ZH']}軍作戰日誌\n\n（你自己的紀錄。裁判不讀、不評分。）\n")
        print("✅", d)

    def norm(x, cfg):
        for k, v in (("ZH", "§我"), ("EZH", "§敵"), ("P", "§M"), ("EP", "§E"),
                     ("SIDE", "§SIDE")):
            x = x.replace(cfg[k], v)
        return x.replace("西緣 x=0", "§EDGE").replace("東緣 x=29", "§EDGE")

    import difflib
    for label, bag in (("手冊", outs), ("讀我", procs), ("命令樣板", orders)):
        ra, rb = bag["allies"].splitlines(), bag["axis"].splitlines()
        na = norm(bag["allies"], SIDES[0]).splitlines()
        nb = norm(bag["axis"], SIDES[1]).splitlines()
        if len(ra) != len(rb):
            print(f"❌ {label} 行數不同"); raise SystemExit(1)
        # 原始行相同者一律放過：那是**絕對事實**（歷史結果、地理方位），
        # 兩份檔案裡本來就一字不差，只是正規化器會把陣營名替換成不同的字。
        bad = [(i, x, y) for i, (x, y, u, v) in enumerate(zip(na, nb, ra, rb))
               if x != y and u != v]
        if bad:
            print(f"❌ {label}不對稱：")
            for i, x, y in bad[:10]:
                print(f"   行 {i+1}\n   - {x}\n   + {y}")
            raise SystemExit(1)
    print("✅ 對稱驗證通過：手冊、讀我、命令樣板逐行相同"
          "（絕對事實行以原始位元組比對）")
