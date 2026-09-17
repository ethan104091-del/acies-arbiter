"""審查卷宗：裁示原文、機械檢查結果、被引用小時的事實、規則全文、判例全文、審查官手冊。"""
import json
from pathlib import Path

import acies
from acies.referee import dossier as D

REVIEWER_MD = Path(__file__).resolve().parents[1] / "prompts" / "reviewer.md"


def rules_text():
    return "\n\n".join((acies.ROOT / rel).read_text() for rel in D.RULE_FILES + D.LAW_FILES)


def rule_sections():
    """[(標籤, 段落文字)]：規則檔與判例檔的每個 ## 節。"""
    out = []
    for rel in D.RULE_FILES + D.LAW_FILES:
        text = (acies.ROOT / rel).read_text()
        cur, buf = None, []
        for line in text.splitlines():
            if line.startswith("## "):
                if cur: out.append((cur, "\n".join(buf)))
                cur, buf = f"{Path(rel).name} {line[3:].strip()[:40]}", []
            else:
                buf.append(line)
        if cur: out.append((cur, "\n".join(buf)))
    return out


def build(ruling, checks, applications, role, opponent_opinion=None, debate_round=0, merge_of=None):
    """回傳 (system 區塊清單, user 文字)。role：'審查官甲'／'審查官乙'（同一手冊、不同席位，用於辯論）。"""
    system = [{"type": "text", "text": REVIEWER_MD.read_text() + "\n\n" + rules_text()}]
    parts = [f"# 審查對象：裁示 {ruling['ruling_id']}（gh{ruling['gh']}）", "",
             f"- 條件：{ruling['condition']}", f"- 效果：{ruling['effect']}", f"- 依據：{ruling.get('basis', '')}",
             f"- 錨點：{json.dumps(ruling.get('anchor'), ensure_ascii=False)}", f"- 為何一級不夠：{ruling.get('why_not_tier1', '')}",
             f"- 裁判自標受益方：{ruling.get('beneficiary')}", "",
             "# 機械檢查", "```json", json.dumps(checks, ensure_ascii=False, indent=1), "```", "",
             "# 被引用的小時（事實）"]
    for a in applications[:12]:
        parts += [f"## gh{a['gh']}", f"動作：{json.dumps(a.get('actions'), ensure_ascii=False)[:1500]}",
                  f"事件：{json.dumps(a.get('events'), ensure_ascii=False)[:1500]}",
                  f"量級：{json.dumps(a.get('measurement'), ensure_ascii=False)}", ""]
    if not applications:
        parts.append("（本局未被任何動作引用）")
    if opponent_opinion:
        parts += ["", f"# 辯論第 {debate_round} 輪：另一位審查官的意見", "```json",
                  json.dumps(opponent_opinion, ensure_ascii=False, indent=1), "```",
                  "請逐點回應對方，改變或維持你的結論都要說明理由。"]
    if merge_of:
        parts += ["", "# 合稿", "兩位審查官結論一致但修訂文字不同。以下是雙方最後一輪的修訂，請合成**一份**最終修訂：",
                  "條件與效果各一句到三句、涵蓋雙方都堅持的要點、不新增任何一方未提出的內容；規則檔註記亦合成一句。", "```json",
                  json.dumps(merge_of, ensure_ascii=False, indent=1), "```"]
    parts += ["", f"你是{role}。輸出一份審查回答，嚴格符合綱要。"]
    return system, "\n".join(parts)
