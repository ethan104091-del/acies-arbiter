"""落地：判例節、規則檔註記、資料庫狀態、審查紀錄（改了哪裡、改動前原文、兩官意見、辯論）。"""
import datetime as dt
import json
import re
from pathlib import Path

import acies

PRECEDENTS = acies.ROOT / "law" / "precedents.md"
RULES = acies.ROOT / "rules"
LOG_DIR = acies.ROOT / "law" / "review_log"

_CN = "〇一二三四五六七八九"


def cn(n):
    """1–99 → 中文數字（判例節號慣例）。"""
    if n < 10: return _CN[n]
    t, o = divmod(n, 10)
    return ("" if t == 1 else _CN[t]) + "十" + (_CN[o] if o else "")


def next_section_no():
    nums = re.findall(r"^## §([〇一二三四五六七八九十]+)", PRECEDENTS.read_text(), flags=re.M)
    def val(s):
        if "十" not in s: return _CN.index(s)
        t, o = s.split("十")
        return (10 if t == "" else _CN.index(t) * 10) + (_CN.index(o) if o else 0)
    return (max(val(s) for s in nums) if nums else 0) + 1


def precedent_section(no, ruling, table_id, result, checks):
    final = result["final"]; v = result["outcome"]
    today = dt.date.today().isoformat()
    head = f"## §{cn(no)} 桌 {table_id[:8]} 裁示 {ruling['ruling_id']}（gh{ruling['gh']}）自動審查：{v}（{today}）\n\n"
    body = [f"> **原裁示**　條件：{ruling['condition']}　效果：{ruling['effect']}",
            f"> 依據：{ruling.get('basis', '')}　裁判自標受益方：{ruling.get('beneficiary')}", ""]
    if v == "定案":
        body += ["**定案，照原文入判例。**", ""]
    elif v == "改寫":
        r = final["revision"]
        body += ["**改寫後入判例：**", "", f"> **條件**：{r['condition']}", f"> **效果**：{r['effect']}", ""]
    else:
        body += ["**推翻，不入判例。**", ""]
    body += [f"- 可自現行規則推出：{'是' if final['derivable_from_rules'] else '否'}——{final['derivation']}",
             f"- 受益方：{final['beneficiary_should_be']}（裁判自標{'正確' if final['beneficiary_ok'] else '有誤'}）",
             f"- 濫用面：{final['exploit']}"]
    for c in final.get("conflicts", []):
        body.append(f"- 衝突：{c['source']}「{c['quote'][:120]}」——{c['why']}")
    body += [f"- 理由：{final['reasoning']}",
             f"- 機械檢查：{json.dumps(checks.get('findings'), ensure_ascii=False)}；影響 {json.dumps(checks.get('impact', {}).get('points_delta'), ensure_ascii=False)}",
             f"- 審查：Claude Opus 與 Codex 兩官{'一致' if len(result['rounds']) == 1 else f'經 {len(result[chr(114)+chr(111)+chr(117)+chr(110)+chr(100)+chr(115)]) - 1} 輪辯論後一致'}；紀錄見 `law/review_log/`。", ""]
    if final.get("amendment"):
        a = final["amendment"]
        body.append(f"已於 `rules/{a['file']}` {a['section']} 註記：「{a['sentence']}」")
    return head + "\n".join(body) + "\n"


def amend_rule(amendment, no):
    """在規則檔對應節的標題後插入一行判例註記。回傳 (檔案, 改動前原文片段) 或 None。"""
    f = RULES / amendment["file"]
    if not f.exists():
        return None
    text = f.read_text()
    lines = text.splitlines()
    sec = amendment["section"].strip()
    idx = next((i for i, l in enumerate(lines) if l.startswith("## ") and sec in l), None)
    if idx is None:
        idx = next((i for i, l in enumerate(lines) if l.startswith("## ")), 0)
    before = "\n".join(lines[idx:idx + 4])
    note = f"> ★ 判例 §{cn(no)}（自動審查，{dt.date.today().isoformat()}）：{amendment['sentence']}"
    lines.insert(idx + 1, "")
    lines.insert(idx + 2, note)
    f.write_text("\n".join(lines) + "\n")
    rel = str(f.relative_to(acies.ROOT)) if acies.ROOT in f.parents else str(f)
    return rel, before


def write_log(table_id, entries):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    p = LOG_DIR / f"{dt.date.today().isoformat()}_{table_id[:8]}.md"
    out = [f"# 判例審查紀錄　桌 {table_id[:8]}　{dt.datetime.now().isoformat(timespec='minutes')}", ""]
    for e in entries:
        out += [f"## 裁示 {e['ruling_id']} → {e['outcome']}", ""]
        for c in e.get("changes", []):
            out += [f"- 改動：{c['what']}", "  改動前：", "  ```", *("  " + l for l in c["before"].splitlines()), "  ```"]
        out += ["- 機械檢查：", "  ```json", "  " + json.dumps(e.get("checks"), ensure_ascii=False), "  ```"]
        for r in e.get("rounds", []):
            out += [f"- 第 {r['round']} 輪：", "  ```json", "  " + json.dumps(r["reviews"], ensure_ascii=False), "  ```"]
        out.append("")
    p.write_text("\n".join(out) + "\n")
    return p


def apply(table_id, ruling, result, checks):
    """依結論落地。回傳 {outcome, section_no, changes:[{what, before}]}。"""
    changes = []
    if result["outcome"] in ("定案", "改寫", "推翻"):
        no = next_section_no()
        before = PRECEDENTS.read_text()[-600:]
        PRECEDENTS.write_text(PRECEDENTS.read_text().rstrip("\n") + "\n\n" + precedent_section(no, ruling, table_id, result, checks))
        changes.append({"what": f"law/precedents.md 追加 §{cn(no)}", "before": "（檔尾）\n" + before})
        am = result["final"].get("amendment")
        if am and result["outcome"] in ("推翻", "改寫"):
            r = amend_rule(am, no)
            if r:
                changes.append({"what": f"{r[0]} {am['section']} 插入判例註記", "before": r[1]})
        return {"outcome": result["outcome"], "section_no": no, "changes": changes}
    return {"outcome": result["outcome"], "section_no": None, "changes": changes}
