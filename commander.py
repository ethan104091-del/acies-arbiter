#!/usr/bin/env python3
"""指揮官圖標編輯器 (interactive editor)。

curses 互動：方向鍵移游標，在地圖上自由放置標記 / 文字 / 箭頭 / 折線，
存進 annotations.json。map.py（檢視器）會 file-watch 自動重繪出漂亮版本。

座標系統、標註 schema、地形/兵種定義都沿用 mapcore.py（與檢視器一致）。

用法： python3 ~/war-game/commander.py
除錯： CMDR_DEBUG=1 python3 commander.py  → 按鍵與動作寫入 /tmp/cmdr_debug.log
"""
import curses
import json
import locale
import os
from pathlib import Path

import mapcore as mc
from wcwidth import wcswidth

GAME_DIR = Path.home() / "war-game"
STATE_PATH = GAME_DIR / "state.json"
ANNOT_PATH = GAME_DIR / "annotations.json"

_DBG = os.environ.get("CMDR_DEBUG")


def dbg(msg):
    if _DBG:
        with open("/tmp/cmdr_debug.log", "a") as f:
            f.write(msg + "\n")


# 可循環選用的標記字元（狀況標記）
MARKER_GLYPHS = ["!", "?", "*", "x", "+", "▲", "●", "■", "✶", "⚑"]
# 可循環選用的顏色（rich 名稱 → curses 256 色號）
COLORS = [
    ("yellow", 226), ("red", 196), ("cyan", 51), ("green", 46),
    ("magenta", 201), ("white", 231), ("orange", 208), ("blue", 39),
]
# 地形 → (3寬字元, curses前景, curses背景)  近似 mapcore 風格 A
TERRAIN_C = {
    ".": ("   ", 28, 22),
    "F": ("♣♣ ", 40, 22),
    "H": ("︿ ", 180, 94),
    "U": ("███", 231, 240),
    "R": ("≈≈≈", 51, 24),
    "B": ("══╪", 214, 94),
    "S": ("~~~", 109, 60),
}
GRID_FG = 245
HELP_FOOT = "方向鍵/hjkl移動  m標記 t文字 a箭頭 p折線 H朝向  g換符 c換色 d刪除  s存 r載 q離開 ?說明"


def fit3(s):
    """裁/補到顯示寬 3（中文算 2）。"""
    w = wcswidth(s)
    if w == 3:
        return s
    if w < 3:
        return s + " " * (3 - w)
    out, cur = "", 0
    for ch in s:
        cw = wcswidth(ch)
        if cur + cw > 3:
            break
        out += ch
        cur += cw
    return out + " " * (3 - cur)


def color_num(name):
    for n, num in COLORS:
        if n == name:
            return num
    return 231


