#!/usr/bin/env python3
"""戰場即時檢視器 (viewer)。

讀 state.json + annotations.json，用 mapcore 渲染擬真地形網格 + 指揮官標註圖層，
右側顯示部隊 / 補給細目 / 氣象 / 敵情 / 戰報。每 0.5s file-watch 自動重繪。

地圖渲染與標註邏輯都在 mapcore.py（與 commander.py 共用）。
本檔只負責 Live 版面組裝與右側資訊面板。

用法： python3 ~/war-game/map.py
"""
import json
import time
from pathlib import Path
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

import mapcore as mc
import orbat as ob_mod  # 營級編制（取代舊 detachments）
import command as cmd_mod  # 指揮所/延遲/斬首（PvP）

GAME_DIR = Path.home() / "war-game"
STATE_PATH = GAME_DIR / "state.json"
LOG_PATH = GAME_DIR / "combat_log.jsonl"

CTRL_LABEL = {"allies": "我方", "axis": "敵方", "contested": "爭奪中"}
TYPE_ZH = {"infantry": "步兵", "armor": "裝甲", "motorized": "摩化", "panzergrenadier": "擲彈兵",
           "artillery": "砲兵", "recon": "偵察", "engineer": "工兵",
           "antitank": "反戰車", "ranger": "特戰"}
VIS_ZH = {"BLIND": "盲", "MINIMAL": "微", "STANDARD": "標", "ENHANCED": "強", "FULL": "全"}
RES_ORDER = ["POL", "SA", "HE", "AT", "RAT", "MED", "PARTS"]


def _bar_color(v):
    return "green" if v >= 75 else ("yellow" if v >= 40 else "red")


def _avg_supply(u):
    res = u.get("resources")
    if isinstance(res, dict) and res:
        vals = [v for v in res.values() if isinstance(v, (int, float))]
        return round(sum(vals) / len(vals)) if vals else 0
    return u.get("supply", 0)


def spotted_set(state):
    return set(state.get("fog_of_war", {}).get("allies_spotted", []))


def cp_overlay(state, view, friendly):
    """指揮所地圖標記 overlay {(x,y):(glyph,color,kind)}。
    god 看雙方；玩家只看自己方（敵指揮所須靠偵察，暫不顯示）。
    軍長所在的指揮所加★標記。"""
    ov = {}
    sides = ("allies", "axis") if view == "god" else (friendly,)
    for side in sides:
        cmd = state.get("command", {}).get(side, {})
        col = "bold color(21)" if side == "allies" else "bold color(124)"
        at = cmd.get("commander_at")
        for kind, gl in (("main", "主"), ("fwd", "前")):
            pos = cmd.get(f"{kind}_cp")
            if pos:
                mark = (gl + "★") if at == kind else gl   # 軍長所在＝★
                ov[tuple(pos)] = (mark, col, "cp")
    return ov


