#!/usr/bin/env python3
"""把一個 tick 的全部材料合成**單一檔案**發給雙方 — `docs/TODO.md` Run 7 開局前必做 #2。

## 為什麼存在

Run 6 的八個 tick，有**六次** codex 讀完檔案就用完回合預算、沒寫出命令，每次都要
壓縮閱讀清單重啟。觀察到的規律：**寫檔前讀超過約兩個檔案就會爆。**
而 Run 6 的指揮部目錄一個 tick 要讀四到五個檔（戰報、裁示、上回命令、手冊某節）。

本檔把該 tick 需要的一切壓成一個 `本回簡報.md`：態勢＋敵情＋落彈分析＋計分
＋本回新裁示＋命令樣板。**AI 指揮官只需讀一個檔、寫一個檔。**

## 公平性（feedback_wargame_referee_leaks 四條硬規則）

1. **單方內容一律由 `arbiter.brief_md()` 產生，裁判不手寫。** 本檔只做拼接。
2. 裁示分兩類：`shared/` 之下的對雙方**逐位元組相同**（本檔會驗證）；
   `to_allies/`、`to_axis/` 之下的只送該方（裁示 7：對一方自身命令的解讀只回該方）。
3. 產生後自動比對兩份簡報的**共用段落**必須相同。
4. 裁判日誌、上帝視角、對手目錄一律不進簡報。

## 用法

    python3 runs/run7_openfield/dispatch.py 0        # 發 T0 簡報
    python3 runs/run7_openfield/dispatch.py 3        # 發 T3 簡報

裁示放法：
    runs/run7_openfield/rulings/shared/03_xxx.md     → 雙方都拿到（須完全相同）
    runs/run7_openfield/rulings/to_allies/03_xxx.md  → 只有藍軍拿到
    runs/run7_openfield/rulings/to_axis/03_xxx.md    → 只有紅軍拿到
（檔名前兩位＝該裁示屬於哪個 tick。）
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import arbiter as ar          # noqa: E402
import command                # noqa: E402

# 藍軍＝人類另開的 AI 指揮官（桌面資料夾）；紅軍＝codex（沿用 Run 6 的 ~/.acies）。
# 人類此局觀戰，不擔任指揮官。
#
# 路徑位置不對稱不構成不公平——**該對稱的是內容與工具**：
# 同一份手冊、同一種單檔簡報、同一個命令樣板、同樣的可用動作集。
# 那些由 gen_handbook.py 與 dispatch.py 在產生時逐位元組驗證。
DEST = {
    "allies": Path.home() / "Desktop" / "料鋒_Run7_藍軍指揮部",
    "axis": Path.home() / ".acies" / "run7_red_hq",
}
ZH = {"allies": "藍", "axis": "紅"}
PFX = {"allies": "BLU", "axis": "RED"}
RULINGS = HERE / "rulings"

HEAD = """# {ZH}軍 · Tick {n} 本回簡報

> **你只需要讀這一個檔案，然後寫 `命令_T{n}.md`。**
> 規則細節在 `{ZH}軍指揮官手冊.md`，但除非你要查具體係數，不必重讀。

## 本回三個提醒

1. **命令延遲是規則。** 現在下的令要 1–5 小時後才生效（看你有沒有指揮所）。
   要某動作在某時刻已在執行，必須**提前一個 tick** 下令。
2. **命令是常設的。** 上一回的命令仍在執行；**不重下＝零延遲**，重下要重新等一次延遲。
3. **彈藥會打完**（一個基數約一個 tick 的連續射擊，每 tick 只補 40%）。
   **工事會被打壞，陣地也會被奪走。** 蹲著不動不再安全。

---

"""

TAIL = """
---

# 你的命令（把下面這段填好，存成 `命令_T{n}.md`）

**不要改四個 ## 標題。**

```markdown
## 意圖
（一到三句：這個 tick 你想達成什麼、為什麼）

## 命令
1. [L1] {PFX}-?：具體動作＋目標座標＋姿態
2. [L2] {PFX}-?：...
（最多 8 條。每條自己標 L1/L2/L3 — 裁判代為認定時只看動作性質，看不到你的意圖。
　座標須在 30×18 內。可用的姿態／動作：
　　行軍縱隊／戰備推進／戰鬥行進／固守／**構築工事**／**偽裝作業**／抽離營級／歸建
　　砲擊 <敵編隊>［急襲｜壓制｜干擾］／**攔阻射擊 (x,y)**／建立主指揮所 (x,y)／建立前進指揮所 (x,y)
　構築工事與偽裝作業必須明確寫出——「固守」「防禦姿態」都不算。）

## 應變
- 若（具體條件）則（具體動作）
（最多 6 條。條件要可判定。位移類應變會執行到完成為止。）

## 給裁判的問題
（可省略。只能問你視角內合法的問題。不可問戰術建議。）
```

