#!/usr/bin/env python3
"""Tick 5 解算（gh30-35, 1944-08-26 12:00-18:00，白天）★第一場地面戰★

延遲：紅軍前進指揮所罩內 → 基準（L1→gh31）；藍軍僅主指揮所 → +1（L1→gh32、L2→gh33）。
應變（預先授權的條件反應）不吃延遲。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, hourstate as hs, command

s = of.load()
ROUTES = {k: [tuple(p) for p in v] for k, v in s.get("standing_routes", {}).items()}
for u in s["units"].values():
    u.setdefault("fortification", 0.0)

for lvl, txt in [("L1", "RED-3 自 (19,3) 攻擊已偵獲的 BLU-SF (18,3)，敵退後僅追擊一格、不進森林"),
                 ("L1", "RED-AD 向 (18,8) 戰鬥行進，抵達後固守，不追擊敵偵察營"),
                 ("L1", "RED-2 向 (19,8) 戰鬥行進，與 RED-AD 維持相鄰協同"),
                 ("L1", "RED-1 向 (18,12) 戰備推進，保持在 RED-1-rcn 以東"),
                 ("L1", "RED-1-rcn 向 (18,13) 前進偵察，監視 BLU-3-rcn 及其西方主力")]:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=0)
for lvl, txt in [("L2", "陣線南移：BLU-1→(15,10)、BLU-2→(15,11)、BLU-3→(15,12)、BLU-AD+eng→(14,11)，抵達挖滿工事後完全休整"),
                 ("L1", "射擊令放寬：任何敵單位進入砲兵射程即開火；師級目標集中、營級小目標只用一個師的砲兵"),
                 ("L2", "BLU-3-rcn→(17,13) 設觀測所，為全軍砲兵持續指示 RED-1"),
                 ("L2", "BLU-AD-rcn→(13,10) 退出敵砲射程、完全休整"),
                 ("L2", "BLU-1-rcn→(14,5) 設觀測所"),
                 ("L2", "BLU-SF→(20,4) 森林，構工事取 CONCEALED，威脅 RED-3 的 y=3 走廊；不得主動攻擊師級"),
                 ("L1", "取消前進指揮所令，軍長留 (4,10)"),
                 ("L1", "觀測所紀律：遭砲擊不後撤，僅在兵力<60% 或組織<40 時後撤 3 格")]:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=1)

RED_31 = {"RED-AD": [(18, 8)], "RED-2": [(19, 8)], "RED-1": [(18, 12)], "RED-1-rcn": [(18, 13)]}
BLUE_33 = {"BLU-1": [(15, 10)], "BLU-2": [(15, 11)], "BLU-3": [(15, 12)],
           "BLU-AD": [(14, 11)], "BLU-AD-eng": [(14, 11)],
           "BLU-3-rcn": [(17, 13)], "BLU-AD-rcn": [(13, 10)], "BLU-1-rcn": [(14, 5)],
           "BLU-SF": [(20, 4)]}
HOLD = {"RED-3", "RED-SF", "RED-2-rcn", "RED-3-rcn", "RED-2-1-r4",
        "BLU-2-1-r4", "BLU-2-2-r4", "BLU-2-3-r4", "BLU-2-rcn"}
AD_H = [0]
BLUE_FIRE = False
log = []

for gh in range(30, 36):
    command.activate_due_cps(s)
    hs.hour_brief(s)
    ev = []
    if gh == 31:
        ROUTES.update(RED_31); HOLD -= set(RED_31)
    if gh == 32:
        BLUE_FIRE = True
    if gh == 33:
        ROUTES.update(BLUE_33); HOLD -= set(BLUE_33)

    # ── 紅軍命令 1：RED-3 攻擊 BLU-SF（gh31 起，只要相鄰且敵仍在）──
    if gh >= 31 and "BLU-SF" in s["fog_of_war"].get("axis_spotted", []):
        r3, sf = s["units"]["RED-3"], s["units"]["BLU-SF"]
        if of.dist(r3["pos"], sf["pos"]) <= 1 and not s.get("_r3_done"):
            defenders = [uid for uid, u in of.own(s, "allies").items()
                         if list(u["pos"]) == list(sf["pos"])]
            detail, push = of.battle(s, ["RED-3"], defenders, sf["pos"], def_passive=True)
            ev.append(("axis", f"我方 RED-3 攻擊 {tuple(sf['pos'])}：{detail}"))
            ev.append(("BLU-SF", f"遭 RED-3 全師攻擊於 {tuple(sf['pos'])}：{detail}"))
            if push > 0:      # 守方被迫後退（朝本方補給源方向）
                for uid in defenders:
                    u = s["units"][uid]
                    nx = max(0, u["pos"][0] - push)
                    u["pos"] = [nx, u["pos"][1]]
                    u["last_action"] = f"戰敗被迫後退 {push} 格"
                    ev.append((uid, f"{uid} 被迫後退至 {tuple(u['pos'])}"))
                # 紅軍命令：敵退後僅追擊一格
                tgt = (r3["pos"][0] - 1, r3["pos"][1])
                if of.terr(s, tgt) != "F":
                    r3["pos"] = list(tgt)
                    r3["flags"]["moved"] = True
                    ev.append(("RED-3", f"RED-3 依命令追擊一格至 {tuple(tgt)}，停止"))
                s["_r3_done"] = True

    # ── 藍軍射擊令（gh32 起）：任何敵單位進入砲兵射程即開火，依優先序 ──
    if BLUE_FIRE:
        spotted = s["fog_of_war"].get("allies_spotted", [])
        def prio(uid):
            u = s["units"][uid]
            f = u.get("fortification", 0)
            if u["type"] == "infantry" and not u.get("is_detachment") and f <= 0: return 0
            if u["type"] == "armor" and f <= 0: return 1
            if not u.get("is_detachment") and u["type"] in ("infantry", "armor", "ranger"): return 2
            return 3
        shooters_all = [uid for uid in of.own(s, "allies")
                        if s["units"][uid]["equip"]["guns"] > 0 and not s["units"][uid].get("is_detachment")]
        cands = []
        for tuid in spotted:
            tu = s["units"][tuid]
            in_range = [su for su in shooters_all if of.dist(s["units"][su]["pos"], tu["pos"]) <= 5]
            if in_range:
                cands.append((prio(tuid), -sum(1 for _ in in_range), tuid, in_range))
        if cands:
            cands.sort()
            _, _, tuid, shooters = cands[0]
            small = s["units"][tuid].get("is_detachment")
            if small:
                shooters = shooters[:1]        # 藍軍自訂：營級小目標只用一個師的砲兵
            cas, tk, gk, msg = of.bombard(s, shooters, tuid)
            if cas or tk or gk:
                of.hurt(s, tuid, personnel=cas, tanks=tk, guns=gk,
                        org=round(cas / max(s["units"][tuid]["personnel"], 1) * 150, 1), fatigue=5,
                        note="遭敵砲兵集中射擊")
                for su in shooters:
                    s["units"][su]["flags"]["fired"] = True
                    of.consume(s, su, "L3")
                ev.append(("allies", f"我方砲兵集中射擊敵 {tuid}：{msg}"))
                ev.append((tuid, f"{tuid} 遭敵砲兵射擊：傷亡 {cas} 人（{msg.split('｜')[0]}）"))

    # ── 紅軍應變：若偵獲敵裝甲或師級主力在 RED-AD 砲兵射程內 → RED-AD 停止前推並砲擊 ──
    rad = s["units"]["RED-AD"]
    rspot = s["fog_of_war"].get("axis_spotted", [])
    rcands = [(of.dist(rad["pos"], s["units"][t2]["pos"]), 0 if s["units"][t2]["type"] == "armor" else 1, t2)
              for t2 in rspot
              if not s["units"][t2].get("is_detachment") and s["units"][t2]["type"] in ("infantry", "armor")
              and of.dist(rad["pos"], s["units"][t2]["pos"]) <= 5]
    if rcands:
        rcands.sort()
        rt = rcands[0][2]
        HOLD.add("RED-AD")          # 應變明文：停止前推
        cas, tk, gk, msg = of.bombard(s, ["RED-AD"], rt)
        if cas or tk or gk:
            of.hurt(s, rt, personnel=cas, tanks=tk, guns=gk,
                    org=round(cas / max(s["units"][rt]["personnel"], 1) * 150, 1), fatigue=5,
                    note="遭敵自走砲集中砲擊")
            rad["flags"]["fired"] = True
            of.consume(s, "RED-AD", "L3")
            ev.append(("axis", f"★應變觸發：RED-AD 停止前推並對敵 {rt} 砲擊：{msg}"))
            ev.append((rt, f"{rt} 遭敵自走砲砲擊：傷亡 {cas} 人（{msg.split('｜')[0]}）"))

    # ── 移動 ──
    for uid in list(ROUTES):
        wps = ROUTES[uid]
        if uid not in s["units"] or not wps or uid in HOLD:
            continue
        u = s["units"][uid]
        if uid in ("BLU-AD", "BLU-AD-eng"):
            front = max(s["units"][d]["pos"][0] for d in ("BLU-1", "BLU-2", "BLU-3"))
            if u["pos"][0] >= front or AD_H[0] >= 4:
                continue
            if uid == "BLU-AD":
                AD_H[0] += 1
        tgt = wps[0]
        moved, msg = of.advance(s, uid, tgt)
        if list(u["pos"]) == list(tgt):
            if len(wps) > 1:
                wps.pop(0)
            else:
                HOLD.add(uid); ev.append((uid, f"{uid} 抵達 {tuple(tgt)}"))
        if moved:
            ev.append((uid, msg))
    # ── 工事構築：★只有「明確下令構築工事」的單位才挖（裁示：工事是明確工程動作，固守/休整不等於挖工事）
    #    藍軍：三個步兵師抵達後明文「連續構築工事至滿」＋ (4,10) 三個警衛營。紅軍本 tick 未下任何構築令。
    DIGGING = {"BLU-1", "BLU-2", "BLU-3", "BLU-2-1-r4", "BLU-2-2-r4", "BLU-2-3-r4"}
    for uid in DIGGING:
        u = s["units"].get(uid)
        if not u or u["flags"].get("moved") or u.get("fortification", 0) >= 0.5:
            continue
        if uid in HOLD or list(u["pos"]) == list(ROUTES.get(uid, [[-1, -1]])[0]):
            rate = 0.1875 if not u.get("is_detachment") else 0.1875   # 師內有 eng → ×1.5
            u["fortification"] = round(min(0.5, u.get("fortification", 0) + rate), 4)
            ev.append((uid, f"{uid} 構築工事 → {u['fortification']:.4f}/0.5"))
    for uid, u in s["units"].items():
        of.consume(s, uid, "L1" if u["flags"].get("moved") else "L0")
        if not u["flags"].get("moved"):
            u["fatigue"] = max(0, u.get("fatigue", 0) - 3)
    of.refresh_visibility(s)
    newly = of.spot(s)
    for side, lst in newly.items():
        for uid in lst:
            ev.append((side, f"★我方偵獲敵 {uid} 於 {tuple(s['units'][uid]['pos'])}"))
    of.push_log(s, ev, gh_label=f"[gh{gh}] ")
    log.append(f"[gh{gh} {hs.game_time_str(gh)}] " + ("；".join(t for _, t in ev) if ev else "無事件"))
    of.clear_flags(s)
    hs.end_hour(s, log[-1])

s.pop("_r3_done", None)
of.resupply(s)
s["standing_routes"] = {k: [list(p) for p in v] for k, v in ROUTES.items() if k not in HOLD and v}
of.save(s)
print("\n".join(log))
print("\n=== 計分 ===", of.score(s))
print("=== 斬首 ===", command.decapitation(s))
print("\n" + of.ascii_map(s, "god"))
