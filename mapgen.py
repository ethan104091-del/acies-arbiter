#!/usr/bin/env python3
"""地圖製作小工具 → maps/<NAME>.json（{width,height,terrain}）。

PvP「純戰場 The Open Field」：歐洲開闊平原、~96% 開闊 + 零星林地，
林地以 180° 旋轉對稱擺放（保證雙方地形絕對公平）。地形刻意非要素——純戰術較量。

地形代碼（同 mapcore.A_TERRAIN）：. 開闊  F 森林  H 丘陵  U 城鎮  R 河  B 橋  S 沼澤  K 灌木籬
"""
import json
from pathlib import Path
from collections import Counter

NAME = "open_field"
W, H = 30, 18

# 只定義「左上半」的林叢種子；程式自動 180° 旋轉補到「右下半」＝絕對對稱。
COPSE_SEEDS = [
    (6, 3), (7, 3), (6, 4),            # 左上小林
    (12, 6), (13, 6), (13, 7),         # 中偏上小林
    (4, 9), (5, 9), (4, 10),           # 左中小林
    (9, 13), (10, 13), (9, 12),        # 左下小林（其旋轉像落在右上）
]

LEGEND = {".": "開闊", "F": "森林", "H": "丘陵", "U": "城鎮",
          "R": "河", "B": "橋", "S": "沼澤", "K": "灌木籬"}


def build():
    grid = [["." for _ in range(W)] for _ in range(H)]
    for (x, y) in COPSE_SEEDS:
        grid[y][x] = "F"
        grid[H - 1 - y][W - 1 - x] = "F"     # 180° 旋轉對稱
    return {"width": W, "height": H, "terrain": grid}


def check_symmetry(m):
    g = m["terrain"]
    for y in range(H):
        for x in range(W):
            if g[y][x] != g[H - 1 - y][W - 1 - x]:
                return False
    return True


def preview(m):
    g = m["terrain"]
    print(f"地圖 {NAME}  {W}×{H}   180°對稱：{'✅' if check_symmetry(m) else '❌ 不對稱!'}")
    print("   " + "".join(str(x % 10) for x in range(W)))
    for y in range(H):
        print(f"{y:2} " + "".join(g[y]))
    cnt = Counter(c for row in g for c in row)
    tot = W * H
    print("地形佔比：" + "  ".join(f"{LEGEND[c]}{cnt[c]}({cnt[c]*100//tot}%)" for c in sorted(cnt)))
    print("部署：藍軍西緣(x=0-2) / 紅軍東緣(x=27-29)，180°對稱布置")


if __name__ == "__main__":
    m = build()
    out = Path.home() / "war-game" / "maps" / f"{NAME}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(m, ensure_ascii=False, indent=2))
    preview(m)
    print(f"✅ 已存：{out}")
