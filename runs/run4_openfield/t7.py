#!/usr/bin/env python3
"""Tick 7 解算（gh42-47, 1944-08-27 00:00-06:00，全程夜間；gh47=05:00 黎明）。

雙方皆固守砲擊。延遲：紅軍基準（L1→gh43）／藍軍 +1（L1→gh44）；但兩邊命令都是「延續現狀」，
故 gh42 起即照各自最新的射擊指派執行（無新機動、無需等延遲的動作）。
夜間視距：師級 2／特戰 3／偵察營 3。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of, hourstate as hs, command

s = of.load()
of.apply_fatigue_caps(s)

for lvl, txt in [("L1", "RED-1 固守 (18,12) 對 BLU-3 持續砲擊"),
                 ("L1", "RED-2 固守 (19,8) 對 BLU-2 持續砲擊（失去觀測則改打其他未構工事敵師，否則固守）"),
                 ("L1", "RED-AD 固守 (18,8) 對 BLU-1 持續自走砲火"),
                 ("L1", "RED-3 固守 (18,3) 持續砲擊 BLU-SF")]:
    hs.enqueue_order(s, "axis", lvl, txt, extra_delay=0)
for lvl, txt in [("L1", "全線固守不動、維持工事 0.5、持續砲擊至終局"),
                 ("L1", "T7 全砲群集中射擊 RED-1；T8 拂曉若重新偵獲未構工事的 RED-AD 則 105 群+自走砲改打之"),
                 ("L1", "BLU-AD 自走砲 POL<15% 即停火"),
                 ("L1", "BLU-SF 固守 (20,4) 森林，取消舊撤退應變"),
                 ("L1", "三個觀測所固守、不構築工事"),
                 ("L1", "三個警衛營 (4,10) 固守，任何理由不得離開")]:
    hs.enqueue_order(s, "allies", lvl, txt, extra_delay=1)

BLUE_GUNS = ["BLU-1", "BLU-2", "BLU-3", "BLU-AD"]
log = []


def observed(s, side, t):
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


for gh in range(42, 48):
    command.activate_due_cps(s)
    hs.hour_brief(s)
    ev = []
    # ── 紅軍：三編隊分火 ──
    for shooter, target in (("RED-1", "BLU-3"), ("RED-2", "BLU-2"), ("RED-AD", "BLU-1")):
        if observed(s, "axis", target):
            fire(s, [shooter], target, ev, "axis", f"{shooter} 砲兵")
        else:
            # 紅軍應變：失去觀測 → 若有其他「未構築工事」的可觀測敵師在射程內則改打，否則固守
            alt = [t for t in ("BLU-1", "BLU-2", "BLU-3", "BLU-AD")
                   if observed(s, "axis", t) and s["units"][t].get("fortification", 0) <= 0
                   and of.dist(s["units"][shooter]["pos"], s["units"][t]["pos"]) <= 5]
            if alt:
                fire(s, [shooter], alt[0], ev, "axis", f"{shooter} 砲兵（改打）")
            else:
                ev.append(("axis", f"{shooter} 對 {target} 失去夜間觀測、且無未構工事的可觀測敵師 → 依應變固守停火"))
    if observed(s, "axis", "BLU-SF"):
        fire(s, ["RED-3"], "BLU-SF", ev, "axis", "RED-3 砲兵")

    # ── 藍軍：全砲群集中 RED-1（T7 夜間）──
    if observed(s, "allies", "RED-1"):
        shooters = [x for x in BLUE_GUNS
                    if not (x == "BLU-AD" and s["units"][x]["resources"]["POL"] < 15)]
        if len(shooters) < len(BLUE_GUNS):
            ev.append(("allies", "BLU-AD 自走砲依 POL<15% 停火令停止射擊"))
        fire(s, shooters, "RED-1", ev, "allies", "全砲群集中")
    else:
        ev.append(("allies", "本 hour 對 RED-1 失去觀測 → 停止射擊"))

    # ── 消耗、休整、疲勞上限 ──
    for uid, u in s["units"].items():
        if u["flags"].get("fired"):
            u["fatigue"] = max(0, u.get("fatigue", 0) - 3)      # 接戰待命 -3
        elif not u["flags"].get("moved"):
            of.consume(s, uid, "L0")
            u["fatigue"] = max(0, u.get("fatigue", 0) - 10)     # 完全休整 -10
    of.apply_fatigue_caps(s)
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
print("\n".join(log[:2]))
print("...")
print(log[-1])
sc = of.score(s)
print(f"\n=== 計分 === 藍 {sc['allies']['points']} {sc['allies']['inflicted']} | 紅 {sc['axis']['points']} {sc['axis']['inflicted']}")
print("=== 斬首 ===", command.decapitation(s))
for side in ("allies", "axis"):
    for uid, u in sorted(of.own(s, side).items()):
        L = u["losses"]
        if L["personnel"]:
            print(f"  {uid:12} 兵{u.get('personnel',0):>6} 車{u['equip']['tanks']:>3} 砲{u['equip']['guns']:>2} "
                  f"組{u.get('org'):>5} 疲{u.get('fatigue'):>3} POL{int(u['resources']['POL']):>3} 工事{u.get('fortification',0):.3f} "
                  f"累損 人{L['personnel']:>4}/車{L['tanks']:>2}/砲{L['guns']:>2}")
