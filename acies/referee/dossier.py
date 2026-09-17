"""卷宗：三段組裝與留痕。

前綴 A（整局凍結）：手冊 v2、動詞目錄、決定紀錄綱要、規則書全文（固定順序）、判例與戰爭法全文、指揮官手冊。
前綴 B（每 tick）：本局裁示集、雙方本 tick 命令定稿原文、常設命令現行版本。
小時尾段：桌況、全知狀態、可行性表、條款帳、上一小時、待裁定回覆、指令。
每個區塊記路徑／雜湊／長度；整份請求雜湊存進資料庫，「裁判看到什麼」是查表。
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import acies
from acies.engine import verbs as V

from . import render, schema

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
RULE_FILES = ["rules/00_核心.md", "rules/10_地形與移動.md", "rules/20_偵察.md", "rules/30_火力.md",
              "rules/40_近戰.md", "rules/50_工事.md", "rules/60_指揮.md", "rules/70_後勤.md", "rules/80_狀態.md",
              "rules/90_史料/scenario_open_field.md"]
LAW_FILES = ["law/precedents.md", "law/law_of_war.md"]

ZH = {"allies": "藍軍", "axis": "紅軍"}


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _block(bid, text, path=None):
    return {"id": bid, "path": path, "sha256": _sha(text), "chars": len(text), "text": text}


def commander_handbook():
    """指揮官手冊（數字自引擎產生）：載入 runs/run8_openfield/gen_handbook.py 的樣板渲染藍軍版；
    紅軍版除陣營字樣外逐位元組相同（該產生器自驗）。"""
    p = acies.ROOT / "runs" / "run8_openfield" / "gen_handbook.py"
    spec = importlib.util.spec_from_file_location("gen_handbook_run8", p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.render(mod.TPL, "allies")


def prefix_a():
    blocks = [_block("A1", (PROMPTS / "referee_v2.md").read_text(), "acies/prompts/referee_v2.md"),
              _block("A2", V.render_catalogue()),
              _block("A3", "# 決定紀錄綱要（JSON Schema）\n\n```json\n" +
                     json.dumps(schema.json_schema(), ensure_ascii=False, indent=1) + "\n```")]
    for rel in RULE_FILES:
        blocks.append(_block(f"A4.{Path(rel).stem}", f"# 規則書：{rel}\n\n" + (acies.ROOT / rel).read_text(), rel))
    for rel in LAW_FILES:
        blocks.append(_block(f"A5.{Path(rel).stem}", f"# {rel}\n\n" + (acies.ROOT / rel).read_text(), rel))
    blocks.append(_block("A6", "# 指揮官手冊（藍軍版；紅軍版除陣營字樣外逐位元組相同）\n\n" + commander_handbook()))
    return blocks


def prefix_b(work):
    rl = work.get("rulings") or []
    rt = ["# 本局裁示集", ""]
    rt += [f"## 裁示 {r['seq']}（gh{r['gh']}，{r['ruling_id']}）\n- 條件：{r['condition']}\n- 效果：{r['effect']}\n"
           f"- 依據：{r.get('basis', '')}\n- 對誰有利：{r.get('beneficiary', 'neutral')}\n" for r in rl] or ["（尚無）"]
    ot = [f"# 本 tick（T{work['tick']}）雙方命令定稿原文", ""]
    for sd in ("allies", "axis"):
        ot += [f"## {ZH[sd]}", "", "```", work["orders"].get(sd, "") or "（未提交：視為維持原命令）", "```", ""]
    standing = [c for c in work.get("clauses", []) if c["kind"] in ("standing", "self_constraint") and c["status"] in ("pending", "active")]
    st = ["# 常設命令現行版本", ""] + [f"- {c['clause_id']}［{c['status']}］{c['text']}" for c in standing] or ["（無）"]
    return [_block("B1", "\n".join(rt)), _block("B2", "\n".join(ot)), _block("B3", "\n".join(st))]


def suffix_c(work):
    s = work["state"]
    kind = work["kind"]
    head = (f"# 桌況\n\n桌 {work['table_id']}　gh{work['gh']}　T{work['tick']}　卷宗種類：**{kind}**"
            f"（{'登記：切條款、登記延遲、形式化應變、回答問題；不動部隊' if kind == 'register' else '解算：展開本小時動作'}）"
            f"　本小時{'是' if work['gh'] % work['tick_hours'] == 0 else '不是'} tick 首小時")
    parts = [head, render.state_table(s), render.feasibility_table(s), render.clause_ledger(work.get("clauses", [])),
             render.previous_hour(work.get("previous"), work.get("previous_execution")),
             render.adjudications(work.get("adjudications", []))]
    if work.get("reopened"):
        parts.append("## 重新登記\n\n本 tick 的登記曾因公告通則裁示而重開提交窗口，雙方已在完整裁示集下重新確認命令。"
                     "快照已還原到登記前、本 tick 的條款帳已清空；請依前綴 B 的**現行**命令原文重新登記全部條款。"
                     "上一次登記的決定紀錄如下，僅供參考：\n\n```json\n" +
                     json.dumps(work.get("previous_register"), ensure_ascii=False)[:20000] + "\n```")
    if work.get("errors"):
        parts.append("## 上一次提交被退回的錯誤（同一卷宗，重出一次）\n\n" +
                     "\n".join(f"- [{c}] {m}" for c, m in work["errors"]))
    parts.append(f"# 指令\n\n輸出一份 {kind} 種類的決定紀錄（gh={work['gh']}），嚴格符合綱要。")
    text = "\n\n".join(p for p in parts if p)
    return [_block("C", text)]


def build(work, prefix_a_blocks=None):
    """回傳 {"system": [...], "user": str, "blocks": [...], "hash": str}。"""
    a = prefix_a_blocks or prefix_a()
    b = prefix_b(work)
    c = suffix_c(work)
    a_text = "\n\n".join(x["text"] for x in a)
    b_text = "\n\n".join(x["text"] for x in b)
    system = [{"type": "text", "text": a_text, "cache_control": {"type": "ephemeral", "ttl": "1h"}},
              {"type": "text", "text": b_text, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    user = c[0]["text"]
    blocks = [{k: v for k, v in x.items() if k != "text"} for x in a + b + c]
    h = _sha(json.dumps({"system": system, "user": user}, ensure_ascii=False, sort_keys=True))
    return {"system": system, "user": user, "blocks": blocks, "hash": h,
            "prefix_a_hash": _sha(a_text), "prefix_b_hash": _sha(b_text)}
