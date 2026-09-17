"""機械檢查（零模型）：形式、數字出處、相似段落、必要欄位、影響統計。

影響門檻用通式（每局數字不同）：
- 該裁示被引用的小時，沙盒量到的單方分數位移累計 > TIE_BAND × 終局較高分（足以翻轉平手判定）
- 或單方加權戰力位移比例 > POWER_RATIO_LIMIT
"""
import re
from collections import Counter

import arbiter as ar
from acies.referee.validate import FACTION_WORDS, PROBABILITY_WORDS

POWER_RATIO_LIMIT = 0.01
NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")


def _bigrams(t):
    t = re.sub(r"\s+", "", t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similarity(a, b):
    A, B = _bigrams(a), _bigrams(b)
    return len(A & B) / len(A | B) if A and B else 0.0


def containment(a, b):
    """重疊係數：短的那段有多少落在長的裡（「就地待機」對「就地待機，不視為位移」＝1.0）。"""
    A, B = _bigrams(a), _bigrams(b)
    return len(A & B) / min(len(A), len(B)) if A and B else 0.0


def form_checks(r):
    out = []
    if FACTION_WORDS.search(r.get("condition", "")):
        out.append(("形式", "條件指名陣營"))
    for f in ("condition", "effect"):
        if PROBABILITY_WORDS.search(r.get(f, "")):
            out.append(("形式", f"{f} 含機率用語"))
    if not r.get("basis"):
        out.append(("欄位", "缺依據"))
    if r.get("tier2_used") and not r.get("why_not_tier1"):
        out.append(("欄位", "有二級動作但未寫為何一級不夠"))
    if NUM.search(r.get("effect", "")) and not (r.get("anchor") or {}).get("magnitude"):
        out.append(("欄位", "效果含數字但無可反駁的錨點（時期／裝備／情境／數量級）"))
    return out


def number_provenance(r, rules_text):
    """效果裡的數字若在規則全文找不到 → 標記（可能是裁判自創的量）。"""
    out = []
    for n in set(NUM.findall(r.get("effect", ""))):
        if n not in rules_text:
            out.append(("數字", f"效果中的數字 {n} 在規則書找不到出處"))
    return out


def similar_sections(r, sections, top=3, floor=0.25):
    """sections：[(來源標籤, 文字)]。回傳相似度最高的幾段（條件＋效果對段落）。"""
    q = r.get("condition", "") + r.get("effect", "")
    scored = sorted(((similarity(q, t), lab) for lab, t in sections), reverse=True)
    return [(f"{s:.2f}", lab) for s, lab in scored[:top] if s >= floor]


def impact(applications, final_scores):
    """applications：[{gh, measurement}]（measurement 為 sandbox.measure 的輸出）。回傳統計與是否超門檻。"""
    delta = Counter(); ratio = Counter()
    for a in applications:
        for sd, m in (a.get("measurement") or {}).items():
            delta[sd] += m.get("points_delta", 0)
            ratio[sd] = max(ratio[sd], abs(m.get("ratio", 0.0)))
    hi = max(final_scores.values()) if final_scores else 0
    limit = ar.TIE_BAND * hi
    flagged = any(abs(v) > limit for v in delta.values()) or any(v > POWER_RATIO_LIMIT for v in ratio.values())
    return {"applications": len(applications), "points_delta": dict(delta), "max_power_ratio": dict(ratio),
            "limit_points": limit, "flagged": flagged}


def run_all(r, rules_text, sections, applications, final_scores):
    findings = form_checks(r) + number_provenance(r, rules_text)
    sim = similar_sections(r, sections)
    imp = impact(applications, final_scores)
    if imp["flagged"]:
        findings.append(("影響", f"累計單方分數位移 {imp['points_delta']} 超過門檻 {imp['limit_points']:.0f}（TIE_BAND×終局較高分）或戰力位移 >{POWER_RATIO_LIMIT:.0%}"))
    return {"findings": [list(f) for f in findings], "similar": sim, "impact": imp}