class Editor:
    def __init__(self, state, annot, viewer_side="god"):
        self.state = state
        self.viewer_side = viewer_side
        self.W = state["map"]["width"]
        self.H = state["map"]["height"]
        self.terr = state["map"]["terrain"]
        self.pos_unit, self.obj_tiles, _ = mc.index_state(state, viewer_side=viewer_side)
        self.annot = annot
        self.cx = self.cy = 0
        self.glyph_i = 0
        self.color_i = 0
        self.dirty = False
        self.msg = "就緒。按 ? 看說明。"
        self.last_key = None
        self.pair_cache = {}
        self.next_pair = 1
        self.arrow_from = None
        self.poly_pts = None

    # ── curses 色彩對 ───────────────────────────────────────────
    def pair(self, fg, bg):
        key = (fg, bg)
        if key not in self.pair_cache:
            if self.next_pair >= min(curses.COLOR_PAIRS, 256):
                return curses.color_pair(0)
            try:
                curses.init_pair(self.next_pair, fg, bg)
            except curses.error:
                return curses.color_pair(0)
            self.pair_cache[key] = self.next_pair
            self.next_pair += 1
        return curses.color_pair(self.pair_cache[key])

    @property
    def color_name(self):
        return COLORS[self.color_i][0]

    @property
    def glyph(self):
        return MARKER_GLYPHS[self.glyph_i]

    # ── overlay（含進行中的預覽）─────────────────────────────────
    def overlay(self):
        ov = mc.build_overlay(self.annot, self.W, self.H)
        if self.arrow_from:
            ov[tuple(self.arrow_from)] = ("◎", self.color_name, "marker")
        if self.poly_pts:
            for i in range(len(self.poly_pts) - 1):
                for c in mc._line_cells(*self.poly_pts[i], *self.poly_pts[i + 1]):
                    ov[c] = ("┊", self.color_name, "phase_line")
            for p in self.poly_pts:
                ov[tuple(p)] = ("◎", self.color_name, "marker")
        return ov

    # ── 繪製 ────────────────────────────────────────────────────
    def draw(self, scr):
        scr.erase()
        maxy, maxx = scr.getmaxyx()
        need_w = 3 + self.W * 4 + 4
        if maxx < need_w or maxy < self.H + 7:
            scr.addstr(0, 0, f"終端太小：需 {need_w}x{self.H+7}，現 {maxx}x{maxy}")
            scr.refresh()
            return
        ov = self.overlay()
        headings = {k: v for k, v in self.annot.get("headings", {}).items()
                    if not k.startswith("_")}

        scr.addstr(0, 0, "指揮官圖標編輯器 — Operation Black Tide", curses.A_BOLD)
        mode = f"標記[{self.glyph}] 色[{self.color_name}] 游標({self.cx},{self.cy})"
        if self.arrow_from:
            mode = f"▶箭頭起{tuple(self.arrow_from)} 移到迄點按a或Enter  " + mode
        if self.poly_pts is not None:
            mode = f"▶折線已{len(self.poly_pts)}點 p加點/Enter結束/Esc取消  " + mode
        scr.addstr(1, 0, mode[:maxx - 1])

        top = 3
        xaxis = "   "
        for x in range(self.W):
            xaxis += (f"{x:<4}" if x % 5 == 0 else "    ")
        scr.addstr(top - 1, 0, xaxis[:maxx - 1], curses.A_DIM)

        for y in range(self.H):
            scr.addstr(top + y, 0, f"{y:>2} ", curses.A_DIM)
            col = 3
            for x in range(self.W):
                t = self.terr[y][x]
                _, tfg, tbg = TERRAIN_C.get(t, ("   ", 28, 22))
                vch = "│" if x % 5 == 0 else " "
                try:
                    scr.addstr(top + y, col, vch, self.pair(GRID_FG, tbg))
                except curses.error:
                    pass
                col += 1
                txt, fg, bg = self._cell(x, y, ov, headings)
                attr = self.pair(fg, bg)
                if (x, y) == (self.cx, self.cy):
                    attr |= curses.A_REVERSE | curses.A_BOLD
                try:
                    scr.addstr(top + y, col, txt, attr)
                except curses.error:
                    pass
                col += 3
            try:
                scr.addstr(top + y, col, "│", self.pair(GRID_FG, 0))
                scr.addstr(top + y, col + 1, f" {y}", curses.A_DIM)
            except curses.error:
                pass

        by = top + self.H + 1
        cnt = len(self.annot.get("annotations", []))
        flag = "[未存]" if self.dirty else ""
        scr.addstr(by, 0, f"標註 {cnt} 筆 {flag}  {self.msg}"[:maxx - 1], curses.A_BOLD)
        scr.addstr(by + 1, 0, HELP_FOOT[:maxx - 1], curses.A_DIM)
        if self.last_key is not None:
            tag = f"key={self.last_key}"
            try:
                scr.addstr(by + 1, max(0, maxx - len(tag) - 1), tag, curses.A_DIM)
            except curses.error:
                pass
        scr.refresh()

    def _cell(self, x, y, ov, headings):
        t = self.terr[y][x]
        glyph, tfg, tbg = TERRAIN_C.get(t, ("   ", 28, 22))
        if (x, y) in self.pos_unit:
            uid, u = self.pos_unit[(x, y)]
            bg = 21 if u["side"] == "allies" else 124
            num = mc.num2(uid)
            ty = mc.TYPE_GLYPH.get(u["type"], "●")
            hd = mc.HEADING_GLYPH.get(headings.get(uid, ""), "")
            return fit3(num + ty + hd), 231, bg
        if (x, y) in ov:
            gl, colname, _ = ov[(x, y)]
            return fit3(gl), color_num(colname), tbg
        if (x, y) in self.obj_tiles:
            return fit3("◆" + glyph[1:]), 226, tbg
        return fit3(glyph), tfg, tbg

    # ── 標註操作 ────────────────────────────────────────────────
    def _new_id(self):
        existing = {a.get("id") for a in self.annot.get("annotations", [])}
        n = 1
        while f"a{n}" in existing:
            n += 1
        return f"a{n}"

    def add(self, a):
        self.annot.setdefault("annotations", []).append(a)
        self.dirty = True
        dbg(f"add {a.get('type')} {a.get('label','')} count={len(self.annot['annotations'])}")

    def place_marker(self, scr):
        label = self._input(scr, f"標記 {self.glyph} @({self.cx},{self.cy}) 說明(可空): ")
        self.add({"id": self._new_id(), "type": "marker",
                  "pos": [self.cx, self.cy], "glyph": self.glyph,
                  "color": self.color_name, "label": label})
        self.msg = f"放置標記 {self.glyph} @({self.cx},{self.cy})"

    def place_text(self, scr):
        label = self._input(scr, f"文字 @({self.cx},{self.cy}): ")
        if not label:
            self.msg = "取消（文字為空）"
            return
        self.add({"id": self._new_id(), "type": "text",
                  "pos": [self.cx, self.cy], "color": self.color_name, "label": label})
        self.msg = f"放置文字 @({self.cx},{self.cy})"

    def toggle_arrow(self, scr):
        if self.arrow_from is None:
            self.arrow_from = [self.cx, self.cy]
            self.msg = f"箭頭起點 ({self.cx},{self.cy})，移到迄點再按 a 或 Enter"
        else:
            label = self._input(scr, "箭頭說明(可空): ")
            self.add({"id": self._new_id(), "type": "arrow",
                      "from": self.arrow_from, "to": [self.cx, self.cy],
                      "color": self.color_name, "label": label})
            self.msg = f"箭頭 {tuple(self.arrow_from)}→({self.cx},{self.cy})"
            self.arrow_from = None

    def poly_step(self):
        if self.poly_pts is None:
            self.poly_pts = []
        self.poly_pts.append([self.cx, self.cy])
        self.msg = f"折線 第{len(self.poly_pts)}點 ({self.cx},{self.cy})，Enter結束"

    def poly_finish(self, scr):
        if not self.poly_pts or len(self.poly_pts) < 2:
            self.poly_pts = None
            self.msg = "折線取消（點太少）"
            return
        label = self._input(scr, "折線/戰線說明(可空): ")
        self.add({"id": self._new_id(), "type": "polyline",
                  "points": self.poly_pts, "color": self.color_name, "label": label})
        self.msg = f"折線 {len(self.poly_pts)} 點完成"
        self.poly_pts = None

    def delete_here(self):
        items = self.annot.get("annotations", [])
        for i, a in enumerate(items):
            if self._covers(a, self.cx, self.cy):
                items.pop(i)
                self.dirty = True
                self.msg = f"刪除 {a.get('type')} {a.get('label','')}"
                return
        self.msg = "游標處無標註"

    def _covers(self, a, x, y):
        k = a.get("type")
        if k in ("marker", "text"):
            return tuple(a.get("pos", [])) == (x, y)
        if k == "arrow":
            return (x, y) in mc._line_cells(*a["from"], *a["to"])
        if k == "polyline":
            pts = a.get("points", [])
            for i in range(len(pts) - 1):
                if (x, y) in mc._line_cells(*pts[i], *pts[i + 1]):
                    return True
        if k == "phase_line":
            return x == a.get("x") and a.get("y0", 0) <= y <= a.get("y1", self.H)
        return False

    def set_heading(self, scr):
        if (self.cx, self.cy) not in self.pos_unit:
            self.msg = "游標不在單位上"
            return
        uid, _ = self.pos_unit[(self.cx, self.cy)]
        d = self._input(scr, f"{uid} 朝向 (N/S/E/W/NE/NW/SE/SW，空=清除): ").upper()
        hd = self.annot.setdefault("headings", {})
        if d in mc.HEADING_GLYPH:
            hd[uid] = d
            self.msg = f"{uid} 朝向 {d}"
        else:
            hd.pop(uid, None)
            self.msg = f"{uid} 朝向已清除"
        self.dirty = True

    # ── 底部單行輸入（get_wch 自繪迴圈，可靠處理中文/Enter/退格/Esc）──
    def _input(self, scr, prompt):
        dbg(f"_input ENTER {prompt!r}")
        maxy, maxx = scr.getmaxyx()
        row = maxy - 1
        curses.curs_set(1)
        buf = ""
        while True:
            scr.move(row, 0)
            scr.clrtoeol()
            try:
                scr.addstr(row, 0, (prompt + buf)[:maxx - 1], curses.A_BOLD)
            except curses.error:
                pass
            scr.refresh()
            try:
                wch = scr.get_wch()
            except curses.error:
                continue
            if isinstance(wch, str):
                if wch in ("\n", "\r"):
                    break
                if wch == "\x1b":
                    buf = ""
                    break
                if wch in ("\x7f", "\x08"):
                    buf = buf[:-1]
                elif wch >= " ":
                    buf += wch
            else:
                if wch in (curses.KEY_ENTER,):
                    break
                if wch in (curses.KEY_BACKSPACE, 127, 8):
                    buf = buf[:-1]
        curses.curs_set(0)
        dbg(f"_input RETURN {buf.strip()!r}")
        return buf.strip()

    def save(self):
        try:
            ANNOT_PATH.write_text(json.dumps(self.annot, ensure_ascii=False, indent=2))
        except OSError as e:
            self.msg = f"存檔失敗：{e}"   # 磁碟滿/無權限不該讓編輯器崩潰丟資料
            dbg(f"save FAILED: {e}")
            return
        self.dirty = False
        self.msg = f"已存 → {ANNOT_PATH.name}（{len(self.annot.get('annotations',[]))} 筆）"
        dbg(f"save -> {ANNOT_PATH} count={len(self.annot.get('annotations',[]))}")

    def reload(self):
        self.annot = mc.load_annot()
        self.dirty = False
        self.arrow_from = None
        self.poly_pts = None
        self.msg = "已重載 annotations.json"


