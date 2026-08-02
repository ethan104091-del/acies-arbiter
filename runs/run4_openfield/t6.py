#!/usr/bin/env python3
"""Tick 6 解算（gh36-41, 1944-08-26 18:00-24:00：gh36 黃昏、gh37-41 夜間）★雙方砲兵對決★

延遲：紅軍前進指揮所罩內 → 基準（L1→gh37）；藍軍僅主指揮所 → +1（L1→gh38、L2→gh39）。
夜間視距：師級 2／特戰 3／偵察營 3 —— 砲擊必須有單位在目標的偵獲距離內（裁示 27、夜間後果）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, hourstate as hs, command

s = of.load()
for u in s["units"].values():
    u.setdefault("fortification", 0.0)

for lvl, txt in [("L1", "RED-1 固守 (18,12)，由 RED-1-rcn 觀測對 BLU-3 集中砲擊"),
                 ("L1", "RED-2 固守 (19,8)，共享觀測對 BLU-3 集中砲擊"),
                 ("L1", "RED-AD 固守 (18,8)，共享觀測對 BLU-3 集中自走砲火，不以戰車追擊"),
                 ("L1", "RED-3 固守 (18,3)，由 RED-3-rcn 觀測對 BLU-SF (20,4) 砲擊壓制，不入森林追擊")]:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=0)
for lvl, txt in [("L1", "全線就地構築工事至滿（取消 BLU-2 前往 (15,11)）；挖滿後完全休整"),
                 ("L1", "砲兵分火：105群+自走砲群→RED-AD；155群→RED-1；失去觀測則改打射程內可觀測目標"),
                 ("L1", "BLU-AD-eng 與 BLU-AD 同格，替其構工事並作第四兵種"),
                 ("L2", "BLU-AD-rcn→(12,10) 退出敵砲射程完全休整"),
                 ("L1", "BLU-SF 就地構築工事至滿，固守不出林、不主動攻擊"),
                 ("L1", "觀測所固守：BLU-3-rcn (17,13)、BLU-1-rcn (14,5)、BLU-2-rcn (8,12)，遭砲擊不後撤"),
                 ("L1", "三個警衛營維持 (4,10) 固守，任何情況不得離開")]:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=1)

# 藍軍 T5 常態令：BLU-2 仍在前往 (15,11)（T6 的取消令 gh38 才生效）
ROUTES = {"BLU-2": [(15, 11)]}
BLUE_DIG = {"BLU-1", "BLU-3", "BLU-AD", "BLU-SF"}        # gh36-37 已在挖（T5 令）
log = []


def observed(s, side, tuid):
    """該方是否有單位在目標的偵獲距離內（夜間視距已含在 sight_of）。"""
    return tuid in s["fog_of_war"].get(f"{side}_spotted", [])


def fire(s, shooters, tuid, ev, side, label):
    shooters = [x for x in shooters if x in s["units"]
                and s["units"][x]["equip"]["guns"] > 0
                and of.dist(s["units"][x]["pos"], s["units"][tuid]["pos"]) <= 5]
    if not shooters:
        return False
    cas, tk, gk, msg = of.bombard(s, shooters, tuid)
    if not (cas or tk or gk):
        return False
    of.hurt(s, tuid, personnel=cas, tanks=tk, guns=gk,
            org=round(cas / max(s["units"][tuid]["personnel"], 1) * 150, 1), fatigue=3,
            note="遭敵砲擊")
    for x in shooters:
        s["units"][x]["flags"]["fired"] = True
        of.consume(s, x, "L3")
    ev.append((side, f"我方{label}射擊敵 {tuid}：{msg}"))
    ev.append((tuid, f"{tuid} 遭敵砲擊：傷亡 {cas} 人"
                     + (f"、-{tk} 戰車" if tk else "") + (f"、-{gk} 火砲" if gk else "")))
    return True


for gh in range(36, 42):
    command.activate_due_cps(s)
    hs.hour_brief(s)
    ev = []
    if gh == 38:
        ROUTES.pop("BLU-2", None)          # 藍軍取消移動令生效
        BLUE_DIG.add("BLU-2")
        ev.append(("allies", "BLU-2 移動令取消生效 → 就地構築工事"))

    # ── 紅軍砲擊（gh37 起）──
    if gh >= 37:
        if observed(s, "axis", "BLU-3"):
            fire(s, ["RED-1", "RED-2", "RED-AD"], "BLU-3", ev, "axis", "三編隊集中砲兵")
        else:
            ev.append(("axis", "本 hour 對 BLU-3 失去觀測 → 依命令停止砲擊、固守"))
        if observed(s, "axis", "BLU-SF"):
            fire(s, ["RED-3"], "BLU-SF", ev, "axis", "RED-3 砲兵")
        else:
            ev.append(("axis", "本 hour 對 BLU-SF 失去觀測 → 停止砲擊"))

    # ── 藍軍砲擊：gh36-37 用 T5 舊令（優先未構工事的敵步兵師）；gh38 起用新分火令 ──
    blue_shooters = ["BLU-1", "BLU-2", "BLU-3", "BLU-AD"]
    vis = [t for t in ("RED-AD", "RED-1", "RED-2", "RED-3") if observed(s, "allies", t)]
    if gh < 38:
        cand = [t for t in vis if s["units"][t]["type"] == "infantry"] or vis
        if cand:
            fire(s, blue_shooters, cand[0], ev, "allies", "全軍砲兵集中")
        else:
            ev.append(("allies", "本 hour 無可觀測的敵師級目標 → 停止射擊"))
    else:
        # 105 群（三個師）＋自走砲群 → RED-AD；失去觀測或不在射程 → 改打「射程內可觀測、裝備價值最高者」
        def in_range_of_any(t):
            return any(of.dist(s["units"][x]["pos"], s["units"][t]["pos"]) <= 5
                       for x in blue_shooters if x in s["units"])
        vis_ir = [t for t in vis if in_range_of_any(t)]
        t105 = "RED-AD" if "RED-AD" in vis_ir else (
            max(vis_ir, key=lambda t: s["units"][t]["equip"]["tanks"]) if vis_ir else None)
        t155 = "RED-1" if "RED-1" in vis_ir else (vis_ir[0] if vis_ir else None)
        if t105 and t155 and t105 == t155:
            fire(s, blue_shooters, t105, ev, "allies", "全砲群集中（兩群同目標）")
            if "RED-AD" not in vis_ir:
                ev.append(("allies", f"（RED-AD 夜間失去觀測／不在射程 → 105 群依命令改打射程內裝備價值最高者 {t105}）"))
        else:
            if t105:
                fire(s, blue_shooters, t105, ev, "allies", "105群＋自走砲群")
            else:
                ev.append(("allies", "105 群本 hour 無可觀測且在射程的目標 → 停止射擊"))
            if t155:
                fire(s, ["BLU-1", "BLU-2", "BLU-3"], t155, ev, "allies", "155群")

    # ── 移動 ──
    for uid in list(ROUTES):
        wps = ROUTES.get(uid)
        if not wps or uid not in s["units"]:
            continue
        moved, msg = of.advance(s, uid, wps[0])
        if moved:
            ev.append((uid, msg))
        if list(s["units"][uid]["pos"]) == list(wps[0]):
            ROUTES.pop(uid)
    if gh >= 39 and s["units"]["BLU-AD-rcn"]["pos"] != [12, 10]:
        moved, msg = of.advance(s, "BLU-AD-rcn", (12, 10))
        if moved:
            ev.append(("BLU-AD-rcn", msg))

    # ── 工事構築（只有明確下令者）──
    for uid in sorted(BLUE_DIG):
        u = s["units"].get(uid)
        if not u or u["flags"].get("moved") or u.get("fortification", 0) >= 0.5:
            continue
        rate = 0.1875 if uid in ("BLU-1", "BLU-2", "BLU-3", "BLU-AD") else 0.125
        u["fortification"] = round(min(0.5, u["fortification"] + rate), 4)
        ev.append((uid, f"{uid} 構築工事 → {u['fortification']:.4f}/0.5"
                        f"（砲擊暴露 {of.exposure_factor(u, of.terr(s, u['pos']))}）"))
    # ── 消耗與休整 ──
    for uid, u in s["units"].items():
        if u["flags"].get("moved"):
            of.consume(s, uid, "L1")
        elif u["flags"].get("fired"):
            pass
        else:
            of.consume(s, uid, "L0")
            rest = 10 if u.get("fortification", 0) >= 0.5 or uid.endswith("rcn") else 3
            u["fatigue"] = max(0, u.get("fatigue", 0) - rest)
    of.refresh_visibility(s)
    newly = of.spot(s)
    for side, lst in newly.items():
        for uid in lst:
            ev.append((side, f"★我方偵獲敵 {uid} 於 {tuple(s['units'][uid]['pos'])}"))
    of.push_log(s, ev, gh_label=f"[gh{gh}] ")
    log.append(f"[gh{gh} {hs.game_time_str(gh)} {hs.daynight(gh)}] " + ("；".join(t for _, t in ev) if ev else "無事件"))
    of.clear_flags(s)
    hs.end_hour(s, log[-1])

of.resupply(s)
of.save(s)
print("\n".join(log))
sc = of.score(s)
print(f"\n=== 計分 === 藍 {sc['allies']['points']} {sc['allies']['inflicted']} | 紅 {sc['axis']['points']} {sc['axis']['inflicted']}")
print("=== 斬首 ===", command.decapitation(s))
