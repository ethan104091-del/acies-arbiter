#!/usr/bin/env python3
"""Run 7 — Tick 5 解算（gh30–gh35，1944-08-26 12:00–17:00，白天）。**全局第一次開火。**

## 兩軍的新命令都在 gh32 生效

| 方 | 命令 | 級別 | 階梯 | 生效 |
|---|---|---|---|---|
| 藍 | 五個砲兵營就地停止並對敵偵察隊「急襲」，逐小時不中斷 | L1 | +1 | gh32 |
| 紅 | RED-AD → (16,8) 後干擾 (11,9)；RED-SF → (14,12) | L2 | **+0** | gh32 |

紅軍的 +0 級來自 (20,9) 前進指揮所——驗算通過且軍長進駐，其 6 格內編隊享零級延遲。
藍軍用 L1（反應式）達到同樣的時刻。**兩軍首次交火的時刻由雙方各自的選擇對齊，非裁判安排。**

## 裁示 63 的首次適用：飽和上限合併解算

藍軍把 `BLU-1-a1`、`BLU-1-a2`（24 門）**與** `BLU-AD-sp1`（18 門）同時指向 RED-3-rcn。
若分開解算，一個 300 人的營一小時會挨 24+24 = 48 人（16%），與「一格的彈著密度有
物理上限」相矛盾。依裁示 63，**同一小時指向同一目標者合併為一次 `bombard` 呼叫**，
發數相加、上限只套用一次（300 × 8% = 24 人/小時）。

實測後果：對 300 人目標，24 門砲的急襲已觸頂（每人耗彈 10 發）；
多派的 18 門 SP105 不多殺一人，而且該小時不能打別的目標。

## 裁示 47 的首次適用：移入敵佔格是近戰突擊

紅軍兩支已完成偽裝的偵察營坐在 **(13,3)** 與 **(13,8)**——正是藍軍 BLU-1／BLU-2 與
BLU-3 的目標格。依裁示 47，藍軍**不得以移動進入**，抵達相鄰格後即轉為近戰突擊
（`battle`，非 `advance`），且只有在守軍被殲滅／投降／潰散／逼退後才佔領該格。

攻方該小時移動過 → 依裁示 53 吃「從行軍中接戰 ×0.7」（`battle` 自行由 `flags["moved"]` 判定）。
守方逼退格數依 `FR_TABLE`；逼退方向為其本方補給源（紅軍向東）。

## 構築工事／偽裝的適用對象（判例 §二十一）

| 編隊 | 作業 | 命令出處 |
|---|---|---|
| BLU-AD (13,5)、BLU-SF (15,1) | **偽裝**（未完成前）→ 完成後構工 | 藍 T4 第 3、5 條 |
| BLU-1／2／3（抵達後） | 同上 | 藍 T4 第 1、2、4 條 |
| 藍軍五個砲兵營 | **不構工**——藍 T5 第 1–3 條命其射擊，射擊與構工不可同小時並行 |
| BLU-2 之四營 (6,4)、BLU-2-rcn、BLU-3-rcn | 構工 | 藍 T0 第 7–8、T1 第 1 條 |
| RED-1／2／3、兩個守備營 | 構工（已達有頂蓋，續挖累積抗摧毀餘裕） | 紅 T3 第 1–6 條 |
| RED-AD（抵 (16,8) 後） | 構工至散兵壕 | 紅 T5 第 1 條 |
| RED-SF（抵 (14,12) 後） | **偽裝** | 紅 T5 第 2 條 |
| RED-2-rcn、RED-3-rcn | 偽裝已完成，維持觀察，不再作業 | 紅 T5 第 3 條 |
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
assert s["global_hour"] == 30, f"t5.py 只能從 gh30 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)
ZH = {"allies": "藍軍", "axis": "紅軍"}

NEW = [
    ("allies", "L1", "BLU-1-a1／a2 就地停止 (11,2)，對 RED-3-rcn 急襲，逐小時不中斷"),
    ("allies", "L1", "BLU-AD-sp1 就地停止 (13,5)，對 RED-3-rcn 急襲，逐小時不中斷"),
    ("allies", "L1", "BLU-3-a1／a2 就地停止 (11,9)，對 RED-2-rcn 急襲，逐小時不中斷"),
    ("axis", "L2", "RED-AD → (16,8)，抵達後對 (11,9) 干擾射擊一次，再構工至散兵壕"),
    ("axis", "L2", "RED-SF → (14,12) 隱蔽機動，抵達後偽裝作業至完成"),
]
for side, lv, txt in NEW:
    hs.enqueue_order(s, side, lv, txt,
                     extra_delay=command.delay_tier_adjust(s, side, [0, 0]))

NEW_GH = 32

DEST = {
    "BLU-1": (13, 3), "BLU-2": (13, 3), "BLU-3": (13, 8),
    "BLU-AD": (13, 5), "BLU-SF": (15, 1),
    "BLU-2-rcn": (13, 6), "BLU-3-rcn": (9, 13),
    "BLU-2-3-r6": (6, 4), "BLU-2-1-r6": (6, 4), "BLU-2-2-r6": (6, 4),
    "BLU-2-3-r5": (6, 4),
    "RED-1": (20, 12), "RED-2": (20, 9), "RED-3": (20, 3),
    "RED-2-1-r4": (29, 8), "RED-2-2-r4": (22, 9),
    "RED-2-rcn": (13, 8), "RED-3-rcn": (13, 3),
    "RED-AD": (20, 10), "RED-SF": (18, 15),          # gh32 起改為 (16,8) / (14,12)
}
# 紅軍 T5 第 3 條：「兩支偵察隊…保持偽裝觀察，**不再向前暴露推進**。」
# 故自 gh32 起兩支偵察隊的目的地＝其當時所在格（含被逼退後的新位置），不得再西進。
# ★ 初版誤沿用其 T3 舊目標 (13,3)/(13,8)，導致它們被逼退後又走回藍軍佔據的格，
#   既違反紅軍自己的命令，也違反裁示 47（移入敵佔格是突擊不是移動），
#   還連帶產生一次不該發生的友軍誤擊。已還原快照重跑。
RED_NEW_DEST = {"RED-AD": (16, 8), "RED-SF": (14, 12)}
RED_HOLD = ("RED-2-rcn", "RED-3-rcn")
# 藍軍砲兵營 gh32 起就地停止（目的地＝現位）
BLU_GUNS = ("BLU-1-a1", "BLU-1-a2", "BLU-AD-sp1", "BLU-3-a1", "BLU-3-a2")
for g in BLU_GUNS:
    DEST[g] = tuple(s["units"][g]["pos"])

DIG = {"BLU-2-3-r6", "BLU-2-1-r6", "BLU-2-2-r6", "BLU-2-3-r5",
       "BLU-2-rcn", "BLU-3-rcn",
       "RED-1", "RED-2", "RED-3", "RED-2-1-r4", "RED-2-2-r4"}
CAMO_FIRST = ("BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-SF")     # 抵達後先偽裝再構工
RED_ARRIVE_DIG = {"RED-AD"}          # 紅 T5 第 1 條：抵 (16,8) 後構工
RED_ARRIVE_CAMO = {"RED-SF"}         # 紅 T5 第 2 條：抵 (14,12) 後偽裝

# 藍軍火力任務：{目標: [射手]}。裁示 63 → 同目標合併一次呼叫。
FIRE_PLAN = {"RED-3-rcn": ["BLU-1-a1", "BLU-1-a2", "BLU-AD-sp1"],
             "RED-2-rcn": ["BLU-3-a1", "BLU-3-a2"]}
FALLBACK = "RED-2-rcn"               # 藍軍命令：主目標消滅或脫離射程後改打此目標
ASSAULT = {"BLU-1": (13, 3), "BLU-2": (13, 3), "BLU-3": (13, 8)}


def do_fire(s, gh, ev):
    """藍軍砲兵：同一小時指向同一目標者合併解算（裁示 63）。"""
    for tgt, shooters in FIRE_PLAN.items():
        t = s["units"].get(tgt)
        live = [u for u in shooters if tk.can_fire(s, u)]
        if t is None or ar.status_of(t) not in ar.COMBAT_STATUSES:
            continue
        live = [u for u in live if tk.in_range(s, u, t["pos"])]
        if not live:
            continue
        cas, tkl, gkl, msg = ar.bombard(s, live, tgt, mission="急襲")
        if not (cas or tkl or gkl):
            ev.append((live[0], f"砲群 → {tgt}：{msg}"))
            continue
        org = ar.org_impact(s, tgt, 100.0 * cas / max(t.get("personnel", 1), 1))
        ar.hurt(s, tgt, personnel=cas, tanks=tkl, guns=gkl, org=org,
                fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
        ev.append((live[0], f"急襲 {'＋'.join(live)} → {tgt}：{msg}（組織度 -{org}）"))
        ev.append((tgt, f"{tgt} 遭敵急襲：傷亡 {cas} 人"
                        + (f"、火砲 -{gkl}" if gkl else "") + f"、組織度 -{org}"))


def do_assault(s, gh, ev):
    """裁示 47：移入敵佔格＝近戰突擊。攻方須為明文受命者（裁示 56）。"""
    for hexpos in {tuple(v) for v in ASSAULT.values()}:
        defs = [uid for uid, u in s["units"].items()
                if u.get("side") == "axis" and list(u["pos"]) == list(hexpos)
                and ar.status_of(u) in ar.COMBAT_STATUSES]
        if not defs:
            continue
        atks = [uid for uid, dst in ASSAULT.items()
                if tuple(dst) == hexpos and uid in s["units"]
                and ar.dist(s["units"][uid]["pos"], hexpos) == 1
                and ar.under_command(s, uid)]
        if not atks:
            continue
        detail, push = ar.battle(s, atks, defs, list(hexpos))
        ev.append((atks[0], f"★近戰突擊 {tuple(hexpos)}：{detail}"))
        for d in defs:
            ev.append((d, f"★遭 {'／'.join(atks)} 近戰突擊於 {tuple(hexpos)}：{detail}"))
        # 逼退：守方向本方補給源（紅軍＝東緣）後退 push 格
        if push > 0:
            # 裁示：逼退是**強制位移**，不受移動速率限制（見 _tickkit.forced_push）
            for d in defs:
                if ar.status_of(s["units"].get(d, {})) in ar.COMBAT_STATUSES:
                    tk.forced_push(s, d, push, ev)
        # 守軍已不在該格 → 攻方進駐
        still = [d for d in defs if list(s["units"][d]["pos"]) == list(hexpos)
                 and ar.status_of(s["units"][d]) in ar.COMBAT_STATUSES]
        if not still:
            for a in atks:
                s["units"][a]["pos"] = list(hexpos)
                ar.abandon_works(s["units"][a])
                ev.append((a, f"{a} 奪下 {tuple(hexpos)} 並進駐"))


def approach(s, uid, dst):
    """回傳本小時實際該走的目標格。

    目標格若由敵方戰鬥編隊佔據（裁示 47：不得以移動進入），則改以**距本編隊最近的
    可通行相鄰格**為行軍目標；若本編隊已在某個相鄰格，回傳 None 表示就地待機
    （進入該格只能經由近戰突擊）。目標格無敵軍時原樣回傳。
    """
    u = s["units"][uid]
    enemy = ar.ENEMY[u["side"]]
    held = any(x.get("side") == enemy and list(x["pos"]) == list(dst)
               and ar.status_of(x) in ar.COMBAT_STATUSES
               for x in s["units"].values())
    if not held:
        return dst
    if ar.dist(u["pos"], dst) <= 1:
        return None
    W, H = s["map"]["width"], s["map"]["height"]
    cands = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == dy == 0:
                continue
            nx, ny = int(dst[0]) + dx, int(dst[1]) + dy
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            if not ar._passable(u, ar.terr(s, (nx, ny))):
                continue
            cands.append((ar.dist(u["pos"], (nx, ny)), (nx, ny)))
    return min(cands)[1] if cands else None


def resolve(s, gh):
    ev = []
    after = gh >= NEW_GH
    if gh == NEW_GH:
        ev.append(("allies", "五個砲兵營新令生效：就地停止，對敵偵察隊實施急襲、逐小時不中斷"))
        ev.append(("axis", "RED-AD／RED-SF 新令生效：分別向 (16,8)／(14,12) 機動"
                           "（(20,10) 之有頂蓋工事留在該格，人離開即失去防護）"))
    dest = dict(DEST)
    if after:
        dest.update(RED_NEW_DEST)
        for uid in RED_HOLD:                    # 紅 T5 第 3 條：不再向前推進
            if uid in s["units"]:
                dest[uid] = tuple(s["units"][uid]["pos"])

    if after:
        do_fire(s, gh, ev)
        do_assault(s, gh, ev)

    for uid, dst in dest.items():
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid):
            continue
        if uid in ASSAULT and after:
            d = ar.dist(u["pos"], dst)
            if d <= 1 and any(x.get("side") == "axis" and list(x["pos"]) == list(dst)
                              and ar.status_of(x) in ar.COMBAT_STATUSES
                              for x in s["units"].values()):
                continue          # 已於 do_assault 處理，不得再呼叫 advance（裁示 47）
        if list(u["pos"]) != list(dst):
            # 裁示 47 的通用護欄：**任何一方**都不得以移動進入敵方戰鬥編隊所在格。
            #
            # ★ 護欄的層級：只擋「最後一步進入」，不擋整段接近。
            #   初版寫成「目標格有敵軍就完全不動」，結果藍軍三個師從 2 格外
            #   就停住、整個 tick 未移動。正確做法是先走到**相鄰格**待機，
            #   由 do_assault 處理進入；若未受突擊命令，就停在相鄰格。
            #   （另一個初版錯誤是只把這條套在藍軍身上，使紅軍偵察隊用移動
            #    走進了藍軍佔據的格，還連帶產生一次不該發生的友軍誤擊。）
            go = approach(s, uid, dst)
            if go is None:
                ev.append((uid, f"{uid} 目標格 {tuple(dst)} 由敵方戰鬥編隊佔據且已抵相鄰格，"
                                f"依裁示 47 不得以移動進入；未受突擊命令，故就地待機"))
                continue
            _, m = ar.advance(s, uid, list(go))
            ev.append((uid, m))
            continue
        m = None
        if uid in CAMO_FIRST and not u.get("camouflaged"):
            m = tk.try_camouflage(s, uid)
        elif uid in RED_ARRIVE_CAMO and after and not u.get("camouflaged"):
            m = tk.try_camouflage(s, uid)
        elif uid in DIG or uid in CAMO_FIRST or (uid in RED_ARRIVE_DIG and after):
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
print(f"   藍軍造成 {sc['allies']['inflicted']}")
print(f"   紅軍造成 {sc['axis']['inflicted']}\n")
for side in ("allies", "axis"):
    print(f"── {ZH[side]} ──")
    for uid, u in sorted(ar.own(s, side).items()):
        w = ar.hex_works(s, u["pos"])
        per = w / max(u.get("personnel", 1), 1)
        camo = "偽✓" if u.get("camouflaged") else (
            f"偽{u.get('camo_hours',0):.1f}" if u.get("camo_hours") else "")
        am = "／".join(f"{g}:{v:.0f}" for g, v in (u.get("ammo") or {}).items())
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 兵{u.get('personnel',0):>6}"
              f" 力{u.get('strength'):>5.1f} 組{u.get('org'):>5.1f} 疲{u.get('fatigue',0):>3}"
              f" {ar.fort_tier(u.get('fortification',0.0))[3]:4} {u['visibility_state']:11}"
              f" {camo:5} {am}")
    print(f"  指揮：{ar.cp_line(s, side)}")
print()
print("偵獲：藍→", s["fog_of_war"].get("allies_spotted"))
print("　　　紅→", s["fog_of_war"].get("axis_spotted"))

snap = HERE / "snap_T6start.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 快照 {snap}")