def show_help(scr):
    scr.erase()
    scr.addstr(0, 0, "指揮官圖標編輯器 — 操作說明", curses.A_BOLD)
    lines = [
        "",
        "移動：方向鍵 或 h/j/k/l（左/下/上/右）",
        "",
        "放置：",
        "  m  標記（目前標記字元+顏色，會問說明文字）",
        "  t  文字（在格上放一段文字標籤）",
        "  a  箭頭：第一次按=設起點，移到迄點再按 a 或 Enter=完成",
        "  p  折線：每按加一個轉折點，Enter 結束，Esc 取消",
        "  H  單位朝向：游標移到單位上按 H，輸入 N/S/E/W/NE…",
        "",
        "調整：",
        "  g  切換標記字元（! ? * x + ▲ ● ■ ✶ ⚑）",
        "  c  切換顏色（黃/紅/青/綠/洋紅/白/橙/藍）",
        "  d  刪除游標處的標註",
        "",
        "檔案：",
        "  s  存檔到 annotations.json（map.py 會自動重繪）",
        "  r  重載 annotations.json（捨棄未存變更）",
        "  q  離開（有未存變更會詢問）",
        "",
        "輸入文字時：Enter 確認、退格刪字、Esc 取消。",
        "",
        "按任意鍵返回。",
    ]
    for i, ln in enumerate(lines):
        try:
            scr.addstr(1 + i, 0, ln)
        except curses.error:
            pass
    scr.refresh()
    scr.get_wch()


