#!/usr/bin/env python3
"""Run 7 — Tick 7 解算（gh42–gh47，1944-08-27 00:00–05:00，全程夜間）。倒數第二回。

## 兩軍都把火力接通，各自搶同一格

- **紅軍**：RED-AD 自 (15,8) 逐小時壓制 **(12,8)**（藍軍兩個砲兵營，各 471 人、11 門砲），
  RED-SF 自 (12,10) 向該格發動地面突擊奪砲。
- **藍軍**：把 (12,8) 那兩個砲兵營東移一格進 **(13,8)** 與 BLU-3 同駐（該格工事記憶
  逾 88,000 man-hours，471 人的營據此直接判為有頂蓋），並把全軍火力接通：
  BLU-2 的 155 逐小時**干擾** RED-AD——目的不是殺傷，是讓其 `interdicted` 每小時成立、
  **到終局都挖不動一鏟土**，使其守方倍率停在 1.0 而非 1.5。

生效時刻（雙方階梯差異決定先後）：

| 方 | 命令 | 級別 | 階梯 | 生效 |
|---|---|---|---|---|
| 紅 | RED-AD 持續壓制 (12,8) | L1 | **+0** | **gh43** |
| 藍 | 全軍火力接通、兩砲營東移 | L1 | +1 | **gh44** |
| 藍 | BLU-AD → (13,8)、BLU-1-a1／a2 → (13,3) | L2 | +1 | gh45 |
| 紅 | RED-SF 突擊 (12,8) | L2 | +1（距前進指揮所 8 格，超出 6） | gh45 |

**紅軍的裝甲師又搶到一小時**（零級延遲），但它的特戰旅離前進指揮所 8 格，
落在罩子外、吃 +1 級——**紅軍自己的節奏優勢只覆蓋前進指揮所六格內的部隊。**

## 藍軍的干擾戰術與裁示 58／60 的關係

BLU-2 的 12 門 155 每小時只造成極少傷亡，但 `interdicted` 旗標是二元的（裁示 58／61），
所以那 12 門砲足以讓一個 13,988 人的裝甲師該小時**不得構築工事**。
裁判已於裁示 61 把這條路徑完整公告雙方，並記入判例 §二十三（模型失真、兩局之間修正）。
本局照規則執行。

## 構築工事／偽裝的適用對象（判例 §二十一）

| 編隊 | 作業 | 命令出處 |
|---|---|---|
| BLU-3 (13,8) | 先構工一小時，其後射擊 | 藍 T7 第 3 條 |
| BLU-AD（抵 (13,8) 後） | 構工至有頂蓋並休整，其後射擊 | 藍 T7 第 6 條 |
| BLU-SF (15,1)、(6,4) 四營、兩支 rcn | 構工 | 藍 T7 第 8 條 |
| RED-1／2／3、兩守備營 | 構工 | 紅 T7 第 3 條 |
| RED-2-rcn／RED-3-rcn（抵本方師級格後） | 休整＋偽裝 | 紅 T6 第 3–4 條（續行） |
| RED-AD、RED-SF | **不構工**——兩者本回皆受命射擊或突擊 |
| 藍軍各砲兵營 | **不構工**——本回皆受命射擊 |
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1]))
import arbiter as ar          # noqa: E402
import command                # noqa: E402
import hourstate as hs        # noqa: E402
import _tickkit as tk         # noqa: E402
import _audit                 # noqa: E402

s = ar.load()
assert s["global_hour"] == 42, f"t7.py 只能從 gh42 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)
ZH = {"allies": "藍軍", "axis": "紅軍"}

NEW = [
    ("axis", "L1", "RED-AD 逐小時壓制 (12,8)，彈藥降至 15% 為止，保持現位"),
    ("axis", "L2", "RED-SF 突擊 (12,8) 奪砲，奪下後偽裝固守"),
    ("allies", "L1", "BLU-2 以 155 逐小時干擾 RED-AD；BLU-1 急襲 RED-3-rcn；"
                     "BLU-3 構工一小時後急襲 RED-SF；BLU-3-a1／a2 移入 (13,8) 後急襲 RED-SF；"
                     "BLU-AD-sp1 急襲 RED-SF"),
    ("allies", "L2", "BLU-AD → (13,8) 與 BLU-3 同駐；BLU-1-a1／a2 → (13,3)"),
]
for side, lv, txt in NEW:
    hs.enqueue_order(s, side, lv, txt,
                     extra_delay=command.delay_tier_adjust(s, side, [0, 0]))

RED_L1, BLU_L1, BLU_L2, RED_L2 = 43, 44, 45, 45
RED_SUPP_HEX = (12, 8)

DEST = {
    "BLU-1": (13, 3), "BLU-2": (13, 3), "BLU-3": (13, 8), "BLU-SF": (15, 1),
    "BLU-AD-sp1": (13, 5), "BLU-2-rcn": (13, 6), "BLU-3-rcn": (9, 13),
    "BLU-2-3-r6": (6, 4), "BLU-2-1-r6": (6, 4), "BLU-2-2-r6": (6, 4),
    "BLU-2-3-r5": (6, 4),
    "BLU-3-a1": (12, 8), "BLU-3-a2": (12, 8),            # gh44 起 → (13,8)
    "BLU-AD": (14, 6), "BLU-1-a1": (11, 2), "BLU-1-a2": (11, 2),   # gh45 起改
    "RED-1": (20, 12), "RED-2": (20, 9), "RED-3": (20, 3),
    "RED-2-1-r4": (29, 8), "RED-2-2-r4": (22, 9),
    "RED-AD": (15, 8), "RED-SF": (12, 10),               # gh45 起 RED-SF 突擊 (12,8)
    "RED-2-rcn": (20, 9), "RED-3-rcn": (20, 3),
}
BLU_L1_DEST = {"BLU-3-a1": (13, 8), "BLU-3-a2": (13, 8)}
BLU_L2_DEST = {"BLU-AD": (13, 8), "BLU-1-a1": (13, 3), "BLU-1-a2": (13, 3)}
RED_L2_ASSAULT = {"RED-SF": (12, 8)}

DIG = {"BLU-SF", "BLU-2-3-r6", "BLU-2-1-r6", "BLU-2-2-r6", "BLU-2-3-r5",
       "BLU-2-rcn", "BLU-3-rcn", "RED-1", "RED-2", "RED-3",
       "RED-2-1-r4", "RED-2-2-r4"}
ARRIVE_CAMO = {"RED-2-rcn", "RED-3-rcn"}
BLU3_DIG_HOURS = 1                    # 藍 T7 第 3 條：先構工一小時
state = {"blu3_dug": 0, "ad_dug": 0}


def apply_fire(s, shooters, tgt, mission, ev, guns_only=None):
    live = [u for u in shooters if tk.can_fire(s, u)]
    t = s["units"].get(tgt)
    if not live or not t or ar.status_of(t) not in ar.COMBAT_STATUSES:
        return
    live = [u for u in live if tk.in_range(s, u, t["pos"])]
    if not live:
        return
    cas, tkl, gkl, msg = ar.bombard(s, live, tgt, mission=mission)
    if not (cas or tkl or gkl):
        ev.append((live[0], f"{'＋'.join(live)} → {tgt}［{mission}］：{msg}"))
        return
    org = ar.org_impact(s, tgt, 100.0 * cas / max(t.get("personnel", 1), 1))
    ar.hurt(s, tgt, personnel=cas, tanks=tkl, guns=gkl, org=org,
            fatigue=ar.fatigue_from_combat("light"), note=f"遭敵{mission}")
    ev.append((live[0], f"{'＋'.join(live)} → {tgt}［{mission}］：{msg}（組織度 -{org}）"))
    ev.append((tgt, f"{tgt} 遭敵{mission}：傷亡 {cas} 人"
                    + (f"、戰車 -{tkl}" if tkl else "")
                    + (f"、火砲 -{gkl}" if gkl else "") + f"、組織度 -{org}"))


def red_fire(s, gh, ev):
    """紅 T7 第 1 條：RED-AD 逐小時壓制 (12,8)，彈藥 <15% 停。裁示 48：該格全部承受。"""
    if gh < RED_L1 or not tk.can_fire(s, "RED-AD"):
        return
    u = s["units"]["RED-AD"]
    am, mx = u.get("ammo") or {}, u.get("ammo_max") or {}
    if any(v / max(mx.get(g, 1), 1) < 0.15 for g, v in am.items()):
        ev.append(("axis", "RED-AD 彈藥降至基數 15% 以下，依其命令停止壓制射擊"))
        return
    occ = [uid for uid, x in s["units"].items()
           if x.get("side") == "allies" and list(x["pos"]) == list(RED_SUPP_HEX)
           and ar.status_of(x) in ar.COMBAT_STATUSES]
    if not occ:
        # 紅軍應變第二條：目標撤出後繼續壓制其最後已知格（該格無敵編隊 → 效果為零）
        ev.append(("axis", f"RED-AD 對 {tuple(RED_SUPP_HEX)} 壓制：該格已無敵編隊，"
                           f"依其應變繼續射擊最後已知格，彈藥與暴露照付、效果為零"))
        ar.bombard_hex(s, ["RED-AD"], list(RED_SUPP_HEX), mission="壓制")
        return
    for tgt in occ:
        apply_fire(s, ["RED-AD"], tgt, "壓制", ev)


def blue_fire(s, gh, ev):
    """藍 T7 第 1–6 條。小目標只派一個編隊（其應變自訂紀律＋裁示 63）。"""
    if gh < BLU_L1:
        return
    plan = []
    # BLU-2：155 干擾 RED-AD，逐小時不中斷
    if tk.can_fire(s, "BLU-2"):
        plan.append(("BLU-2", "RED-AD", "干擾"))
    # BLU-1：急襲 RED-3-rcn；脫離射程後改打射程內任何敵編隊
    if tk.can_fire(s, "BLU-1"):
        t = s["units"].get("RED-3-rcn")
        if t and ar.status_of(t) in ar.COMBAT_STATUSES and tk.in_range(s, "BLU-1", t["pos"]):
            plan.append(("BLU-1", "RED-3-rcn", "急襲"))
        else:
            alt = tk.nearest_target(s, ["BLU-1"], "allies")
            if alt:
                plan.append(("BLU-1", alt, "急襲"))
    # BLU-3：先構工一小時，其後急襲 RED-SF
    if state["blu3_dug"] >= BLU3_DIG_HOURS and tk.can_fire(s, "BLU-3"):
        plan.append(("BLU-3", "RED-SF", "急襲"))
    # 兩個砲兵營：抵達 (13,8) 後急襲 RED-SF
    for g in ("BLU-3-a1", "BLU-3-a2"):
        if list(s["units"][g]["pos"]) == [13, 8] and tk.can_fire(s, g):
            plan.append((g, "RED-SF", "急襲"))
    # BLU-AD-sp1：急襲 RED-SF
    if tk.can_fire(s, "BLU-AD-sp1"):
        plan.append(("BLU-AD-sp1", "RED-SF", "急襲"))
    # BLU-AD：抵 (13,8) 且已構工至有頂蓋並休整後才射擊（本 tick 不會成立）
    by = {}
    for sh, tgt, mis in plan:
        by.setdefault((tgt, mis), []).append(sh)
    for (tgt, mis), shooters in by.items():
        apply_fire(s, shooters, tgt, mis, ev)


def red_assault(s, gh, ev):
    """紅 T7 第 2 條：RED-SF 突擊 (12,8)。裁示 47：須先抵相鄰格，且為突擊非移動。"""
    if gh < RED_L2:
        return
    hexpos = (12, 8)
    u = s["units"].get("RED-SF")
    if not u or not ar.under_command(s, "RED-SF") or u["flags"].get("fired"):
        return
    defs = [uid for uid, x in s["units"].items()
            if x.get("side") == "allies" and list(x["pos"]) == list(hexpos)
            and ar.status_of(x) in ar.COMBAT_STATUSES]
    if not defs:
        return
    if ar.dist(u["pos"], hexpos) != 1:
        return
    detail, push = ar.battle(s, ["RED-SF"], defs, list(hexpos))
    ev.append(("RED-SF", f"★近戰突擊 {tuple(hexpos)}：{detail}"))
    for d in defs:
        ev.append((d, f"★遭 RED-SF 近戰突擊於 {tuple(hexpos)}：{detail}"))
    if push > 0:
        for d in defs:
            if ar.status_of(s["units"][d]) in ar.COMBAT_STATUSES:
                tk.forced_push(s, d, push, ev)
    still = [d for d in defs if list(s["units"][d]["pos"]) == list(hexpos)
             and ar.status_of(s["units"][d]) in ar.COMBAT_STATUSES]
    if not still:
        s["units"]["RED-SF"]["pos"] = list(hexpos)
        ar.abandon_works(s["units"]["RED-SF"])
        ev.append(("RED-SF", f"RED-SF 奪下 {tuple(hexpos)} 並進駐"))


def approach(s, uid, dst):
    u = s["units"][uid]
    enemy = ar.ENEMY[u["side"]]
    held = any(x.get("side") == enemy and list(x["pos"]) == list(dst)
               and ar.status_of(x) in ar.COMBAT_STATUSES for x in s["units"].values())
    if not held:
        return dst
    if ar.dist(u["pos"], dst) <= 1:
        return None
    W, H = s["map"]["width"], s["map"]["height"]
    c = [(ar.dist(u["pos"], (x, y)), (x, y))
         for dx in (-1, 0, 1) for dy in (-1, 0, 1) if not dx == dy == 0
         for x, y in [(int(dst[0]) + dx, int(dst[1]) + dy)]
         if 0 <= x < W and 0 <= y < H and ar._passable(u, ar.terr(s, (x, y)))]
    return min(c)[1] if c else None


def resolve(s, gh):
    ev = []
    dest = dict(DEST)
    if gh >= BLU_L1:
        dest.update(BLU_L1_DEST)
    if gh >= BLU_L2:
        dest.update(BLU_L2_DEST)
    if gh >= RED_L2:
        dest.update(RED_L2_ASSAULT)          # 由 red_assault 處理進入
    if gh == RED_L1:
        ev.append(("axis", "RED-AD 新令生效：逐小時壓制 (12,8)，保持現位"))
    if gh == BLU_L1:
        ev.append(("allies", "藍軍新令生效：全軍火力接通；兩個砲兵營東移入 (13,8)"))
    if gh == BLU_L2:
        ev.append(("allies", "BLU-AD → (13,8)、BLU-1-a1／a2 → (13,3) 生效"))
    if gh == RED_L2:
        ev.append(("axis", "RED-SF 新令生效：突擊 (12,8) 奪砲"))

    red_fire(s, gh, ev)
    blue_fire(s, gh, ev)
    red_assault(s, gh, ev)

    for uid, dst in dest.items():
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid):
            continue
        if u["flags"].get("fired"):           # 裁示 18
            continue
        if uid == "BLU-3" and state["blu3_dug"] < BLU3_DIG_HOURS:
            m = tk.try_dig(s, uid)
            state["blu3_dug"] += 1
            if m:
                ev.append((uid, m))
            continue
        if list(u["pos"]) != list(dst):
            go = approach(s, uid, dst)
            if go is None:
                ev.append((uid, f"{uid} 已抵 {tuple(dst)} 相鄰格，該格由敵佔據；"
                                f"依裁示 47 不得以移動進入"))
                continue
            _, m = ar.advance(s, uid, list(go))
            ev.append((uid, m))
            continue
        m = None
        if uid in ARRIVE_CAMO and not u.get("camouflaged"):
            m = tk.try_camouflage(s, uid)
        elif uid == "BLU-AD":
            m = tk.try_dig(s, uid)            # 抵 (13,8) 後構工至有頂蓋
        elif uid in DIG:
            m = tk.try_dig(s, uid)
        if m:
            ev.append((uid, m))
    return ev


lines = ar.run_tick(s, resolve, hours=6)
ar.save(s)
for l in lines:
    print(l)
print()
_audit.require_clean(s, before)
sc = ar.score(s)
print(f"★ 計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}")
print(f"   藍軍造成 {sc['allies']['inflicted']}｜紅軍造成 {sc['axis']['inflicted']}\n")
for side in ("allies", "axis"):
    print(f"── {ZH[side]} ──")
    for uid, u in sorted(ar.own(s, side).items()):
        w = ar.hex_works(s, u["pos"])
        per = w / max(u.get("personnel", 1), 1)
        am = "／".join(f"{g}:{v:.0f}" for g, v in (u.get("ammo") or {}).items())
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 兵{u.get('personnel',0):>6}"
              f" 力{u.get('strength'):>5.1f} 組{u.get('org'):>5.1f}"
              f" {ar.fort_tier(u.get('fortification',0.0))[3]:4}({per:5.2f})"
              f" {u['visibility_state']:11} {am}")
print("\n偵獲：藍→", s["fog_of_war"].get("allies_spotted"))
print("　　　紅→", s["fog_of_war"].get("axis_spotted"))
snap = HERE / "snap_T8start.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 快照 {snap}")