# ── 右側資訊面板 ───────────────────────────────────────────────────
def render_header(state):
    obj = state.get("objectives", {})
    run = state.get("campaign_run", "?")
    pool = state.get("campaign_pool", {})
    name = state.get("scenario_name", "黑潮行動 — Operation Black Tide")
    wx = state.get("weather") or state.get("weather_state", {}).get("current", {}).get("note", "?")
    title = f"[bold cyan]{name}[/]" + (f" [dim]Run {run}[/]" if run != "?" else "")
    lines = [
        title,
        f"回合 [yellow]{state['tick']}/{state['max_ticks']}[/]  ⏱ {state.get('game_time', '')}",
        f"☁ 天候：{wx}",
    ]
    # hour 級資訊（若 state 已升級）
    if "global_hour" in state:
        hr = f"小時 [yellow]{state.get('hour_in_tick', 0)}/6[/]（全局 {state['global_hour']}）"
        phase = state.get("phase", "")
        pend = state.get("pending_orders", [])
        npend = sum(1 for o in pend if o.get("status") == "pending")
        extra = f"  延遲令 {npend}" if npend else ""
        lines.append(f"{hr}  [dim]{phase}[/]{extra}")
    if pool:
        lines.append(
            f"[dim]物資池 盟[/][blue]{pool.get('allies_tons', 0)//1000}k[/]"
            f"[dim]噸 / 軸[/][red]{pool.get('axis_tons', 0)//1000}k[/][dim]噸[/]"
        )
    if obj.get("type") == "attrition":           # PvP 消耗型：無地圖目標
        lines += ["", f"[bold]勝負：[/][dim]{obj.get('note', '殲敵較多者勝')}[/]"]
        return "\n".join(lines)
    lines += ["", "[bold]戰略目標：[/]"]
    for key, o in obj.items():
        if not isinstance(o, dict):
            continue
        ctrl = o.get("controller", "?")
        color = "blue" if ctrl == "allies" else ("red" if ctrl == "axis" else "yellow")
        marker = "■" if ctrl == "allies" else ("□" if ctrl == "axis" else "▣")
        pos = o.get("pos", [0, 0])
        lines.append(
            f"  [{color}]{marker} {o['name']}[/] ({pos[0]},{pos[1]}) "
            f"[dim]{CTRL_LABEL.get(ctrl, ctrl)}[/]"
        )
    return "\n".join(lines)


def render_forces(state, friendly="allies"):
    table = Table(show_edge=False, expand=True, padding=(0, 0))
    for c, j in [("番", "left"), ("兵種", "left"), ("座標", "center"),
                 ("兵", "right"), ("組", "right"), ("補", "right"),
                 ("疲", "right"), ("視", "center")]:
        table.add_column(c, justify=j, no_wrap=True,
                         style="bold cyan" if c == "番" else None)
    # 先列母師，分遣隊縮排排在母師下方
    divs = [(uid, u) for uid, u in state["units"].items()
            if u["side"] == friendly and not u.get("is_detachment")]
    dets_by_parent = {}
    for uid, u in state["units"].items():
        if u["side"] == friendly and u.get("is_detachment"):
            dets_by_parent.setdefault(u.get("parent"), []).append((uid, u))

    def add_unit(uid, u, indent=False):
        pos_str = f"{u['pos'][0]:>2},{u['pos'][1]:<2}"
        if u.get("hidden"):
            pos_str = f"[dim]{pos_str}隱[/]"
        sup = _avg_supply(u)
        fat = u.get("fatigue", 0)
        fc = "green" if fat < 30 else ("yellow" if fat < 60 else "red")
        label = (f"[dim]└[/]{u['short']}" if indent else u["short"])
        table.add_row(
            label, TYPE_ZH.get(u["type"], u["type"][:4]), pos_str,
            f"[{_bar_color(u['strength'])}]{u['strength']}[/]",
            f"[{_bar_color(u['org'])}]{u['org']}[/]",
            f"[{_bar_color(sup)}]{sup}[/]",
            f"[{fc}]{fat}[/]",
            VIS_ZH.get(u.get("visibility_state", ""), "·"),
        )

    for uid, u in divs:
        add_unit(uid, u)
        for duid, du in dets_by_parent.get(uid, []):
            add_unit(duid, du, indent=True)
        # 母師下方：用兵種短碼摘要「師內還有哪些營」(已拉出的不列)。
        # 完整編制樹用 orbat 面板看(orbat_panel)。
        ob = u.get("orbat", {})
        if ob:
            in_div = [TYPE_TAG.get(b["type"], "?") for b in ob.values()
                      if b.get("status") == "in_division" and b["type"] != "hq"]
            from collections import Counter
            cnt = Counter(in_div)
            summary = " ".join(f"{t}{n}" for t, n in cnt.items())
            if summary:
                table.add_row("[dim]└在師[/]", "[dim]" + summary + "[/]",
                              "", "", "", "", "", "")
    return table


