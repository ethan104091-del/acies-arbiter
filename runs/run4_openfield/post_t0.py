#!/usr/bin/env python3
"""T0 收尾：回填各方可觀察日誌（防洩漏）＋登錄常態令路線。"""
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of

s = of.load()
own = {"allies": [], "axis": []}
for h in s.get("hour_log", []):
    txt, gh = h["summary"], h["global_hour"]
    for side, pre in (("allies", "BLU"), ("axis", "RED")):
        parts = [p for p in txt.split("；") if pre in p]
        tag = "allies main" if side == "allies" else "axis main"
        for p2 in txt.split("；"):
            if tag in p2:
                parts.append(p2.replace(tag, "我方主").replace("[gh%d %s] " % (gh, ""), ""))
        if parts:
            own[side].append(f"[gh{gh}] " + "；".join(parts))
        elif "無動作" in txt:
            own[side].append(f"[gh{gh}] 我方原地（命令延遲中）")
for side in ("allies", "axis"):
    out = []
    for line in own[side]:
        line = re.sub(r"\[gh(\d+)\] \[gh\d+ [^\]]+\] ", r"[gh\1] ", line)
        line = line.replace("我方主 指揮所", "我方主指揮所")
        out.append(line)
    own[side] = out + ["[T0 總結] 全程未偵獲任何敵軍單位。"]
s["hour_log_side"] = own
s["standing_routes"] = {
    "BLU-1": [[4, 6], [8, 8]], "BLU-2": [[3, 8], [6, 8], [8, 9]], "BLU-3": [[5, 12], [8, 10]],
    "BLU-AD": [[5, 8], [7, 9]], "BLU-SF": [[8, 1], [16, 1], [22, 2]],
    "BLU-1-rcn": [[6, 3], [12, 3]], "BLU-AD-rcn": [[7, 8], [13, 8]], "BLU-3-rcn": [[6, 14], [12, 14]],
    "BLU-2-rcn": [[3, 9], [3, 13], [6, 13], [6, 5]], "BLU-2-1-r4": [[4, 10]], "BLU-2-2-r4": [[4, 10]],
    "RED-3": [[25, 3]], "RED-2": [[25, 8]], "RED-1": [[25, 13]], "RED-SF": [[23, 15]],
}
of.save(s)
print("✅ T0 收尾完成")
