#!/usr/bin/env python3
"""地圖顯示重設計 — 三風格 prototype。

用法：
    python3 map_proto.py 1      # 風格 A：擬真地形圖
    python3 map_proto.py 2      # 風格 B：NATO 軍事符號
    python3 map_proto.py 3      # 風格 C：資訊密集儀表
    python3 map_proto.py all    # 三個一起印（預設）

每格 4 半形寬。讀真實 state.json。靜態印一次（非 Live）方便對比。
選定風格後再整合進 map.py。
"""
import json
import sys
from pathlib import Path
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from wcwidth import wcswidth

GAME_DIR = Path.home() / "war-game"
STATE_PATH = GAME_DIR / "state.json"
ANNOT_PATH = GAME_DIR / "annotations.json"
CELL = 4  # 每格半形寬

# 方向 → 箭頭字元（單位 heading + arrow 路徑端點用）
HEADING_GLYPH = {
    "N": "↑", "S": "↓", "E": "→", "W": "←",
    "NE": "↗", "NW": "↖", "SE": "↘", "SW": "↙",
}

# 兵種 → 格內符號（1 半形寬）
TYPE_GLYPH = {
    "infantry": "●",
    "armor": "▲",
    "motorized": "◆",
    "panzergrenadier": "■",
    # 分遣隊兵種（避開 Ambiguous-width 字元，防破版）
    "artillery": "✸",   # 砲兵
    "recon": "r",       # 偵察
    "engineer": "✦",    # 工兵
    "antitank": "j",    # 反戰車(Panzerjäger)
    "ranger": "✶",      # 特戰/Ranger
}

# ── 共用：讀檔 + 建索引 ────────────────────────────────────────────
def index_state(s, viewer_side="god"):
    """從 state 建空間索引（不讀磁碟），供 viewer/editor 共用。

    viewer_side 決定戰爭迷霧（多人 1v1 各方只看到該看的）：
      "god"    — GM 上帝視角，看全部單位
      "allies" — 盟軍玩家：自己所有師 + fog.allies_spotted 裡的德軍
      "axis"   — 德軍玩家：自己所有師 + fog.axis_spotted 裡的盟軍
    回傳 (pos_unit, obj_tiles, spotted)。spotted = 對該視角可見的「敵方」集合。
    """
    fog = s.get("fog_of_war", {})
    if viewer_side == "allies":
        own, spotted = "allies", set(fog.get("allies_spotted", []))
    elif viewer_side == "axis":
        own, spotted = "axis", set(fog.get("axis_spotted", []))
    else:  # god
        own, spotted = None, None
    pos_unit = {}
    for uid, u in s["units"].items():
        if own is not None:               # 玩家視角：過濾敵方未偵獲者
            if u["side"] != own and uid not in spotted:
                continue
        pos_unit[tuple(u["pos"])] = (uid, u)
    obj_tiles = {}
    for k, o in s.get("objectives", {}).items():
        if not isinstance(o, dict) or "pos" not in o:   # 消耗型 PvP 目標無地圖格，跳過
            continue
        for t in o.get("tiles", [o.get("pos")]):
            if t:
                obj_tiles[tuple(t)] = o
        obj_tiles.setdefault(tuple(o["pos"]), o)
    return pos_unit, obj_tiles, spotted


def load():
    s = json.loads(STATE_PATH.read_text())
    pos_unit, obj_tiles, spotted = index_state(s)
    return s, pos_unit, obj_tiles, spotted


# 敵方偵獲單位只洩露的欄位（其餘內部資料如資源/命令/組織度精確值不送出）
_ENEMY_PUBLIC = ("side", "short", "name", "type", "pos", "visibility_state", "hidden")