# 兵種 → 單字短碼（面板/編制樹摘要用）
TYPE_TAG = {
    "infantry": "步", "armor": "裝", "mech_inf": "裝步", "panzergrenadier": "擲",
    "artillery": "砲", "recon": "偵", "engineer": "工", "antitank": "反",
    "aa": "防", "ranger": "特", "hq": "部",
}


def render_orbat(state, friendly="allies"):
    """完整營級編制樹面板：每師列出所有營(碼/名/兵種/人數/狀態)。"""
    from rich.table import Table as _T
    t = _T(show_edge=False, expand=True, padding=(0, 0))
    t.add_column("營", style="bold", no_wrap=True)
    t.add_column("兵種", no_wrap=True)
    t.add_column("人", justify="right")
    t.add_column("狀態", no_wrap=True)
    for uid, u in state["units"].items():
        if u["side"] != friendly or u.get("is_detachment"):
            continue
        ob = u.get("orbat", {})
        if not ob:
            continue
        t.add_row(f"[cyan]{u['short']}[/]", "", f"{u.get('personnel','?')}", "")
        for code, b in ob.items():
            st = b.get("status", "in_division")
            if st == "in_division":
                stxt = "[dim]在師[/]"
            elif st == "detached":
                stxt = "[yellow]已拉出[/]"
            else:
                stxt = f"[green]{st}[/]"
            t.add_row(f" [dim]{code}[/]", TYPE_TAG.get(b["type"], b["type"][:2]),
                      f"{b.get('personnel','')}", stxt)
    return t


def render_supply_detail(state, friendly="allies"):
    table = Table(show_edge=False, expand=True, padding=(0, 0))
    table.add_column("番", style="bold cyan", no_wrap=True)
    for r in RES_ORDER:
        table.add_column(r, justify="right")
    for uid, u in state["units"].items():
        if u["side"] != friendly:
            continue
        res = u.get("resources", {})
        cells = [u["short"]]
        for r in RES_ORDER:
            v = res.get(r)
            cells.append("[dim]-[/]" if v is None else f"[{_bar_color(v)}]{v}[/]")
        table.add_row(*cells)
    return table


def render_intel(state, friendly="allies"):
    """敵情面板：顯示敵方(非 friendly)。
    god 視角下 state 完整 → 用 fog 判定哪些偵獲；
    玩家視角下 state 已被 filter_state_for 過濾 → 未偵獲的敵師根本不在 units，
    偵獲的只有 strength_approx，沒有完整 strength。"""
    enemy = "axis" if friendly == "allies" else "allies"
    table = Table(show_edge=False, expand=True, padding=(0, 0))
    table.add_column("番", style="bold red", no_wrap=True)
    table.add_column("兵種", no_wrap=True)
    table.add_column("座標", justify="center", no_wrap=True)
    table.add_column("兵", justify="right")
    spotted = set(state.get("fog_of_war", {}).get(f"{friendly}_spotted", []))
    any_enemy = False
    for uid, u in state["units"].items():
        if u["side"] != enemy:
            continue
        any_enemy = True
        # 偵獲判定：在 spotted 名單，或（已過濾 state）只剩公開欄=已偵獲
        seen = uid in spotted or "strength" not in u
        if seen:
            approx = u.get("strength_approx", u.get("strength"))
            table.add_row(
                u["short"], TYPE_ZH.get(u["type"], u["type"][:4]),
                f"{u['pos'][0]:>2},{u['pos'][1]:<2}",
                f"~{approx}" if approx is not None else "?")
        else:
            table.add_row(u["short"], "[dim]?[/]", "[dim]?[/]", "[dim]?[/]")
    if not any_enemy:
        table.add_row("[dim]無接觸[/]", "", "", "")
    return table


