"""簡報：單方戰報（引擎產）＋徵候＋裁示全集（共用）＋命令樣板（共用）。
發布前必過洩漏檢查與對稱檢查；共用段雜湊存進資料庫，雙方相等可查。
"""
import hashlib

from sqlalchemy import select

import arbiter as ar
from acies.db import models as M
from acies.engine import leakcheck

ZH = {"allies": "藍", "axis": "紅"}
PFX = {"allies": "BLU", "axis": "RED"}

HEAD = """# {ZH}軍 · Tick {n} 本回簡報

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

# 你的命令

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
"""


class LeakError(Exception):
    pass


def rulings_text(db, table_id):
    rows = db.scalars(select(M.Ruling).where(M.Ruling.table_id == table_id).order_by(M.Ruling.seq)).all()
    if not rows:
        return "# 裁示全集（雙方拿到完全相同的內容）\n\n（本局尚無裁示）\n"
    out = ["# 裁示全集（雙方拿到完全相同的內容）", ""]
    for r in rows:
        b = r.body
        out += [f"## 裁示 {r.seq}（gh{r.gh}，{r.ruling_id}）", "",
                f"- 條件：{b.get('condition','')}", f"- 效果：{b.get('effect','')}",
                f"- 依據：{b.get('basis','')}", f"- 對誰有利：{b.get('beneficiary','neutral')}", ""]
    return "\n".join(out)


def signals_text(db, table_id, side, tick, tick_hours):
    lo, hi = (tick - 1) * tick_hours, tick * tick_hours
    rows = db.scalars(select(M.Signal).where(M.Signal.table_id == table_id, M.Signal.side == side,
                                             M.Signal.gh >= lo, M.Signal.gh < hi).order_by(M.Signal.gh)).all()
    if not rows:
        return ""
    return "\n## 八、上一 tick 的徵候（只給你方）\n\n" + "\n".join(f"- [gh{r.gh}] {r.text}" for r in rows) + "\n"


def answers_text(db, table_id, side):
    rows = db.scalars(select(M.Question).where(M.Question.table_id == table_id, M.Question.side == side)).all()
    rows = [q for q in rows if q.answer]
    if not rows:
        return ""
    out = ["\n## 九、裁判對你方提問的答覆", ""]
    for q in rows:
        a = q.answer
        out.append(f"- **{q.question_id}**（{'通則，已公告雙方' if a.get('kind') == 'general' else '只回你方'}）："
                   f"{a.get('public_text') or a.get('private_text', '')}")
    return "\n".join(out) + "\n"


def build(db, t, s, side, tick):
    head = HEAD.format(ZH=ZH[side], n=tick)
    body = ar.brief_md(s, side) + signals_text(db, t.id, side, tick, t.tick_hours) + answers_text(db, t.id, side)
    shared = rulings_text(db, t.id) + TAIL.format(PFX=PFX[side])
    text = head + body + "\n---\n\n" + shared
    leaks = leakcheck.check_leak(s, text, side)
    if leaks:
        raise LeakError(f"{side} 簡報洩漏：{leaks}")
    shared_hash = hashlib.sha256(leakcheck.normalize_faction(head + shared).encode()).hexdigest()
    return text, shared_hash


def publish(db, t, s, tick):
    """雙方各一份；共用段雜湊必須相等。"""
    out = {}
    for side in ("allies", "axis"):
        text, h = build(db, t, s, side, tick)
        out[side] = (text, h)
    if out["allies"][1] != out["axis"][1]:
        raise LeakError("雙方簡報共用段雜湊不同")
    for side, (text, h) in out.items():
        row = get(db, t.id, tick, side)
        if row is None:
            db.add(M.Brief(table_id=t.id, tick=tick, side=side, text=text, shared_hash=h))
        else:                                   # 同 tick 重發（裁示後窗口重開）：覆寫
            row.text = text; row.shared_hash = h
    db.flush()
    return out


def get(db, table_id, tick, side):
    return db.scalar(select(M.Brief).where(M.Brief.table_id == table_id, M.Brief.tick == tick,
                                           M.Brief.side == side))
