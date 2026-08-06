#!/usr/bin/env python3
"""Run 7 — Tick 6 解算（gh36–gh41，1944-08-26 18:00–23:00，黃昏轉夜間）。

## 兩軍的計畫正面對撞，但都撞在自己的延遲上

- **紅軍**：RED-AD 先自 (16,8) 對 **(11,9)** 的兩個藍軍砲兵營壓制射擊一次，隨即西進
  (12,9) 突擊該格；RED-SF 至 (12,10) 協攻；兩支受創偵察隊撤回本方師級所在格。
- **藍軍**：把 **(11,9)** 的兩個砲兵營東撤至 (13,8)，並把 BLU-AD 自 (13,5) 疊進 (13,8)
  ——它算出兩個師＋兩個砲營同格後，紅軍裝甲師突擊的兵力比會由 1.76 翻成 0.54。

**紅軍的目標正在搬走，藍軍的援軍來不及到。** 生效時刻：

| 方 | 命令 | 級別 | 階梯 | 生效 |
|---|---|---|---|---|
| 紅 | RED-AD 射擊後西進、RED-SF 協攻、兩偵察隊東撤 | L2 | **+0**（前進指揮所 6 格內） | **gh38** |
| 藍 | BLU-1-a1 續射、a2 改構工、sp1 續射 | L1 | +1 | **gh38** |
| 藍 | BLU-AD 與 BLU-3-a1／a2 移入 (13,8) | L2 | +1 | **gh39** |

紅軍的零級延遲（前進指揮所驗算通過、軍長進駐）讓它的射擊比藍軍的撤離**早一小時**。
那一小時就是 (11,9) 那兩個營要付的代價。

## 裁示 18 的適用：紅軍那條命令一小時只能做一件事

紅軍第 1 條寫「先對 (11,9) 實施一次壓制射擊；**隨即**向 (12,9) 行軍」。
依裁示 18（該小時行軍過的編隊不得實施間接火力），**射擊與行軍不得在同一小時內完成**。
裁判解為：gh38 射擊（靜止），gh39 起西進。「隨即」讀為「其次」，非「同一小時」。
`_audit` 的射擊合法性檢查會驗證這一點。

## 裁示 63 的適用：紅軍對 (11,9) 的壓制

該格有 BLU-3-a1 與 BLU-3-a2 兩個編隊。依裁示 48 兩者皆在彈著區內、依裁示 63
合併為一次解算、發數按人數分攤、飽和上限各按其自身兵力（500 × 8% = 40 人）套用。

## 藍軍自訂的火力紀律（其 T6 應變第二條）

「同一小時不得有兩個以上我方編隊指向同一個人數 <2,000 的敵編隊」——這是它讀了
裁示 63 之後自己加的限制。裁判照其命令執行：對小目標只派一個編隊。

## 構築工事／偽裝的適用對象（判例 §二十一）

| 編隊 | 作業 | 命令出處 |
|---|---|---|
| BLU-1、BLU-2 (13,3)、BLU-3 (13,8)、BLU-SF (15,1) | 構工 | 藍 T6 第 6 條 |
| BLU-1-a2 (11,2) | **構工**（並明令不射擊） | 藍 T6 第 4 條 |
| (6,4) 四營、BLU-2-rcn、BLU-3-rcn | 構工 | 藍 T6 第 6 條 |
| BLU-AD、BLU-3-a1／a2（抵 (13,8) 後） | 構工 | 藍 T6 第 1–2 條 |
| RED-1／2／3、兩守備營 | 構工 | 紅 T6 第 5 條 |
| RED-AD（抵 (12,9) 後） | 構工 | 紅 T6 第 1 條 |
| RED-SF（抵 (12,10) 後） | **偽裝** | 紅 T6 第 2 條 |
| RED-2-rcn／RED-3-rcn（抵本方師級格後） | 休整＋**偽裝** | 紅 T6 第 3–4 條 |
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
assert s["global_hour"] == 36, f"t6.py 只能從 gh36 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)
ZH = {"allies": "藍軍", "axis": "紅軍"}

NEW = [
    ("axis", "L2", "RED-AD 對 (11,9) 壓制一次後西進 (12,9) 突擊；RED-SF → (12,10) 協攻"),
    ("axis", "L2", "RED-2-rcn 撤至 (20,9)、RED-3-rcn 撤至 (20,3)，抵達後休整並偽裝"),
    ("allies", "L1", "BLU-1-a1 續對 RED-3-rcn 急襲；BLU-1-a2 改構工不射擊；"
                     "BLU-AD-sp1 續對 RED-2-rcn 急襲，其脫離後改對 RED-AD 干擾"),
    ("allies", "L2", "BLU-AD 自 (13,5) → (13,8) 與 BLU-3 同駐；BLU-3-a1／a2 亦移入 (13,8)"),
]
for side, lv, txt in NEW:
    hs.enqueue_order(s, side, lv, txt,
                     extra_delay=command.delay_tier_adjust(s, side, [0, 0]))

RED_GH, BLU_L1_GH, BLU_L2_GH = 38, 38, 39

DEST = {
    "BLU-1": (13, 3), "BLU-2": (13, 3), "BLU-3": (13, 8), "BLU-SF": (15, 1),
    "BLU-1-a1": (11, 2), "BLU-1-a2": (11, 2), "BLU-AD-sp1": (13, 5),
    "BLU-2-rcn": (13, 6), "BLU-3-rcn": (9, 13),
    "BLU-2-3-r6": (6, 4), "BLU-2-1-r6": (6, 4), "BLU-2-2-r6": (6, 4),
    "BLU-2-3-r5": (6, 4),
    "BLU-AD": (13, 5), "BLU-3-a1": (11, 9), "BLU-3-a2": (11, 9),   # gh39 起改 (13,8)
    "RED-1": (20, 12), "RED-2": (20, 9), "RED-3": (20, 3),
    "RED-2-1-r4": (29, 8), "RED-2-2-r4": (22, 9),
    "RED-AD": (16, 8), "RED-SF": (14, 12),                          # gh38 起改
    "RED-2-rcn": (15, 8), "RED-3-rcn": (15, 3),                     # gh38 起東撤
}
BLU_L2_DEST = {"BLU-AD": (13, 8), "BLU-3-a1": (13, 8), "BLU-3-a2": (13, 8)}
RED_L2_DEST = {"RED-AD": (12, 9), "RED-SF": (12, 10),
               "RED-2-rcn": (20, 9), "RED-3-rcn": (20, 3)}

DIG = {"BLU-1", "BLU-2", "BLU-3", "BLU-SF", "BLU-1-a2",
       "BLU-2-3-r6", "BLU-2-1-r6", "BLU-2-2-r6", "BLU-2-3-r5",
       "BLU-2-rcn", "BLU-3-rcn",
       "RED-1", "RED-2", "RED-3", "RED-2-1-r4", "RED-2-2-r4"}
ARRIVE_DIG = {"BLU-AD", "BLU-3-a1", "BLU-3-a2", "RED-AD"}
ARRIVE_CAMO = {"RED-SF", "RED-2-rcn", "RED-3-rcn"}
NO_FIRE = {"BLU-1-a2"}                      # 藍 T6 第 4 條：明令不射擊
RED_ASSAULT_TARGET = (11, 9)
done = {"red_supp": False}


def blue_fire(s, gh, ev):
    """藍 T6 第 3、5 條 + 其應變的目標優先序。小目標只派一個編隊（其自訂紀律）。"""
    plan = []
    for shooter, primary, fallback_mission in (
            ("BLU-1-a1", "RED-3-rcn", None),
            ("BLU-AD-sp1", "RED-2-rcn", ("RED-AD", "干擾")),
    ):
        if not tk.can_fire(s, shooter) or shooter in NO_FIRE:
            continue
        t = s["units"].get(primary)
        if t and ar.status_of(t) in ar.COMBAT_STATUSES and tk.in_range(s, shooter, t["pos"]):
            plan.append((shooter, primary, "急襲"))
            continue
        if fallback_mission:
            fb, mis = fallback_mission
            ft = s["units"].get(fb)
            if ft and ar.status_of(ft) in ar.COMBAT_STATUSES and tk.in_range(s, shooter, ft["pos"]):
                plan.append((shooter, fb, mis))
                continue
        # 命令：改對射程內人數最少之敵編隊急襲
        cands = [(u.get("personnel", 0), uid) for uid, u in s["units"].items()
                 if u.get("side") == "axis" and uid in tk.spotted(s, "allies")
                 and ar.status_of(u) in ar.COMBAT_STATUSES
                 and tk.in_range(s, shooter, u["pos"])]
        if cands:
            plan.append((shooter, min(cands)[1], "急襲"))
    # 裁示 63：同目標合併
    by_tgt = {}
    for sh, tgt, mis in plan:
        by_tgt.setdefault((tgt, mis), []).append(sh)
    for (tgt, mis), shooters in by_tgt.items():
        apply_fire(s, shooters, tgt, mis, ev)


def apply_fire(s, shooters, tgt, mission, ev):
    live = [u for u in shooters if tk.can_fire(s, u)]
    t = s["units"].get(tgt)
    if not live or not t or ar.status_of(t) not in ar.COMBAT_STATUSES:
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
    """紅 T6 第 1 條：RED-AD 對 (11,9) 壓制**一次**，且該小時不得行軍（裁示 18）。"""
    if done["red_supp"] or gh < RED_GH or not tk.can_fire(s, "RED-AD"):
        return
    occ = [uid for uid, u in s["units"].items()
           if u.get("side") == "allies" and list(u["pos"]) == list(RED_ASSAULT_TARGET)
           and ar.status_of(u) in ar.COMBAT_STATUSES]
    if not occ:
        ev.append(("axis", f"RED-AD：{tuple(RED_ASSAULT_TARGET)} 已無敵編隊，"
                           f"壓制射擊取消（依其應變第二條，改逕行西進佔領 (12,9)）"))
        done["red_supp"] = True
        return
    if not tk.in_range(s, "RED-AD", RED_ASSAULT_TARGET):
        return
    # 裁示 48／63：該格全部承受、合併一次解算、上限各按自身兵力
    for tgt in occ:
        apply_fire(s, ["RED-AD"], tgt, "壓制", ev)
    done["red_supp"] = True


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
    if gh >= RED_GH:
        dest.update(RED_L2_DEST)
    if gh >= BLU_L2_GH:
        dest.update(BLU_L2_DEST)
    if gh == RED_GH:
        ev.append(("axis", "新令生效：RED-AD 壓制 (11,9) 後西進；RED-SF → (12,10)；兩偵察隊東撤"))
    if gh == BLU_L2_GH:
        ev.append(("allies", "新令生效：BLU-AD 與 BLU-3-a1／a2 移入 (13,8) 與 BLU-3 同駐"))

    red_fire(s, gh, ev)
    if gh >= BLU_L1_GH:
        blue_fire(s, gh, ev)

    for uid, dst in dest.items():
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid):
            continue
        if u["flags"].get("fired"):        # 裁示 18：本小時已射擊者不再行軍
            continue
        if list(u["pos"]) != list(dst):
            go = approach(s, uid, dst)
            if go is None:
                ev.append((uid, f"{uid} 目標格 {tuple(dst)} 由敵方戰鬥編隊佔據且已抵相鄰格，"
                                f"依裁示 47 不得以移動進入；未受突擊命令，故就地待機"))
                continue
            _, m = ar.advance(s, uid, list(go))
            ev.append((uid, m))
            continue
        m = None
        if uid in ARRIVE_CAMO and not u.get("camouflaged"):
            m = tk.try_camouflage(s, uid)
        elif uid in DIG or uid in ARRIVE_DIG:
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
        camo = "偽✓" if u.get("camouflaged") else ""
        am = "／".join(f"{g}:{v:.0f}" for g, v in (u.get("ammo") or {}).items())
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 兵{u.get('personnel',0):>6}"
              f" 力{u.get('strength'):>5.1f} 組{u.get('org'):>5.1f}"
              f" {ar.fort_tier(u.get('fortification',0.0))[3]:4}({per:5.2f})"
              f" {u['visibility_state']:11} {camo:3} {am}")
    print(f"  指揮：{ar.cp_line(s, side)}")
print("\n偵獲：藍→", s["fog_of_war"].get("allies_spotted"))
print("　　　紅→", s["fog_of_war"].get("axis_spotted"))
snap = HERE / "snap_T7start.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 快照 {snap}")