def filter_state_for(state, side):
    """產生「某一方視角」的安全 state（多人 server 用）。

    - 己方單位：完整送出。
    - 敵方已偵獲單位：只送 _ENEMY_PUBLIC 欄位 + 概略兵力(strength 取整到 10)。
    - 敵方未偵獲單位：完全不出現。
    這是在 server 端過濾，所以對手即使抓封包也看不到不該看的資料。
    side: "allies" / "axis"（"god" 則原樣回傳）。
    """
    if side == "god":
        return state
    s = json.loads(json.dumps(state))  # deep copy，不動原 state
    fog = s.get("fog_of_war", {})
    spotted = set(fog.get(f"{side}_spotted", []))
    new_units = {}
    for uid, u in s["units"].items():
        if u["side"] == side:
            new_units[uid] = u                      # 己方：完整
        elif uid in spotted:
            pub = {k: u[k] for k in _ENEMY_PUBLIC if k in u}
            st = u.get("strength")
            if isinstance(st, (int, float)):
                pub["strength_approx"] = int(round(st / 10.0) * 10)   # 概略兵力
            new_units[uid] = pub                    # 敵方偵獲：只給公開欄
        # 敵方未偵獲：略過
    s["units"] = new_units
    # fog 只保留自己那份（不洩露對方偵察到了什麼）
    s["fog_of_war"] = {f"{side}_spotted": sorted(spotted),
                       "_note": fog.get("_note", "")}
    # 對手不需要看到敵方指揮官 agent 內部
    s.pop("axis_commander", None) if side == "allies" else None
    # hour 級：延遲命令佇列 + 主令 是各方機密，只留自己那方（敵方的不可見）
    if "pending_orders" in s:
        s["pending_orders"] = [o for o in s["pending_orders"]
                               if o.get("side") == side]
    if "standing_orders" in s and isinstance(s["standing_orders"], dict):
        s["standing_orders"] = {side: s["standing_orders"].get(side, "")}
    return s


def load_annot():
    if not ANNOT_PATH.exists():
        return {"annotations": [], "headings": {}}
    try:
        return json.loads(ANNOT_PATH.read_text())
    except Exception:
        return {"annotations": [], "headings": {}}


def _line_cells(x0, y0, x1, y1):
    """Bresenham：回傳線段經過的格子序列。"""
    cells = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    cx, cy = x0, y0
    while True:
        cells.append((cx, cy))
        if (cx, cy) == (x1, y1):
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
    return cells