def run(scr):
    curses.curs_set(0)
    scr.keypad(True)               # 方向鍵/Enter/退格 轉成 KEY_*（勿省略）
    try:
        curses.set_escdelay(25)    # 縮短 Esc 反應（Python 3.9+）
    except Exception:
        pass
    try:
        curses.use_default_colors()
    except curses.error:
        pass
    if not STATE_PATH.exists():
        scr.addstr(0, 0, "找不到 state.json — 請先確認 ~/war-game/state.json 存在")
        scr.get_wch()
        return
    try:
        state = json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        scr.addstr(0, 0, f"state.json 讀取失敗：{e}")
        scr.addstr(1, 0, "按任意鍵離開。")
        scr.get_wch()
        return
    # 玩家視角：先過濾，敵方底牌根本不進編輯器（縱深防禦，與 map.py 一致）
    if VIEW != "god":
        state = mc.filter_state_for(state, VIEW)
    ed = Editor(state, mc.load_annot(), viewer_side=VIEW)

    while True:
        ed.draw(scr)
        try:
            ch = scr.get_wch()
        except curses.error:
            continue
        # 統一成「字串字元」或「整數特殊鍵」兩種比對
        is_str = isinstance(ch, str)
        ed.last_key = repr(ch)
        dbg(f"main ch={ch!r} arrow={ed.arrow_from} poly={ed.poly_pts}")

        def k(c):
            return is_str and ch == c

        if k("q") or k("Q"):
            if ed.dirty:
                ans = ed._input(scr, "有未存變更，存檔再離開? (y/n/c): ").lower()
                if ans == "y":
                    ed.save()
                    break
                if ans == "n":
                    break
                continue
            break
        elif ch == curses.KEY_LEFT or k("h"):
            ed.cx = max(0, ed.cx - 1)
        elif ch == curses.KEY_RIGHT or k("l"):
            ed.cx = min(ed.W - 1, ed.cx + 1)
        elif ch == curses.KEY_UP or k("k"):
            ed.cy = max(0, ed.cy - 1)
        elif ch == curses.KEY_DOWN or k("j"):
            ed.cy = min(ed.H - 1, ed.cy + 1)
        elif k("m"):
            ed.place_marker(scr)
        elif k("t"):
            ed.place_text(scr)
        elif k("a"):
            ed.toggle_arrow(scr)
        elif k("p"):
            ed.poly_step()
        elif ch in ("\n", "\r") or ch == curses.KEY_ENTER:
            if ed.poly_pts is not None:
                ed.poly_finish(scr)
            elif ed.arrow_from is not None:
                ed.toggle_arrow(scr)
            else:
                ed.msg = "Enter 無作用（先按 a 起箭頭或 p 起折線）"
        elif ch == "\x1b":
            if ed.poly_pts is not None:
                ed.poly_pts = None
                ed.msg = "折線取消"
            elif ed.arrow_from is not None:
                ed.arrow_from = None
                ed.msg = "箭頭取消"
        elif k("g"):
            ed.glyph_i = (ed.glyph_i + 1) % len(MARKER_GLYPHS)
        elif k("c"):
            ed.color_i = (ed.color_i + 1) % len(COLORS)
        elif k("d"):
            ed.delete_here()
        elif k("H"):
            ed.set_heading(scr)
        elif k("s"):
            ed.save()
        elif k("r"):
            ed.reload()
        elif k("?"):
            show_help(scr)


VIEW = "god"   # 由 main() 依 --side 設定；run() 透過此 global 取得視角


def main():
    global VIEW
    import argparse
    ap = argparse.ArgumentParser(description="指揮官圖標編輯器")
    ap.add_argument("--side", choices=["god", "allies", "axis"], default="god",
                    help="視角：god=裁判(預設,看全部)；allies/axis=玩家視角(只看自己+偵獲敵軍)")
    args = ap.parse_args()
    VIEW = args.side
    # curses 處理中文/UTF-8 輸入與寬字元（get_wch/addstr 中文都需要）
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    curses.wrapper(run)


if __name__ == "__main__":
    main()