def render_weather(state):
    ws = state.get("weather_state")
    if not ws:
        return f"☁ {state.get('weather', '?')}"
    cur = ws.get("current", {})
    actual = ws.get("campaign_actual", {})
    cur_tick = state.get("tick", 0)
    lines = [
        f"[bold]當前[/] T{cur_tick}：{state.get('weather', '?')}",
        f"  能見 {cur.get('visibility_km', '?')}km  "
        f"CAS×[{'green' if cur.get('cas_modifier',1)>=0.8 else 'red'}]{cur.get('cas_modifier','?')}[/]  "
        f"移動×{cur.get('move_modifier','?')}",
        "",
        "[bold]戰役天氣表（已寫死）：[/]",
    ]
    for i in range(state.get("max_ticks", 8) + 1):
        w = actual.get(f"T{i}")
        if not w:
            continue
        cas = w.get("cas", 1.0)
        cas_c = "green" if cas >= 0.8 else ("yellow" if cas > 0 else "red")
        mark = "[reverse]" if i == cur_tick else ""
        markend = "[/]" if i == cur_tick else ""
        prec = w.get("precipitation", "?").replace("_", " ")
        lines.append(f"{mark}T{i}{markend} {prec[:12]:<12} CAS[{cas_c}]{cas}[/] 移{w.get('move','?')}")
    return "\n".join(lines)


def render_log():
    lines = []
    if LOG_PATH.exists():
        try:
            raw = LOG_PATH.read_text().splitlines()
        except Exception:
            raw = []
        for line in raw[-14:]:
            try:
                e = json.loads(line)
                lines.append(f"[dim]回{e.get('tick','?')}[/] [{e.get('color','white')}]{e.get('msg','')}[/]")
            except Exception:
                pass
    return "\n".join(lines) if lines else "[dim](尚無戰報)[/dim]"


def render_annot_summary(annot):
    items = annot.get("annotations", [])
    hd = {k: v for k, v in annot.get("headings", {}).items() if not k.startswith("_")}
    if not items and not hd:
        return "[dim](無標註 — 執行 commander.py 編輯)[/dim]"
    out = []
    for a in items:
        k = a.get("type")
        col = a.get("color", "white")
        lab = a.get("label", "")
        if k == "arrow":
            out.append(f"[{col}]→ {tuple(a['from'])}→{tuple(a['to'])}[/] {lab}")
        elif k == "marker":
            out.append(f"[{col}]{a.get('glyph','*')} {tuple(a['pos'])}[/] {lab}")
        elif k == "text":
            out.append(f"[{col}]▸ {tuple(a['pos'])}[/] {lab}")
        elif k == "phase_line":
            out.append(f"[{col}]┊ x={a['x']}[/] {lab}")
        elif k == "polyline":
            out.append(f"[{col}]┊ 折線×{len(a.get('points',[]))}[/] {lab}")
    if hd:
        out.append("[dim]朝向 " + " ".join(
            f"{u}{mc.HEADING_GLYPH.get(d,d)}" for u, d in hd.items()) + "[/]")
    return "\n".join(out)


# ── 版面 ───────────────────────────────────────────────────────────
def make_layout():
    """地圖橫跨上方全寬（只需 ~111 寬）；面板移到下方分三欄，
    終端機總寬需求從 ~358 降到 ~115。"""
    layout = Layout()
    layout.split_column(
        Layout(name="map", size=23),       # 地圖：20 內容 + 框 + 標題
        Layout(name="panels"),             # 下方面板區
    )
    layout["panels"].split_row(
        Layout(name="col1", ratio=1),
        Layout(name="col2", ratio=1),
        Layout(name="col3", ratio=1),
    )
    layout["col1"].split_column(
        Layout(name="header", size=15),
        Layout(name="forces"),
    )
    layout["col2"].split_column(
        Layout(name="weather", size=13),
        Layout(name="supply"),
    )
    layout["col3"].split_column(
        Layout(name="intel", size=8),
        Layout(name="annot", size=8),
        Layout(name="log"),
    )
    return layout