def _dir8(dx, dy):
    """向量 → 8 向箭頭字元。"""
    import math
    ang = math.degrees(math.atan2(-dy, dx)) % 360  # 螢幕 y 向下
    dirs = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]
    return dirs[int((ang + 22.5) % 360 // 45)]


def build_overlay(annot, W, H):
    """把 annotations 攤平成 {(x,y): (glyph, color, kind)}。
    kind 用於渲染優先序：marker/text > arrow > phase_line。"""
    ov = {}
    PRIO = {"phase_line": 1, "arrow": 2, "text": 3, "marker": 4}
    def put(x, y, glyph, color, kind):
        if not (0 <= x < W and 0 <= y < H):
            return
        old = ov.get((x, y))
        if old is None or PRIO[kind] >= PRIO[old[2]]:
            ov[(x, y)] = (glyph, color, kind)
    for a in annot.get("annotations", []):
        kind = a.get("type")
        col = a.get("color", "white")
        try:  # 單筆壞資料（手改 JSON 缺欄位等）不該讓整個檢視器掛掉
            if kind == "arrow":
                if not (a.get("from") and a.get("to")):
                    continue
                fx, fy = a["from"]; tx, ty = a["to"]
                cells = _line_cells(fx, fy, tx, ty)
                for (cx, cy) in cells[1:-1]:
                    put(cx, cy, "•", col, "arrow")
                ah = _dir8(tx - fx, ty - fy) if (tx, ty) != (fx, fy) else "•"
                put(tx, ty, ah, col, "arrow")
            elif kind == "marker":
                if not a.get("pos"):
                    continue
                x, y = a["pos"]
                put(x, y, a.get("glyph", "*"), col, "marker")
            elif kind == "text":
                if not a.get("pos"):
                    continue
                x, y = a["pos"]
                put(x, y, "▸", col, "text")
            elif kind == "phase_line":
                if "x" not in a:
                    continue
                x = a["x"]
                for y in range(a.get("y0", 0), a.get("y1", H - 1) + 1):
                    put(x, y, "┊", col, "phase_line")
            elif kind == "polyline":
                pts = [tuple(p) for p in a.get("points", [])]
                for i in range(len(pts) - 1):
                    seg = _line_cells(*pts[i], *pts[i + 1])
                    start = 0 if i == 0 else 1  # 不重畫接點
                    for (cx, cy) in seg[start:]:
                        put(cx, cy, "┊", col, "phase_line")
        except (KeyError, TypeError, ValueError):
            continue  # 跳過這筆壞標註，繼續畫其餘
    return ov


def pad(seg, width=CELL):
    """把字串補/截到指定『顯示寬度』（半形格）。中文算 2。"""
    w = wcswidth(seg)
    if w < width:
        return seg + " " * (width - w)
    if w > width:
        # 截斷到剛好不超過
        out = ""
        cur = 0
        for ch in seg:
            cw = wcswidth(ch)
            if cur + cw > width:
                break
            out += ch
            cur += cw
        return out + " " * (width - cur)
    return seg


def num2(uid):
    """抽番號數字，最多 2 位。"""
    d = "".join(c for c in uid if c.isdigit())
    return (d[:2] or uid[:2])


GRID_STEP = 5             # 每幾格一條主格線（對齊座標標籤）
GLINE = "color(244)"      # 垂直細線顏色（中灰，可見但不搶地形）
GRID_V = "│"              # 垂直細線字元（1 寬）


def first_cell(padded):
    """把已 pad 到 CELL 寬的字串切成 (第一顯示格, 其餘)。處理寬字元。"""
    if not padded:
        return "", ""
    ch = padded[0]
    return ch, padded[1:]


def is_gridcol(x):
    return x % GRID_STEP == 0


def is_gridrow(y):
    return y % GRID_STEP == 0


def colnum_row(W, underline=False):
    g = Text()
    ul = " underline" if underline else ""
    g.append("   ", ul.strip() or None)
    for x in range(W):
        g.append(pad(str(x), CELL) if x % 5 == 0 else "    ", f"dim cyan{ul}")
    g.append("\n")
    return g


def hsep_row(W):
    """水平主格線：在格線欄交會處用 ┼，其餘 ─。寬度對齊資料列。"""
    g = Text()
    g.append("   ")  # 行號 gutter
    line = ""
    for x in range(W):
        line += (GRID_CROSS if is_gridcol(x) else GRID_H) + GRID_H * 3
    g.append(line, GRID_STYLE)
    g.append("\n")
    return g


# ════════════════════════════════════════════════════════════════════
# 風格 A：擬真地形圖（固定緩衝區網格 + underline 橫線）
#   每格 = 「垂直線欄(1寬) + 地形內容(3寬)」，線在專屬欄位，內容永不推移它。
#   直線：主線(每5格,亮│) + 次線(每格,暗┆)。
#   橫線：用 underline 文字裝飾畫在格線列「上緣」（不佔行、連續貫穿、不被打斷）。
#   四邊標座標。
# ════════════════════════════════════════════════════════════════════
INT = 3                      # 每格內容寬（3 半形）
A_TERRAIN = {                # glyph: (3寬填充, 前景色, 背景色)
    # 離散地物（森林/丘陵）尾部留 1 空 → 格與格之間自然現出空隙、不靠線。
    # 連續地物（城/河/橋）填滿 3 寬 → 本就該連續，不留隙。
    ".": ("   ", "color(28)",  "color(22)"),
    "F": ("♣♣ ", "color(40)",  "color(22)"),
    "H": ("︿ ", "color(180)", "color(94)"),
    "U": ("███", "color(231)", "color(240)"),
    "R": ("≈≈≈", "color(51)",  "color(24)"),
    "B": ("══╪", "color(214)", "color(94)"),
    "S": ("~~~", "color(109)", "color(60)"),
    "K": ("⌗⌗ ", "color(64)",  "color(22)"),   # Bocage 樹籬田野(諾曼第)：移動×0.4、守方×2.0、視距0.5
}
MAJ_V, MAJ_S = "│", "color(250)"   # 主垂直線（每5格，亮）
MIN_V, MIN_S = "┆", "color(237)"   # 次垂直線（每格，暗）
LBL_S = "bold color(45)"           # 座標標籤色
ULINE_FG = "color(245)"            # 橫線(underline)統一色：套在無筆畫處的前景，使底線一致
GLINE = "color(245)"


def _vline(x):
    """欄位 x 左緣的垂直線字元與樣式（x 可為 0..W）。
    主線(每5格)畫 │；次線位置留空格 → 消除每格分裂感、只當自然間隔。"""
    if x % GRID_STEP == 0:
        return MAJ_V, MAJ_S
    return " ", MIN_S


def _xlabel_row(W):
    """頂/底座標列：數字對齊每格內容起點。左右各留 3 寬 gutter 對稱。"""
    g = Text()
    g.append("   ")          # 左 y 座標 gutter(3)
    g.append(" ")            # 第0欄垂直線位
    for x in range(W):
        g.append(pad(str(x), INT + 1) if x % GRID_STEP == 0 else " " * (INT + 1), LBL_S)
    g.append("   ")          # 右 gutter 對稱
    g.append("\n")
    return g


def _unit_interior(uid, u, headings):
    """組單位內容到 3 顯示寬，回傳 [(text, style)] 片段。
    番號(白) + 兵種(黃) + 朝向(亮白)，空間不足時優先保番號與朝向。"""
    num = num2(uid)
    hd = HEADING_GLYPH.get(headings.get(uid, ""), "")
    ty = TYPE_GLYPH.get(u["type"], "●")
    segs = [(num, "bold white")]
    if hd:
        if wcswidth(num + ty + hd) <= INT:
            segs.append((ty, "bold yellow"))
            segs.append((hd, "bold bright_white"))
        else:                       # 2 位番號：捨兵種、保朝向
            segs.append((hd, "bold bright_white"))
    else:
        segs.append((ty, "bold yellow"))
    used = sum(wcswidth(t) for t, _ in segs)
    if used < INT:
        segs.append((" " * (INT - used), ""))
    return segs


CURSOR_BG = "color(45)"   # 游標格高亮底色（青）


CURSOR_BG = "color(45)"   # 游標格高亮底色（青），commander.py 編輯用


# ── 補給走廊層（PvP 補給線）──────────────────────────────────────
SUPPLY_DASH = {
    "intact":    ("╌╌╌", "color(24)"),        # 暗藍＝暢通
    "contested": ("╌╌╌", "color(178)"),       # 黃＝受威脅
    "cut":       ("╌╌╌", "bold color(196)"),  # 紅＝切斷
}


def compute_supply(state, sides=("allies", "axis")):
    """回傳 {(x,y): 'intact'/'contested'/'cut'}。藍(allies)補給源=西緣、紅(axis)=東緣；
    走廊=同橫排從編隊拉回本方邊緣。切斷=敵佔走廊格(編隊與源之間)、受威脅=敵距走廊1格。"""
    W = state["map"]["width"]
    units = state.get("units", {})
    sev = {"intact": 0, "contested": 1, "cut": 2}
    out = {}
    for uid, u in units.items():
        if u.get("is_detachment") or u.get("side") not in sides:
            continue
        side = u["side"]
        ux, uy = u["pos"]
        src = 0 if side == "allies" else W - 1
        if ux == src:
            continue
        step = -1 if src < ux else 1
        corridor = list(range(ux + step, src + step, step))   # 由近而遠
        enemies = {(e["pos"][0], e["pos"][1]) for e in units.values()
                   if e.get("side") and e["side"] != side}
        block = next((cx for cx in corridor if (cx, uy) in enemies), None)
        for cx in corridor:
            if block is not None and ((step < 0 and cx >= block) or (step > 0 and cx <= block)):
                st = "cut"
            else:
                st = "intact"
                for (ex, ey) in enemies:
                    if abs(ex - cx) <= 1 and abs(ey - uy) <= 1:
                        st = "contested"
                        break
            k = (cx, uy)
            if k not in out or sev[st] > sev[out[k]]:
                out[k] = st
    return out


def render_A(s, pos_unit, obj_tiles, ov, headings, grid=True, cursor=None,
             viewer_side="god", supply=None):
    W, H = s["map"]["width"], s["map"]["height"]
    terr = s["map"]["terrain"]
    g = Text()
    # 頂部 x 座標列：加 underline → 畫出 y=0 上緣的橫線
    g.append_text(_xlabel_row(W) if not grid else _xlabel_row_ul(W))
    for y in range(H):
        # 橫線靠「下一列為格線列時，本列加 underline」實現（線畫在本列底＝下列頂）。
        is_ul = grid and (y + 1) % GRID_STEP == 0
        ul = " underline" if is_ul else ""
        # 橫線列：無筆畫處前景統一成格線色，使底線整條同色（不影響可見字/塊）。
        lbl_fg = ULINE_FG if is_ul else None
        g.append(f"{y:>2} ", (f"bold {lbl_fg}{ul}" if is_ul else f"{LBL_S}"))  # 左 y 座標
        row = terr[y] if y < len(terr) else ""
        for x in range(W):
            t = row[x] if x < len(row) else "."   # 容錯：地形列不規則不致 IndexError
            _, fgt, bg = A_TERRAIN.get(t, ("   ", "white", "color(16)"))
            is_cur = cursor is not None and (x, y) == tuple(cursor)
            # 垂直線欄：套地形底色避免暗縫；underline 列前景統一成橫線色。
            if grid:
                vch, vs = _vline(x)
                vfg = ULINE_FG if is_ul else vs
                g.append(vch, f"{vfg} on {bg}{ul}")
            # 內容欄（3 寬）；游標格底色覆蓋成高亮青
            cbg = CURSOR_BG if is_cur else bg
            if (x, y) in pos_unit:
                uid, u = pos_unit[(x, y)]
                # 敵我顏色：god 視角按陣營(盟藍/軸紅)；玩家視角以「觀看者立場」為準
                #   → 我方=藍 color(21)、敵方=紅 color(124)，符合直覺。
                if viewer_side in ("allies", "axis"):
                    friendly = (u["side"] == viewer_side)
                else:
                    friendly = (u["side"] == "allies")  # god: 盟軍藍、軸心紅
                ubg = CURSOR_BG if is_cur else ("color(21)" if friendly else "color(124)")
                for txt, st in _unit_interior(uid, u, headings):
                    g.append(txt, f"{st} on {ubg}{ul}".strip())
            elif (x, y) in ov:
                glyph, col, _ = ov[(x, y)]
                g.append(pad(glyph, INT), f"bold {col} on {cbg}{ul}")
            elif (x, y) in obj_tiles:
                fill = A_TERRAIN.get(t, ("   ",))[0]
                g.append(pad("◆" + fill[1:], INT), f"bold yellow on {cbg}{ul}")
            else:
                sup = supply.get((x, y)) if supply else None
                if sup and t == ".":         # 補給層：只在空的開闊格畫虛線、遇字元自然斷
                    dash, dcol = SUPPLY_DASH[sup]
                    g.append(pad(dash, INT), f"{dcol} on {cbg}{ul}")
                else:
                    # 平原(全空格)在 underline 列改用統一橫線色當前景 → 底線同色
                    fg = ULINE_FG if (is_ul and t == ".") else fgt
                    g.append(pad(fill_of(t), INT), f"{fg} on {cbg}{ul}")
        # 最右邊界線（用最後一格地形底色）
        if grid:
            last_t = row[W - 1] if (W - 1) < len(row) else "."
            _, _, rbg = A_TERRAIN.get(last_t, ("   ", "white", "color(16)"))
            vch, vs = _vline(W)
            vfg = ULINE_FG if is_ul else vs
            g.append(vch, f"{vfg} on {rbg}{ul}")
        g.append(f" {y:<2}", (f"bold {lbl_fg}{ul}" if is_ul else f"{LBL_S}"))  # 右 y 座標
        g.append("\n")
    g.append_text(_xlabel_row(W))                # 底部 x 座標（無 underline）
    return g


def _xlabel_row_ul(W):
    """頂部 x 座標列 + underline（=畫出 y=0 上緣橫線）。
    座標數字與空格前景統一成橫線色 → 底線整條同色。"""
    g = Text()
    g.append("    ", f"{ULINE_FG} underline")          # gutter(3)+第0欄線位(1)
    for x in range(W):
        txt = pad(str(x), INT + 1) if x % GRID_STEP == 0 else " " * (INT + 1)
        g.append(txt, f"bold {ULINE_FG} underline")
    g.append("   ", f"{ULINE_FG} underline")
    g.append("\n")
    return g


def fill_of(t):
    return A_TERRAIN.get(t, ("?  ",))[0]


def render_map(state, annot=None, grid=True, cursor=None, preview=None,
               viewer_side="god", supply=None):
    """一步到位渲染：state(+annot) → rich Text。
    cursor: (x,y) 高亮游標格。 preview: 額外暫時 overlay {(x,y):(glyph,color,kind)}。
    viewer_side: god/allies/axis — 戰爭迷霧視角（見 index_state）。
    supply: {(x,y):status} 補給走廊層（compute_supply 產出）；None=不畫。"""
    if annot is None:
        annot = load_annot()
    pos_unit, obj_tiles, _ = index_state(state, viewer_side=viewer_side)
    W, H = state["map"]["width"], state["map"]["height"]
    ov = build_overlay(annot, W, H)
    if preview:
        ov = {**ov, **preview}
    headings = {k: v for k, v in annot.get("headings", {}).items()
                if not k.startswith("_")}
    return render_A(state, pos_unit, obj_tiles, ov, headings,
                    grid=grid, cursor=cursor, viewer_side=viewer_side, supply=supply)


# ════════════════════════════════════════════════════════════════════
# 風格 B：NATO 軍事符號 — 克制配色，制式軍標 token
# ════════════════════════════════════════════════════════════════════
B_TERRAIN = {
    ".": (".", "color(238)"),
    "F": ("♣", "color(65)"),
    "H": ("^", "color(94)"),
    "U": ("#", "color(250)"),
    "R": ("|", "color(38)"),
    "B": ("=", "color(208)"),
    "S": ("~", "color(60)"),
}
NATO = {"infantry": "I", "armor": "O", "motorized": "M", "panzergrenadier": "X"}
def render_B(s, pos_unit, obj_tiles, ov, headings):
    W, H = s["map"]["width"], s["map"]["height"]
    terr = s["map"]["terrain"]
    g = colnum_row(W)
    for y in range(H):
        g.append(f"{y:>2} ", "dim cyan")
        for x in range(W):
            t = terr[y][x]
            if (x, y) in pos_unit:
                uid, u = pos_unit[(x, y)]
                col = "bright_blue" if u["side"] == "allies" else "bright_red"
                hd = HEADING_GLYPH.get(headings.get(uid, ""), "")
                sym = hd or NATO.get(u["type"], "I")
                g.append(pad(f"{sym}{num2(uid)}", CELL), f"bold {col}")
            elif (x, y) in ov:
                glyph, ocol, _ = ov[(x, y)]
                g.append(pad(glyph, CELL), f"bold {ocol}")
            elif (x, y) in obj_tiles:
                o = obj_tiles[(x, y)]
                cc = "red" if o.get("controller") == "axis" else "blue"
                g.append(pad("[#]", CELL), f"bold {cc}")
            else:
                glyph, fg = B_TERRAIN.get(t, ("?", "white"))
                g.append(pad(glyph, CELL), fg)
        g.append("\n")
    return g


# ════════════════════════════════════════════════════════════════════
# 風格 C：資訊密集儀表 — 單位底色濃淡 = 兵力高低，暗色地形省眼
# ════════════════════════════════════════════════════════════════════
C_TERRAIN = {
    ".": ("·", "color(237)", "color(233)"),
    "F": ("♣", "color(28)",  "color(233)"),
    "H": ("^", "color(94)",  "color(234)"),
    "U": ("▓", "color(250)", "color(236)"),
    "R": ("≈", "color(31)",  "color(17)"),
    "B": ("╪", "color(214)", "color(94)"),
    "S": ("~", "color(60)",  "color(17)"),
}
def str_bg(side, hp):
    if side == "allies":
        return "color(17)" if hp >= 75 else ("color(20)" if hp >= 40 else "color(53)")
    return "color(52)" if hp >= 75 else ("color(130)" if hp >= 40 else "color(94)")
def render_C(s, pos_unit, obj_tiles, ov, headings):
    W, H = s["map"]["width"], s["map"]["height"]
    terr = s["map"]["terrain"]
    g = colnum_row(W)
    for y in range(H):
        g.append(f"{y:>2} ", "dim cyan")
        for x in range(W):
            t = terr[y][x]
            if (x, y) in pos_unit:
                uid, u = pos_unit[(x, y)]
                bg = str_bg(u["side"], u["strength"])
                fg = "bright_cyan" if u["side"] == "allies" else "bright_yellow"
                hd = HEADING_GLYPH.get(headings.get(uid, ""), "")
                body = num2(uid) + (hd or ("▲" if u["type"] == "armor" else "●"))
                g.append(pad(body, CELL), f"bold {fg} on {bg}")
            else:
                glyph, fg, bg = C_TERRAIN.get(t, ("?", "white", "color(16)"))
                if (x, y) in ov:
                    oglyph, ocol, _ = ov[(x, y)]
                    g.append(pad(oglyph, CELL), f"bold {ocol} on {bg}")
                elif (x, y) in obj_tiles:
                    o = obj_tiles[(x, y)]
                    oc = "bright_red" if o.get("controller") == "axis" else "bright_blue"
                    g.append(pad("◈", CELL), f"bold {oc} on {bg}")
                else:
                    g.append(pad(glyph, CELL), f"{fg} on {bg}")
        g.append("\n")
    return g


LEGENDS = {
 "A": "擬真地形｜♣森林 ︿丘陵 █城鎮 ≈河流 ══╪橋｜◆=目標｜單位格=番號+兵種(黃:●步▲裝■擲◆摩)+朝向箭頭",
 "B": "NATO軍標｜I步兵 O裝甲 M摩化 X擲彈｜字色藍/紅=陣營｜[#]=目標｜地形 ASCII 淡化",
 "C": "資訊儀表｜單位底色深→殘血｜◈=目標｜青字我方/黃字敵方｜暗地形省眼力",
}
RENDERERS = {"1": ("A", render_A), "2": ("B", render_B), "3": ("C", render_C)}


def annot_legend(annot):
    """列出標註圖層內容（指揮官的標記/箭頭/文字）。"""
    items = annot.get("annotations", [])
    if not items and not annot.get("headings"):
        return None
    g = Text()
    g.append("指揮官圖層：\n", "bold")
    for a in items:
        k = a.get("type")
        col = a.get("color", "white")
        lab = a.get("label", "")
        if k == "arrow":
            g.append(f"  → {a['from']}→{a['to']}  ", col)
            g.append(f"{lab}\n", col)
        elif k == "marker":
            g.append(f"  {a.get('glyph','*')} {tuple(a['pos'])}  ", col)
            g.append(f"{lab}\n", col)
        elif k == "text":
            g.append(f"  ▸ {tuple(a['pos'])}  ", col)
            g.append(f"{lab}\n", col)
        elif k == "phase_line":
            g.append(f"  ┊ x={a['x']}  ", col)
            g.append(f"{lab}\n", col)
        elif k == "polyline":
            pts = a.get("points", [])
            g.append(f"  ┊ {len(pts)}點折線  ", col)
            g.append(f"{lab}\n", col)
    hd = annot.get("headings", {})
    hd = {k: v for k, v in hd.items() if not k.startswith("_")}
    if hd:
        g.append("  朝向：" + "  ".join(f"{u}{HEADING_GLYPH.get(d,d)}" for u, d in hd.items()) + "\n", "dim")
    return g


def show(key, fn, s, pu, ot, ov, headings, console):
    console.print(Panel(fn(s, pu, ot, ov, headings), title=f"[bold]風格 {key}[/]",
                        subtitle=LEGENDS[key], border_style="green"))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    s, pu, ot, spotted = load()
    annot = load_annot()
    W, H = s["map"]["width"], s["map"]["height"]
    ov = build_overlay(annot, W, H)
    headings = {k: v for k, v in annot.get("headings", {}).items() if not k.startswith("_")}
    console = Console()
    keys = ["1", "2", "3"] if arg == "all" else ([arg] if arg in RENDERERS else [])
    if not keys:
        print("用法: python3 map_proto.py [1|2|3|all]"); return
    for num in keys:
        key, fn = RENDERERS[num]
        show(key, fn, s, pu, ot, ov, headings, console)
    leg = annot_legend(annot)
    if leg:
        console.print(Panel(leg, title="[bold]標註圖層內容（demo）[/]", border_style="magenta"))

if __name__ == "__main__":
    main()
