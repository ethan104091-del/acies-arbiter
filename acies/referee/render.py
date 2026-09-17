"""卷宗尾段的確定性渲染：同一狀態永遠渲染出同一位元組（鍵排序、固定小數位）。"""
import arbiter as ar
import command
import hourstate as hs

SIDES = ("allies", "axis")
ZH = {"allies": "藍軍", "axis": "紅軍"}


def _f(x, nd=1):
    return f"{float(x):.{nd}f}"


def state_table(s):
    lines = ["## 全知狀態", "",
             f"gh{s['global_hour']}　{hs.game_time_str(s['global_hour'])}　{hs.daynight(s['global_hour'])}　"
             f"tick {s['tick']}/{s['max_ticks']}　hour {s['hour_in_tick']}", ""]
    for side in SIDES:
        lines += [f"### {ZH[side]}", "",
                  "| 編隊 | 位置 | 人員 | 戰車 | 火砲 | 彈藥 | 組織 | 疲勞 | 工事 | 偽裝 | 能見 | 狀態 | 補給 | 上小時旗標 |",
                  "|---|---|---:|---:|---:|---|---:|---:|---|---|---|---|---|---|"]
        for uid, u in sorted(s["units"].items()):
            if u.get("side") != side:
                continue
            ammo = "／".join(f"{g}:{int(v)}" for g, v in sorted((u.get("ammo") or {}).items()))
            camo = "✓" if u.get("camouflaged") else (_f(u.get("camo_hours", 0)) if u.get("camo_hours") else "")
            flags = ",".join(k for k, v in sorted((u.get("flags") or {}).items()) if v)
            lines.append(f"| {uid} | {tuple(u['pos'])} | {u.get('personnel', 0)} | {u['equip'].get('tanks', 0)} | "
                         f"{u['equip'].get('guns', 0)} | {ammo} | {_f(u.get('org', 0))} | {u.get('fatigue', 0)} | "
                         f"{ar.fort_tier(u.get('fortification', 0.0))[3]} {_f(u.get('fortification', 0.0), 2)} | {camo} | "
                         f"{u.get('visibility_state', '')} | {ar.status_of(u)} | {u.get('supply_status', '')} | {flags} |")
        lines.append("")
        cmd = s.get("command", {}).get(side, {})
        lines.append(f"指揮所：主 {cmd.get('main_cp')}　前進 {cmd.get('fwd_cp')}　軍長在 {cmd.get('commander_at')}"
                     f"　架設中 {cmd.get('pending_cp', [])}")
        lines.append(f"偵獲：{sorted(s.get('fog_of_war', {}).get(f'{side}_spotted', []))}"
                     f"　偵獲指揮所：{sorted(s.get('fog_of_war', {}).get(f'{side}_spotted_cps', []))}")
        lines.append("")
    works = s.get("works", {})
    if works:
        lines += ["### 工事（格：工時，歸屬）", "",
                  "、".join(f"({k}):{_f(v.get('man_hours', 0))}{v.get('by', '')[:1]}" for k, v in sorted(works.items())), ""]
    po = [o for o in s.get("pending_orders", []) if o.get("status") == "pending"]
    if po:
        lines += ["### 待生效命令（引擎佇列）", ""]
        lines += [f"- {o['side']} {o['level']} gh{o['effective_global_hour']} 生效：{o['text'][:80]}" for o in po]
        lines.append("")
    sc = ar.score(s)
    lines.append(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}")
    return "\n".join(lines)


def feasibility_table(s):
    """後端算好的可行性：受指揮、可射擊、射程內已偵獲敵、相鄰敵佔格、上小時旗標。"""
    from acies.engine import verbs as V
    lines = ["## 可行性表", "", "| 編隊 | 受指揮 | 可射擊 | 射程內已偵獲敵（距離） | 相鄰敵佔格 | 最低資源 |", "|---|---|---|---|---|---|"]
    for uid, u in sorted(s["units"].items()):
        side = u.get("side")
        if side not in SIDES:
            continue
        enemy = ar.ENEMY[side]
        spotted = set(s.get("fog_of_war", {}).get(f"{side}_spotted", []))
        inr = []
        for e in sorted(spotted):
            eu = s["units"].get(e)
            if eu and eu.get("side") == enemy and ar.status_of(eu) in ar.COMBAT_STATUSES and V.in_range(s, uid, eu["pos"]):
                inr.append(f"{e}({ar.dist(u['pos'], eu['pos'])})")
        adj = sorted({tuple(x["pos"]) for x in s["units"].values()
                      if x.get("side") == enemy and ar.status_of(x) in ar.COMBAT_STATUSES
                      and ar.dist(u["pos"], x["pos"]) == 1})
        res = u.get("resources") or {}
        low = min(res.values()) if res else ""
        lines.append(f"| {uid} | {'是' if ar.under_command(s, uid) else '否'} | {'是' if V.can_fire(s, uid) else '否'} | "
                     f"{'、'.join(inr)} | {adj if adj else ''} | {_f(low) if low != '' else ''} |")
    return "\n".join(lines)


def clause_ledger(clauses):
    lines = ["## 條款帳", ""]
    if not clauses:
        return "\n".join(lines + ["（尚無條款）"])
    for c in sorted(clauses, key=lambda c: (c["side"], c["clause_id"])):
        lines.append(f"- **{c['clause_id']}**［{c['side']}／{c['kind']}／{c['status']}］"
                     f" 生效 gh{c.get('effective_gh')}　取代 {c.get('supersedes') or []}"
                     + (f"　被 {c['superseded_by']} 取代" if c.get("superseded_by") else "")
                     + (f"　已用於 gh{c['consumed_gh']}" if c.get("consumed_gh") is not None else ""))
        lines.append(f"  原文：{c['text']}")
        if c.get("predicate"):
            lines.append(f"  述詞：{c['predicate']}")
        if c.get("phase"):
            lines.append(f"  階段：{dict(sorted(c['phase'].items()))}")
    return "\n".join(lines)


def previous_hour(prev, prev_exec):
    if not prev:
        return "## 上一小時\n\n（無：本小時為本桌第一小時或登記之後的首小時）"
    lines = ["## 上一小時的決定與事件", ""]
    for a in sorted(prev.get("actions", []), key=lambda a: a["seq"]):
        lines.append(f"- seq {a['seq']} {'二級 ' + str(a.get('ruling_id')) if a.get('tier') == 2 else a.get('verb')} "
                     f"{a.get('args', {})} ← {a['provenance']['clause_id']}")
    if prev_exec:
        lines += ["", "事件："]
        lines += [f"- [{t}] {x}" for t, x in prev_exec.get("events", [])]
        for r in prev_exec.get("results", []):
            if r.get("result") is not None:
                lines.append(f"- 結果 seq {r['seq']}：{r['result']}")
    return "\n".join(lines)


def adjudications(items):
    if not items:
        return ""
    lines = ["## 待裁定回覆與指示", ""]
    for p in items:
        a = p.get("answer") or {}
        lines.append(f"- {p['pending_id']}（{p['kind']}）→ {a.get('kind')}：{a.get('public_text') or a.get('private_text', '')}")
    return "\n".join(lines)
