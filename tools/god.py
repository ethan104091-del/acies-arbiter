#!/usr/bin/env python3
"""上帝視角 —— 觀戰用。看得到雙方的一切。

## 誰可以用這個

**只有不擔任指揮官的人。** Run 7 的雙方都由 AI 指揮、人類觀戰,所以這支腳本
給人類看。若哪一局人類自己下場打,**這支腳本就不得使用**——它會直接洩漏
對手的全部部署,包括未被偵獲的編隊、指揮所位置、彈藥存量與命令佇列。

兩位 AI 指揮官在任何情況下都不得執行本檔(他們連 `~/war-game/` 都不該讀)。

## 用法

    python3 tools/god.py              # 印一次
    python3 tools/god.py -w           # 每 2 秒重印(盯解算過程)
    python3 tools/god.py -f <state>   # 看指定的快照,例如某個 snap_T3start.json

比 `arbiter.god_md()` 多的東西:彈藥實數、工事 hex 記憶、雙方偵獲清單的差集
(誰看得到誰、誰在暗處)、延遲中的命令佇列、以及最近的逐時事件。
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import arbiter as ar          # noqa: E402
import command                # noqa: E402
import hourstate as hs        # noqa: E402

ZH = {"allies": "藍軍", "axis": "紅軍"}
C = {"allies": "\033[94m", "axis": "\033[91m", "dim": "\033[2m",
     "bold": "\033[1m", "warn": "\033[93m", "off": "\033[0m"}


def paint(t, k):
    return f"{C[k]}{t}{C['off']}"


def unit_block(s, side):
    out = []
    sup = ar.supply_status(s)
    for uid, u in sorted(ar.own(s, side).items()):
        if u.get("is_detachment"):
            tag = paint("〔抽離〕", "dim")
        else:
            tag = ""
        st = ar.status_of(u)
        stt = "" if st == "ACTIVE" else paint(f" [{st}]", "warn")
        out.append(f"  {paint(uid, side)}{tag} {u['name']} @{tuple(u['pos'])}{stt}")
        out.append(f"      兵 {u.get('personnel',0):>6}｜戰力 {u.get('strength')}%"
                   f"｜組織 {u.get('org'):>5.1f}｜疲勞 {u.get('fatigue'):>3}"
                   f"｜戰車 {u['equip']['tanks']:>3}｜火砲 {u['equip']['guns']:>3}"
                   f"｜補給 {sup.get(uid,'?')}")
        # 彈藥
        am, mx = u.get("ammo") or {}, u.get("ammo_max") or {}
        if am:
            bits = []
            for g, v in sorted(am.items()):
                cap = mx.get(g) or 1
                p = 100.0 * v / cap
                txt = f"{g} {v:,.0f}({p:.0f}%)"
                bits.append(paint(txt, "warn") if p < 35 else txt)
            out.append("      彈藥 " + "｜".join(bits))
        # 工事與能見
        mh = ar.hex_works(s, u["pos"])
        per = mh / max(u.get("personnel", 1), 1)
        tier = ar.fort_tier(u.get("fortification", 0.0))[0]
        camo = "偽裝完成" if u.get("camouflaged") else (
            f"偽裝{u.get('camo_hours',0):.1f}/{ar.CAMO_HOURS}" if u.get("camo_hours") else "—")
        out.append(f"      工事 {tier}(本格 {mh:,.0f}mh = {per:.2f}hr/人)"
                   f"｜能見 {u['visibility_state']}｜{camo}"
                   f"｜損失 {u['losses']['personnel']}人/{u['losses']['tanks']}車/"
                   f"{u['losses']['guns']}砲")
        if u.get("last_action"):
            out.append(f"      {paint('上一動作: ' + str(u['last_action'])[:78], 'dim')}")
    return "\n".join(out)


def intel_block(s):
    """誰看得到誰。差集就是「在暗處的部隊」——觀戰最想知道的東西。"""
    out = []
    for side in ("allies", "axis"):
        e = ar.ENEMY[side]
        seen = set(s.get("fog_of_war", {}).get(f"{side}_spotted", []))
        alive = {u for u, x in s["units"].items() if x.get("side") == e}
        dark = sorted(alive - seen)
        cps = s.get("fog_of_war", {}).get(f"{side}_spotted_cps", [])
        out.append(f"  {paint(ZH[side], side)} 偵獲 {len(seen)}/{len(alive)}："
                   f"{'、'.join(sorted(seen)) or '（無）'}")
        if dark:
            out.append(f"      {paint('在暗處: ' + '、'.join(dark), 'warn')}")
        out.append(f"      已偵獲敵指揮所: {'、'.join(cps) or '（無）'}")
    return "\n".join(out)


def cmd_block(s):
    out = []
    for side in ("allies", "axis"):
        c = s["command"][side]
        out.append(f"  {paint(ZH[side], side)} {ar.cp_line(s, side)}")
        pend = hs.pending_for(s, side)
        for o in pend:
            out.append(f"      {paint('延遲中', 'dim')} [{o['level']}] "
                       f"「{o['text'][:60]}」還要 {o['hours_until_effective']}hr")
        if not pend:
            out.append(f"      {paint('延遲中: (無)', 'dim')}")
    return "\n".join(out)


def works_block(s):
    w = {k: v.get("man_hours", 0.0) for k, v in (s.get("works") or {}).items()
         if v.get("man_hours", 0) > 0}
    if not w:
        return "  （尚無任何構築）"
    rows = sorted(w.items(), key=lambda kv: -kv[1])[:12]
    by = s.get("works", {})
    return "\n".join(
        f"  ({k})  {v:>9,.0f} man-hours　{paint('由 ' + ZH.get(by[k].get('by'), '?') + ' 構築', by[k].get('by') or 'dim')}"
        for k, v in rows)


def score_block(s):
    sc = ar.score(s)
    a, x = sc["allies"], sc["axis"]
    lead = "allies" if a["points"] > x["points"] else ("axis" if x["points"] > a["points"] else None)
    out = [f"  {paint('藍軍', 'allies')} {a['points']:>6} 分　{a['inflicted']}",
           f"  {paint('紅軍', 'axis')} {x['points']:>6} 分　{x['inflicted']}"]
    if lead:
        out.append(f"  → {paint(ZH[lead] + ' 領先 ' + str(abs(a['points']-x['points'])) + ' 分', lead)}")
    else:
        out.append("  → 平手")
    return "\n".join(out)


LOG_W = 150


def fmt_log(e):
    """逐時事件。舊 state 存的是 dict、新的是字串,兩種都要吃。

    一條 gh 的 summary 可以長到兩千字(把該小時每一門砲的明細都列進去),
    整條倒出來會把畫面洗掉。這裡截斷——要看完整明細去讀該方的戰報或 tick 腳本輸出。
    """
    if isinstance(e, dict):
        t = e.get("summary") or json.dumps(e, ensure_ascii=False)
    else:
        t = str(e)
    t = t.replace("\n", " ")
    return t if len(t) <= LOG_W else t[:LOG_W] + paint(f"…（{len(t)}字,已截斷）", "dim")


def render(s, log_n=16):
    L = []
    L.append(paint(f"═══ 上帝視角 — {ar.clock(s)} ═══", "bold"))
    L.append("")
    L.append(ar.ascii_map(s, "god"))
    L.append("")
    L.append(paint("── 藍軍 ──", "allies"))
    L.append(unit_block(s, "allies"))
    L.append(paint("── 紅軍 ──", "axis"))
    L.append(unit_block(s, "axis"))
    L.append(paint("── 指揮系統與延遲中的命令 ──", "bold"))
    L.append(cmd_block(s))
    L.append(paint("── 偵獲狀況（差集＝在暗處的部隊）──", "bold"))
    L.append(intel_block(s))
    L.append(paint("── 工事累積（前 12 格）──", "bold"))
    L.append(works_block(s))
    L.append(paint("── 殲敵計分（自傷不計入對手）──", "bold"))
    L.append(score_block(s))
    hl = s.get("hour_log", [])[-log_n:]
    if hl:
        L.append(paint(f"── 最近 {len(hl)} 條逐時事件 ──", "bold"))
        L += [f"  {t}" for t in map(fmt_log, hl)]
    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(description="上帝視角（觀戰用，指揮官不得使用）")
    p.add_argument("-w", "--watch", action="store_true", help="每 2 秒重印")
    p.add_argument("-f", "--file", help="指定 state 檔（預設讀現行 state）")
    p.add_argument("-n", "--log", type=int, default=16, help="顯示幾條逐時事件")
    a = p.parse_args()

    def load():
        # ar.load(path) 會補齊欄位預設值,直接讀 raw JSON 會缺 equip/ammo 等欄(缺陷 19)
        return ar.load(Path(a.file)) if a.file else ar.load()

    if not a.watch:
        print(render(load(), a.log))
        return
    try:
        while True:
            print("\033[2J\033[H" + render(load(), a.log), flush=True)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n（結束）")


if __name__ == "__main__":
    main()
