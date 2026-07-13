#!/usr/bin/env python3
"""補給線渲染原型：把補給走廊用「底色染色」畫上去，證明不蓋掉地形字元。
產出 PNG（supply_demo.png）給人看。用 PIL 直畫，色彩仿 mapcore.A_TERRAIN。
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

G = Path.home() / "war-game"
m = json.load(open(G / "maps" / "open_field.json"))
W, H, terr = m["width"], m["height"], m["terrain"]

# ── 展示場景（demo 用；真正引擎會自動算）──────────────────
BLUE = {(20, 7): "B1", (18, 4): "B2"}      # 藍軍：補給源=西緣(x=0)
RED = {(10, 7): "R1", (15, 5): "R2"}        # 紅軍：R1 卡在 B1 走廊上、R2 貼近 B2 走廊
unit = {}
for (x, y), l in BLUE.items(): unit[(x, y)] = ("blue", l)
for (x, y), l in RED.items():  unit[(x, y)] = ("red", l)

# ── 算藍軍每個師的補給走廊狀態（往西回 x=0）──────────────
#   intact 暢通 / contested 受威脅(敵距走廊1格) / cut 切斷(敵佔走廊、在師與源之間)
supply = {}   # (x,y) -> "intact"|"contested"|"cut"
for (ux, uy) in BLUE:
    block_x = -1
    for (rx, ry) in RED:
        if ry == uy and rx < ux:
            block_x = max(block_x, rx)          # 最靠近師的阻斷點
    for x in range(0, ux):
        if block_x >= 0 and x >= block_x:
            supply[(x, uy)] = "cut"             # 阻斷點到師之間＝斷
        else:
            st = "intact"
            for (rx, ry) in RED:                # 走廊旁 1 格＝受威脅
                if abs(rx - x) <= 1 and abs(ry - uy) <= 1:
                    st = "contested"
            supply.setdefault((x, uy), st)

# ── 256 色 → RGB ────────────────────────────────────────
def xterm(n):
    if n < 16:
        base = [(0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),(128,0,128),
                (0,128,128),(192,192,192),(128,128,128),(255,0,0),(0,255,0),
                (255,255,0),(0,0,255),(255,0,255),(0,255,255),(255,255,255)]
        return base[n]
    if n < 232:
        n -= 16; r, g, b = n//36, (n%36)//6, n%6
        return tuple(0 if c == 0 else 55+40*c for c in (r, g, b))
    v = 8 + 10*(n-232); return (v, v, v)

TERR = {".": ("  ", 28, 22), "F": ("♣♣", 40, 22), "H": ("︿", 180, 94),
        "U": ("██", 231, 240), "R": ("≈≈", 51, 24), "B": ("╪", 214, 94),
        "S": ("~~", 109, 60), "K": ("⌗⌗", 64, 22)}
SUP_DASH = {"intact": (95, 130, 185), "contested": (225, 200, 70), "cut": (225, 70, 70)}

# ── PIL 畫格 ────────────────────────────────────────────
CW, CH = 46, 46
Y0, Y1 = 3, 9   # 只畫行動區的橫排（放大看清楚）
try:
    fnt = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 30)
    sml = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
except Exception:
    fnt = sml = ImageFont.load_default()

img = Image.new("RGB", (W*CW, (Y1-Y0)*CH), (10, 10, 10))
d = ImageDraw.Draw(img)
for y in range(Y0, Y1):
    for x in range(W):
        t = terr[y][x]
        glyph, fg, bg = TERR.get(t, ("  ", 231, 16))
        x0, y0 = x*CW, (y-Y0)*CH
        d.rectangle([x0, y0, x0+CW-1, y0+CH-1], fill=xterm(bg))   # 底色＝地形本色，不動
        st = supply.get((x, y))
        if (x, y) in unit:                                # 單位：疊在最上
            side, lab = unit[(x, y)]
            d.rectangle([x0+1, y0+1, x0+CW-2, y0+CH-2],
                        fill=(20,70,200) if side == "blue" else (200,40,40))
            d.text((x0+4, y0+7), lab, font=sml, fill=(255,255,255))
        elif st and t == ".":                             # 空地上的補給格 → 畫虛線橫段
            cy = y0 + CH//2
            col = SUP_DASH[st]
            for dx in range(4, CW-3, 12):                 # 短劃 + 間隙 = 虛線
                d.line([x0+dx, cy, x0+dx+6, cy], fill=col, width=3)
        else:                                             # 林叢/地形字元照畫，虛線在此自然斷開
            d.text((x0+3, y0+5), glyph, font=fnt, fill=xterm(fg))

out = G / "supply_demo.png"
img.save(out)
print("cut cells:", sum(1 for v in supply.values() if v == "cut"),
      "| contested:", sum(1 for v in supply.values() if v == "contested"),
      "| intact:", sum(1 for v in supply.values() if v == "intact"))
print("✅", out)