SIDE_ZH = {"god": "上帝視角（GM）", "allies": "盟軍 III Corps", "axis": "德軍 Panzergruppe"}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="戰場檢視器")
    ap.add_argument("--side", choices=["god", "allies", "axis"], default="god",
                    help="視角：god=裁判看全部(預設)；allies/axis=玩家視角(只看自己+偵獲敵軍)")
    ap.add_argument("--state", default=str(STATE_PATH),
                    help="要載入的 state 檔（預設 state.json；PvP 用 maps/open_field_state.json）")
    ap.add_argument("--supply", action="store_true",
                    help="疊上補給走廊層（虛線：藍暢通/黃威脅/紅切斷）")
    args = ap.parse_args()
    view = args.side
    friendly = "allies" if view in ("god", "allies") else "axis"
    state_path = Path(args.state)

    console = Console()
    layout = make_layout()
    with Live(layout, console=console, refresh_per_second=2, screen=True):
        while True:
            try:
                if not state_path.exists():
                    layout["map"].update(Panel(f"[red]{state_path.name} not found.[/]"))
                    time.sleep(1)
                    continue
                full_state = json.loads(state_path.read_text())
                # 玩家視角：先過濾(敵方內部資料根本不進這支程式)；god 用完整 state
                state = full_state if view == "god" else mc.filter_state_for(full_state, view)
                render_state = full_state if view == "god" else state
                # 標註依劇本載入：黑潮用全域 annotations.json；其他劇本用 maps/<id>_annot.json（無則空）
                scen = full_state.get("scenario_id", "black_tide")
                if scen == "black_tide":
                    annot = mc.load_annot()
                else:
                    _ap = GAME_DIR / "maps" / f"{scen}_annot.json"
                    annot = (json.loads(_ap.read_text()) if _ap.exists()
                             else {"annotations": [], "headings": {}})
                # 補給層：god 看雙方；玩家只看自己那方
                sup = None
                if args.supply:
                    sides = ("allies", "axis") if view == "god" else (friendly,)
                    sup = mc.compute_supply(render_state, sides=sides)
                cp_ov = cp_overlay(render_state, view, friendly)   # 指揮所標記
                map_text = mc.render_map(render_state, annot=annot, grid=True,
                                         viewer_side=view, supply=sup,
                                         preview=cp_ov or None)
                # 地圖框寬度 = 內容寬 + 左右框各1（padding=0），避免框撐滿區塊留右側空白帶
                from rich.cells import cell_len
                map_w = max((cell_len(l) for l in map_text.plain.split("\n") if l.strip()),
                            default=107) + 2
                layout["map"].update(Panel(
                    map_text,
                    title=f"[bold]料鋒 ACIES[/] [dim]{full_state.get('scenario_name', '戰場')} ｜ {SIDE_ZH[view]}[/]",
                    subtitle="[dim]●步 ▲裝 ■擲 ◆摩 ｜ ♣森林 ⌗樹籬 ︿丘 █城 ≈河 ╪橋 ｜ →軸線 ?疑敵[/]",
                    border_style="green", width=map_w, padding=0))
                layout["supply"].update(Panel(
                    render_supply_detail(state, friendly),
                    title="[blue]我方補給細目 (POL/SA/HE/AT/RAT/MED/PARTS)[/]",
                    border_style="blue"))
                layout["annot"].update(Panel(
                    render_annot_summary(annot),
                    title="[magenta]指揮官圖層[/]", border_style="magenta"))
                layout["header"].update(Panel(render_header(state), title="戰況", border_style="cyan"))
                layout["forces"].update(Panel(
                    render_forces(state, friendly),
                    title="[blue]我方部隊（兵/組/補/疲/視）[/]", border_style="blue"))
                layout["weather"].update(Panel(render_weather(state), title="[cyan]氣象[/]", border_style="cyan"))
                layout["intel"].update(Panel(render_intel(state, friendly), title="[red]敵情[/]", border_style="red"))
                layout["log"].update(Panel(render_log(), title="戰報", border_style="yellow"))
            except Exception as e:
                layout["map"].update(Panel(f"[red]Error: {e}[/]"))
            time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
