#!/usr/bin/env python3
"""Tick 8 解算（gh48-53, 1944-08-27 06:00-12:00，白天）★終局★

紅軍：RED-1 攻 BLU-3、RED-AD 攻 BLU-1（正面強攻），RED-2/RED-3 砲擊壓制。
藍軍：全線固守工事、全砲群集中射擊 RED-AD。
延遲：紅軍基準（L1→gh49）／藍軍 +1（L1→gh50）；藍軍 T7 已下的「拂曉轉打 RED-AD」條件令自 gh48 生效。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, hourstate as hs, command

s = of.load()
of.apply_fatigue_caps(s)
for lvl, txt in [("L1", "RED-1 自 (18,12) 向 BLU-3 (15,12) 正面強攻，抵達後全師投入不後撤"),
                 ("L1", "RED-AD 自 (18,8) 向 BLU-1 (15,10) 戰鬥行進並攻擊，抵達後全師投入"),
                 ("L1", "RED-2 固守 (19,8) 對 BLU-2 集中砲擊"),
                 ("L1", "RED-3 固守 (18,3) 持續砲擊 BLU-SF")]:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=0)
for lvl, txt in [("L1", "全線固守不動、維持工事、持續砲擊至局終"),
                 ("L1", "全部砲群集中射擊 RED-AD（取消分火）"),
                 ("L1", "取消 BLU-AD 的 POL 15% 停火下限，打到見底"),
                 ("L1", "BLU-SF 固守森林、迫砲射程不足不射擊"),
                 ("L1", "觀測所與警衛營固守原位")]:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=1)

BLUE_GUNS = ["BLU-1", "BLU-2", "BLU-3", "BLU-AD"]
ATTACK = {"RED-1": ("BLU-3", (16, 12)), "RED-AD": ("BLU-1", (16, 9))}
log = []


def obs(s, side, t):
    return t in s["fog_of_war"].get(f"{side}_spotted", [])


def fire(s, shooters, tuid, ev, side, label):
    sh = [x for x in shooters if x in s["units"] and s["units"][x]["equip"]["guns"] > 0
          and of.dist(s["units"][x]["pos"], s["units"][tuid]["pos"]) <= 5]
    if not sh:
        return False
    cas, tk, gk, msg = of.bombard(s, sh, tuid)
    if not (cas or tk or gk):
        return False
    of.hurt(s, tuid, personnel=cas, tanks=tk, guns=gk,
            org=round(cas / max(s["units"][tuid]["personnel"], 1) * 150, 1), fatigue=3, note="遭敵砲擊")
    for x in sh:
        s["units"][x]["flags"]["fired"] = True
        of.consume(s, x, "L3")
    ev.append((side, f"我方{label}射擊敵 {tuid}：{msg}"))
    ev.append((tuid, f"{tuid} 遭敵砲擊：傷亡 {cas} 人"
                     + (f"、-{tk} 戰車" if tk else "") + (f"、-{gk} 火砲" if gk else "")))
    return True


for gh in range(48, 54):
    command.activate_due_cps(s)
    hs.hour_brief(s)
    ev = []

    # ── 紅軍砲兵（RED-2 → BLU-2、RED-3 → BLU-SF）──
    for shooter, target in (("RED-2", "BLU-2"), ("RED-3", "BLU-SF")):
        if obs(s, "axis", target):
            fire(s, [shooter], target, ev, "axis", f"{shooter} 砲兵")

    # ── 藍軍砲兵：全砲群集中 RED-AD（拂曉條件令 gh48 起生效）──
    if obs(s, "allies", "RED-AD"):
        fire(s, BLUE_GUNS, "RED-AD", ev, "allies", "全砲群集中")
    elif obs(s, "allies", "RED-1"):
        fire(s, BLUE_GUNS, "RED-1", ev, "allies", "全砲群集中（RED-AD 未偵獲，遞補）")

    # ── 紅軍強攻：gh49 起移動，抵達攻擊位置後每 hour 交戰 ──
    battles = []
    if gh >= 49:
        for atk, (tgt, appr) in ATTACK.items():
            a = s["units"][atk]
            d = s["units"][tgt]
            if of.dist(a["pos"], d["pos"]) > 1:
                moved, msg = of.advance(s, atk, appr)
                if moved:
                    ev.append((atk, msg))
            if of.dist(a["pos"], d["pos"]) <= 1:
                battles.append((atk, tgt))
    # 支援分配：每個編隊每 hour 只能投入一場（同裁示 20）；依藍軍命令「指定給交戰 CP 最大的一場」
    if battles:
        battles.sort(key=lambda b: -of.base_power(s["units"][b[0]]))
        assigned = set()
        for atk, tgt in battles:
            defenders = [tgt]
            for uid, u in of.own(s, "allies").items():
                if uid in assigned or uid == tgt or u.get("is_detachment") and u["type"] == "recon":
                    continue
                if uid in ("BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-AD-eng") and \
                        of.dist(u["pos"], s["units"][tgt]["pos"]) <= 1:
                    defenders.append(uid)
            assigned |= set(defenders)
            detail, push = of.battle(s, [atk], defenders, s["units"][tgt]["pos"],
                                     atk_from_march=True, def_passive=False)
            ev.append(("axis", f"我方 {atk} 攻擊 {tgt} 於 {tuple(s['units'][tgt]['pos'])}：{detail}"))
            ev.append(("allies", f"我方 {tgt}（＋{', '.join(defenders[1:]) or '無支援'}）遭 {atk} 攻擊：{detail}"))
            if push < 0:      # 兵力比 <0.5 → 攻方被迫後退
                a = s["units"][atk]
                a["pos"] = [min(29, a["pos"][0] + 1), a["pos"][1]]
                a["last_action"] = "攻擊失敗、被迫後退"
                ev.append((atk, f"{atk} 攻擊失敗、被迫後退至 {tuple(a['pos'])}"))

    for uid, u in s["units"].items():
        if u["flags"].get("moved"):
            of.consume(s, uid, "L1")
        elif u["flags"].get("fired"):
            u["fatigue"] = max(0, u.get("fatigue", 0) - 3)
        else:
            of.consume(s, uid, "L0")
            u["fatigue"] = max(0, u.get("fatigue", 0) - 10)
    of.apply_fatigue_caps(s)
    of.refresh_visibility(s)
    newly = of.spot(s)
    for side, lst in newly.items():
        for uid in lst:
            ev.append((side, f"★我方偵獲敵 {uid} 於 {tuple(s['units'][uid]['pos'])}"))
    of.push_log(s, ev, gh_label=f"[gh{gh}] ")
    log.append(f"[gh{gh} {hs.game_time_str(gh)}] " + ("；".join(t for _, t in ev) if ev else "無事件"))
    of.clear_flags(s)
    hs.end_hour(s, log[-1])

dec = command.decapitation(s)
of.save(s)
for l in log:
    print(l[:600]); print()
sc = of.score(s)
print(f"=== 終局計分 === 藍 {sc['allies']['points']} {sc['allies']['inflicted']} | 紅 {sc['axis']['points']} {sc['axis']['inflicted']}")
print("=== 斬首 ===", dec)
