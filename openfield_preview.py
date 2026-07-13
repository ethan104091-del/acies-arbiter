#!/usr/bin/env python3
"""純戰場部署預覽 → open_field_preview.png（全圖+雙方編隊+主指揮所）。"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

G = Path.home() / "war-game"
s = json.load(open(G / "maps" / "open_field_state.json"))
W, H, terr = s["map"]["width"], s["map"]["height"], s["map"]["terrain"]
CW = CH = 30

# 單位 → ASCII 標籤（避 CJK 字型問題）
LAB = {"BLU-1": "B1", "BLU-2": "B2", "BLU-3": "B3", "BLU-AD": "Bx", "BLU-SF": "B*",
       "RED-1": "R1", "RED-2": "R2", "RED-3": "R3", "RED-AD": "Rx", "RED-SF": "R*"}

try:
    fnt = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 18)
    sml = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
except Exception:
    fnt = sml = ImageFont.load_default()

img = Image.new("RGB", (W*CW, H*CH), (0, 60, 0))
d = ImageDraw.Draw(img)
# 地形：開闊深綠、林叢 ♣♣
for y in range(H):
    for x in range(W):
        x0, y0 = x*CW, y*CH
        if terr[y][x] == "F":
            d.text((x0+4, y0+5), "♣♣", font=fnt, fill=(60, 180, 60))
# 指揮所：開局皆未建（玩家自行下令）→ 若已設才畫
for side in ("allies", "axis"):
    cp = s["command"][side].get("main_cp")
    if not cp:
        continue
    cx, cy = cp
    x0, y0 = cx*CW, cy*CH
    d.rectangle([x0+1, y0+1, x0+CW-2, y0+CH-2], outline=(255, 220, 0), width=3)
    d.text((x0+2, y0+8), "HQ", font=sml, fill=(255, 220, 0))
# 單位
for uid, u in s["units"].items():
    x, y = u["pos"]
    x0, y0 = x*CW, y*CH
    blue = u["side"] == "allies"
    d.rectangle([x0+1, y0+1, x0+CW-2, y0+CH-2],
                fill=(20, 70, 210) if blue else (210, 40, 40))
    d.text((x0+3, y0+7), LAB[uid], font=sml, fill=(255, 255, 255))

out = G / "open_field_preview.png"
img.save(out)
print("藍軍(西)：B1/B2/B3 步兵 · Bx 裝甲 · B* 特戰(隱蔽) ｜ 紅軍(東)：R... 對稱")
print("黃框 HQ = 主指揮所（軍長初始位置）")
print("✅", out)