**規則沒寫的動作，你一律得嘗試。** 裁判不得以「規則沒寫」為由拒絕。
Run 6 有四項規則就是指揮官提問長出來的。
"""


def rulings_for(tick, side):
    """本 tick 的裁示。回傳 (共用段, 單方段)。"""
    def collect(d):
        if not d.is_dir():
            return []
        return [(f.name, f.read_text()) for f in sorted(d.glob(f"{tick:02d}_*.md"))]

    shared = collect(RULINGS / "shared")
    only = collect(RULINGS / f"to_{side}")
    return shared, only


def build(s, tick, side):
    shared, only = rulings_for(tick, side)
    parts = [HEAD.format(ZH=ZH[side], n=tick), ar.brief_md(s, side)]
    if shared:
        parts.append("\n---\n\n# 本回裁示（雙方拿到完全相同的內容）\n")
        parts += [t for _n, t in shared]
    if only:
        parts.append(f"\n---\n\n# 本回裁示（只給{ZH[side]}軍 — 裁示 7：對你自身命令的解讀只回你）\n")
        parts += [t for _n, t in only]
    parts.append(TAIL.format(n=tick, PFX=PFX[side]))
    return "\n".join(parts)


def check_symmetry(texts, tick):
    """共用段落（HEAD、shared 裁示、TAIL）必須在兩份簡報中逐位元組相同。

    brief_md 的內容本來就該不同（那是各方視角），所以只驗共用段。
    """
    def sig(t, side):
        head, _, rest = t.partition("# 藍軍戰報")
        if not rest:
            head, _, rest = t.partition("# 紅軍戰報")
        # 取戰報之後的部分（裁示＋樣板），並正規化陣營字樣
        _brief, _, after = rest.partition("\n---\n")
        norm = (head + after).replace("藍", "§").replace("紅", "§") \
                             .replace("BLU", "¤").replace("RED", "¤")
        return norm

    a, b = sig(texts["allies"], "allies"), sig(texts["axis"], "axis")
    sh_a, sh_b = rulings_for(tick, "allies")[0], rulings_for(tick, "axis")[0]
    if [n for n, _ in sh_a] != [n for n, _ in sh_b]:
        return False, "shared 裁示清單不一致"
    if a != b:
        import difflib
        d = [l for l in difflib.unified_diff(a.split("\n"), b.split("\n"), lineterm="", n=0)
             if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        return False, f"共用段落有 {len(d)} 行差異：" + " / ".join(x[:60] for x in d[:4])
    return True, "共用段落逐位元組相同"


def check_leak(s, text, side):
    """簡報不得提及任何**未被該方偵獲**的敵編隊或敵指揮所位置。

    對稱檢查其實很弱——`shared/` 是同一個目錄，兩份當然一樣。
    真正會出事的是洩漏：`brief_md` 的過濾器若有破口，或裁判在 `to_<side>/`
    裡順手寫了一句敵情。本檔的核心防線是這個檢查，不是對稱檢查。
    """
    enemy = ar.ENEMY[side]
    spotted = set(s.get("fog_of_war", {}).get(f"{side}_spotted", []))
    bad = []
    for uid, u in s["units"].items():
        if u.get("side") != enemy or uid in spotted:
            continue
        if uid in text:
            bad.append(f"提及未偵獲的敵編隊 {uid}")
        if u.get("short") and u["short"] in text:
            bad.append(f"提及未偵獲的敵編隊代號「{u['short']}」")
    # 敵指揮所座標：未被偵獲時不得出現在簡報。
    # 偵獲紀錄的欄位是 fog_of_war["<side>_spotted_cps"]，格式 "main@29,8"。
    #
    # 座標是純字串比對，會誤判：敵指揮所若與一個**已偵獲**的敵單位同格，
    # 那個座標本來就會合法印出來（Run 4 的 fixture 正是如此——RED-2-1-r4
    # 就站在敵前進指揮所那一格）。因此先算出「有正當理由出現的座標」，
    # 只有落在那之外的才算洩漏。誤判的代價是簡報永遠發不出去，不能容忍。
    legit = set()
    for uid, u in s["units"].items():
        if u.get("side") == side or uid in spotted:
            legit.add(tuple(u["pos"]))
    for _k, p in command.cp_hexes(s, side).items():      # 自己的指揮所
        legit.add(tuple(p))
    known = set(s.get("fog_of_war", {}).get(f"{side}_spotted_cps", []))
    for kind, pos in command.cp_hexes(s, enemy).items():
        if f"{kind}@{pos[0]},{pos[1]}" in known or tuple(pos) in legit:
            continue
        if f"({pos[0]}, {pos[1]})" in text:
            bad.append(f"提及未偵獲的敵{kind}指揮所 {tuple(pos)}")
    return bad


def main():
    tick = int(sys.argv[1]) if len(sys.argv) > 1 else None
    s = ar.load()
    if tick is None:
        tick = s.get("tick", 0)

    texts = {}
    for side in ("allies", "axis"):
        texts[side] = build(s, tick, side)

    ok, why = check_symmetry(texts, tick)
    if not ok:
        print(f"❌ 對稱檢查失敗：{why}")
        print("   簡報未發出。修正後重跑。")
        sys.exit(1)

    leaks = {sd: check_leak(s, t, sd) for sd, t in texts.items()}
    if any(leaks.values()):
        print("❌ 洩漏檢查失敗：")
        for sd, b in leaks.items():
            for x in b:
                print(f"   [{ZH[sd]}軍] {x}")
        print("   簡報未發出。修正後重跑。")
        sys.exit(1)

    for side, t in texts.items():
        d = DEST[side]
        d.mkdir(parents=True, exist_ok=True)
        f = d / "本回簡報.md"
        f.write_text(t)
        # 保留歷史副本供稽核（指揮官不必讀，但紀錄要留）
        (d / f"_歷史簡報_T{tick}.md").write_text(t)
        print(f"  {ZH[side]}軍 → {f}（{len(t.splitlines())} 行）")

    sh = rulings_for(tick, "allies")[0]
    print(f"\n✅ {why}")
    print("✅ 洩漏檢查通過（未偵獲的敵編隊與敵指揮所皆未出現在簡報中）")
    print(f"   共用裁示 {len(sh)} 份"
          + (f"：{', '.join(n for n, _ in sh)}" if sh else "")
          + f"｜單方裁示 藍 {len(rulings_for(tick,'allies')[1])} / "
            f"紅 {len(rulings_for(tick,'axis')[1])}")
    print(f"   {ar.clock(s)}")


if __name__ == "__main__":
    main()
