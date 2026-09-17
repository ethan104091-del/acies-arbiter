"""簡報文字的洩漏檢查與對稱檢查。

自 runs/run7_openfield/dispatch.py 的 check_leak／check_symmetry 移植；三個誤判例外
（歷史日誌節排除、抽離營母編隊代號、有正當理由出現的座標）各自付過一次事故，照搬不改。
後端發布任何單方文字前必須通過 check_leak；任何共用文字必須通過 check_symmetry。
"""
import difflib
import re

import arbiter as ar
import command

HISTORY_HEADING = "## 七、上一 tick"


def check_leak(s, text, side, *, skip_history=True):
    """text 不得提及任何該方未偵獲的敵編隊或敵指揮所位置。回傳問題清單（空＝通過）。"""
    enemy = ar.ENEMY[side]
    spotted = set(s.get("fog_of_war", {}).get(f"{side}_spotted", []))
    bad = []
    if skip_history:
        # 那一節由 push_log 在事件當時過濾，用現在的偵獲清單複查歷史是錯的（Run 7 T7 誤判）。
        head, sep, _hist = text.partition(HISTORY_HEADING)
        text = head if sep else text

    def mentions(token, chinese=False):
        tail = r"(?![-/])" if chinese else r"(?![-\w])"
        return re.search(re.escape(token) + tail, text) is not None

    parent_disclosed = {u.split("-")[0] + "-" + u.split("-")[1]
                        for u in spotted if u.count("-") >= 2}
    for uid, u in s["units"].items():
        if u.get("side") != enemy or uid in spotted:
            continue
        if mentions(uid):
            bad.append(f"提及未偵獲的敵編隊 {uid}")
        if (u.get("short") and uid not in parent_disclosed
                and mentions(u["short"], chinese=True)):
            bad.append(f"提及未偵獲的敵編隊代號「{u['short']}」")

    legit = set()
    for uid, u in s["units"].items():
        if u.get("side") == side or uid in spotted:
            legit.add(tuple(u["pos"]))
    for _k, p in command.cp_hexes(s, side).items():
        legit.add(tuple(p))
    known = set(s.get("fog_of_war", {}).get(f"{side}_spotted_cps", []))
    for kind, pos in command.cp_hexes(s, enemy).items():
        if f"{kind}@{pos[0]},{pos[1]}" in known or tuple(pos) in legit:
            continue
        if f"({pos[0]}, {pos[1]})" in text:
            bad.append(f"提及未偵獲的敵{kind}指揮所 {tuple(pos)}")
    return bad


_FACTION_WORDS = (("藍", "§"), ("紅", "§"), ("BLU", "¤"), ("RED", "¤"),
                  ("allies", "★"), ("axis", "★"))


def normalize_faction(text):
    for a, b in _FACTION_WORDS:
        text = text.replace(a, b)
    return text


def check_symmetry(text_allies, text_axis):
    """共用文字在陣營字樣正規化後必須逐位元組相同。回傳 (ok, 說明)。"""
    a, b = normalize_faction(text_allies), normalize_faction(text_axis)
    if a == b:
        return True, "共用段落逐位元組相同"
    d = [l for l in difflib.unified_diff(a.split("\n"), b.split("\n"), lineterm="", n=0)
         if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    return False, f"共用段落有 {len(d)} 行差異：" + " / ".join(x[:60] for x in d[:4])
