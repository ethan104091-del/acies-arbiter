#!/usr/bin/env python3
"""Run 6 Tick 5 解算（gh30-35，1944-08-26 12:00-17:00，全程白天）。

雙方新令皆為 [L1]，主指揮所 +1 級 → **gh32 生效**，本 tick 有效時數 4 小時。

  藍軍 BLU-AD (10,9)、BLU-1 (9,4) 實施偽裝作業（裁示 17，3 工時完成）；
       BLU-2 (11,9) 續挖工事至有頂蓋；BLU-3 (9,14) 完全休整；
       BLU-SF (6,4) 森林續挖工事。不抽離任何營級單位。全軍靜止、不主動開火。

  紅軍 轉入全面攻勢：RED-AD 沿 (20,10)→(16,9)→(12,9) 全速推進並攻擊；
       RED-2 沿 (21,9)→(17,9)→(13,9) 跟進攻擊；RED-3 沿 (21,3)→(17,4)→(13,4) 推進；
       兩個偵察營與 RED-SF 維持既定循環偵察；RED-2-1-r4 固守 (29,8)。

**裁示 18 於本 tick 起適用**：該小時行軍過的編隊不得實施砲擊。
紅軍三個攻擊編隊本 tick 全程在行軍，故無一得以實施砲擊；
藍軍應變 4（前進合圍＋砲兵集中射擊）同受此限，本 tick 未觸發。

**移動即棄工事與偽裝**（手冊 §11、裁示 17）：紅軍三個攻擊編隊一離開陣地，
其累積 8 工時的有頂蓋工事即歸零。此為其自身命令的代價，非裁判裁量。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 30, f"必須從 gh30 起始，現在 gh={s['global_hour']}"

NEW_ORDERS = [
    ("allies", "L1", "BLU-AD", "於 (10,9) 就地實施偽裝作業至完成並維持，工事已封頂"),
    ("allies", "L1", "BLU-1", "於 (9,4) 就地實施偽裝作業至完成並維持，工事已封頂"),
    ("allies", "L1", "BLU-2", "於 (11,9) 續行構築工事至有頂蓋級"),
    ("allies", "L1", "BLU-3", "於 (9,14) 固守完全休整，工事已封頂"),
    ("allies", "L1", "BLU-SF", "於 (6,4) 森林維持靜止隱蔽並續行構築工事"),
    ("axis", "L1", "RED-AD", "沿 (20,10)→(16,9)→(12,9) 全速推進，進入可攻擊距離即攻擊"),
    ("axis", "L1", "RED-2", "沿 (21,9)→(17,9)→(13,9) 跟進 RED-AD，對 BLU-2 正面攻擊"),
    ("axis", "L1", "RED-3", "沿 (21,3)→(17,4)→(13,4) 向西北翼推進，接觸後攻擊 BLU-1"),
    ("axis", "L1", "RED-2-rcn", "維持既定循環偵察，優先回報敵主力位置與工事狀態"),
    ("axis", "L1", "RED-3-rcn", "維持既定循環偵察"),
    ("axis", "L1", "RED-SF", "維持既定南翼搜索與滲透"),
    ("axis", "L1", "RED-2-1-r4", "固守主指揮所 (29,8)，不得移動"),
]
EFF = {}
for side, lvl, uid, txt in NEW_ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    EFF[uid] = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}",
                                extra_delay=extra)["effective_global_hour"]

# 紅軍攻擊軸線（只給軸線上的關鍵點，由 plan_path 尋路避開該兵種不可通行的地形）
AXIS = {"RED-AD": [(16, 9), (12, 9)],
        "RED-2":  [(17, 9), (13, 9)],
        "RED-3":  [(17, 4), (13, 4)]}
PATROL = {"RED-2-rcn": [(10, 8), (13, 8), (16, 8), (13, 8)],
          "RED-3-rcn": [(10, 3), (13, 3), (16, 3), (13, 3)],
          "RED-SF":    [(12, 14), (12, 16), (15, 16), (15, 14)]}
CAMO = ["BLU-AD", "BLU-1"]                       # 偽裝作業
DIG = ["BLU-2", "BLU-SF"]                        # 續挖工事（BLU-3 已封頂 → 純休整）
axis_i = {k: 0 for k in AXIS}
pat_i = {k: 0 for k in PATROL}
halted, retreated = set(), set()
RETREAT = {}      # uid -> 後撤目的地。後撤是持續動作，須走到才停（首次解算時只走一小時，已修）


def spotted(s, side):
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def is_big(u):
    return not u.get("is_detachment")


def follow(s, uid, ring, i, ev, note, cyclic):
    u = s["units"][uid]
    t = ring[i[uid] % len(ring)] if cyclic else (ring[i[uid]] if i[uid] < len(ring) else None)
    if t is None:
        return
    if list(u["pos"]) == list(t):
        i[uid] += 1
        if not cyclic and i[uid] >= len(ring):
            return
        t = ring[i[uid] % len(ring)]
    _, m = ar.advance(s, uid, list(t))
    ev.append((uid, f"{m}（{note}，目標 {tuple(t)}）"))


def resolve(s, gh):
    ev = []

    # ① 藍軍應變 1：敵師級/旅級進入 3 格 → 向西後撤 2 格（撤即棄工事與偽裝）
    for uid in ("BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-SF"):
        u = s["units"].get(uid)
        if not u or uid in retreated:
            continue
        threat = [e for e in spotted(s, "allies")
                  if is_big(s["units"][e]) and ar.dist(s["units"][e]["pos"], u["pos"]) <= 3]
        if threat:
            retreated.add(uid)
            halted.add(uid)
            RETREAT[uid] = [max(0, u["pos"][0] - 2), u["pos"][1]]
            ev.append((uid, f"{uid} 依應變 1 開始向西後撤 2 格至 {tuple(RETREAT[uid])}"
                            f"（敵 {', '.join(threat)} 已在 3 格內）｜工事與偽裝歸零"))

    # ①-b 後撤是持續動作：走到目的地為止
    for uid, dest in list(RETREAT.items()):
        u = s["units"].get(uid)
        if not u:
            continue
        if list(u["pos"]) == list(dest):
            RETREAT.pop(uid)
            ev.append((uid, f"{uid} 已抵達後撤位置 {tuple(dest)}，就地固守"))
            continue
        _, m = ar.advance(s, uid, list(dest))
        ev.append((uid, f"{uid} 後撤中：{m}"))

    # ② 紅軍攻擊軸線推進
    for uid, ring in AXIS.items():
        if uid in halted or gh < EFF[uid]:
            continue
        follow(s, uid, ring, axis_i, ev, "攻擊軸線", cyclic=False)

    # ③ 循環偵察／巡邏
    for uid, ring in PATROL.items():
        if uid in halted or gh < EFF[uid]:
            continue
        follow(s, uid, ring, pat_i, ev, "循環偵察", cyclic=True)

    # ④ 紅軍攻擊編隊的火力：裁示 18 — 該小時行軍過者不得砲擊
    for uid, tgts in (("RED-AD", ["BLU-AD", "BLU-2"]), ("RED-2", ["BLU-2"]),
                      ("RED-3", ["BLU-1"])):
        u = s["units"].get(uid)
        if not u or gh < EFF[uid] or uid in halted:
            continue
        seen = spotted(s, "axis")
        cand = [t for t in tgts if t in seen
                and any(ar.dist(u["pos"], s["units"][t]["pos"]) <= ar.GUN_SPEC[g][2]
                        for g in ar.GUN_MIX.get(u["type"], {}))]
        if not cand:
            continue
        cas, tk, gk, msg = ar.bombard(s, [uid], cand[0])
        if not (cas or tk or gk):
            ev.append((uid, f"{uid} 欲對 {cand[0]} 射擊但未實施：{msg}"))
            continue
        t = cand[0]
        pct = 100.0 * cas / max(s["units"][t].get("personnel", 1), 1)
        org = ar.org_impact(s, t, pct)
        ar.hurt(s, t, personnel=cas, tanks=tk, guns=gk, org=org,
                fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
        ev.append((uid, f"{uid} 對 {t} 實施砲擊：{msg}（組織度 -{org}）"))
        ev.append((t, f"{t} 遭敵砲擊：傷亡 {cas} 人"
                      + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else "")
                      + f"、組織度 -{org}"))

    # ⑤ 藍軍偽裝作業與構築工事（與工時池互斥：一小時擇一，命令已各自指定）
    for uid in CAMO:
        u = s["units"].get(uid)
        if not u or gh < EFF[uid] or uid in retreated or u["flags"].get("moved"):
            continue
        r = ar.camouflage(s, uid)
        if r and r[0] <= ar.CAMO_HOURS + 1e-9:
            ev.append((uid, f"{uid} 偽裝作業 → {r[0]:.2f}/{ar.CAMO_HOURS} 工時"
                            + ("　★完成，靜止時能見狀態好一級" if r[1] else "")))
    for uid in DIG:
        u = s["units"].get(uid)
        if not u or gh < EFF[uid] or uid in retreated:
            continue
        if u["flags"].get("moved") or u.get("dig_hours", 0.0) >= 8.0:
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))

    return ev


log = []
lines = ar.run_tick(s, resolve, hours=6, log=log)
ar.save(s)
print("=" * 78)
for line in lines:
    print(line)
print("=" * 78)
sc = ar.score(s)
print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}"
      f"｜斬首：{command.decapitation(s)}")
print(f"事實紀錄：{len(s.get('record', []))} 筆")
for side in ("allies", "axis"):
    print(f"{side:7} 已偵獲敵編隊：{spotted(s, side) or '（無）'}")
print()
print(f"{'編隊':13} {'位置':10} {'兵力':>6} {'疲勞':>4} {'org':>5} {'工事':>6} {'偽裝':>5} "
      f"{'暴露':>6} {'能見':>12}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('personnel', 0):6} "
          f"{u.get('fatigue', 0):4} {u.get('org', 0):5} {u.get('dig_hours', 0):6.1f} "
          f"{u.get('camo_hours', 0):5.1f} {ar.exposure_factor(u, ar.terr(s, u['pos'])):6} "
          f"{u.get('visibility_state', '?'):>12}")
