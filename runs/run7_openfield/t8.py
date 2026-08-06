#!/usr/bin/env python3
"""Run 7 — Tick 8 解算（gh48–gh53，1944-08-27 06:00–11:00，白天）。**終局。**

## 兩軍的最後選擇正好相反

- **紅軍領先 128 分,選擇脫離接觸守住勝分**：RED-AD 與 RED-SF 一律東撤回 RED-2 的
  有頂蓋防線,不交戰。它的理由寫在意圖裡：「此時不以高價兵力交換未必可得的戰果。」
- **藍軍落後,把決戰動作全部寫進應變欄**——因為命令欄要 3 小時才生效（L2 → gh51）,
  而**應變觸發即生效、不延遲**（`rules_v2.md`）。而 RED-SF 就在 (13,8) 隔壁。

生效時刻:

| 方 | 內容 | 級別 | 階梯 | 生效 |
|---|---|---|---|---|
| **雙方應變** | 藍軍突擊 RED-SF／紅軍 RED-SF 遭擊即東撤 | — | — | **gh48（即刻）** |
| 藍 | 全軍火力改「壓制」、BLU-AD-sp1 改射目標 | L1 | +1 | gh50 |
| 紅 | RED-AD 撤至 (20,9) | L2 | **+0**（距前進指揮所 5 格） | gh50 |
| 紅 | RED-SF 撤至 (17,10) | L2 | +1（距前進指揮所 8 格，罩外） | gh51 |

**紅軍的撤退令比藍軍的突擊晚了兩小時**——因為突擊走的是應變（零延遲），
撤退走的是命令欄（吃延遲）。這是本局第三次由「應變 vs 命令欄」的時序差決定勝負片段。

## 藍軍應變的兩段結構

1. **第一段**：RED-SF 若在 (13,8) ≤1 格 → (13,8) 格內四個編隊**當小時立即突擊,不先移動**
   （依裁示 53，在鄰格發起之突擊不設 `moved`，不吃「從行軍中接戰 ×0.7」）。逐小時重判。
2. **第二段**：RED-SF 脫離 ≤1 格後 → 若 RED-AD 那一格**沒有其他敵師級編隊**,
   BLU-AD 與 BLU-3 經 (14,8) 推進追擊；**若有其他敵師級編隊會合則一律不推進**,
   留在 (13,8) 固守並以壓制支援。此禁止條件逐小時重做。

紅軍的對應應變是「不反向突擊,沿撤退路線繼續東撤」——所以這是一場**追擊**,不是對攻。

## 火力

紅軍 T8 **沒有任何射擊命令**（其三個師與守備營一律「維持既有工事、休整與守備」,
應變亦僅「固守」）。故本 tick 紅軍不實施任何火力任務——它選擇不用彈藥換分。
藍軍則「打到彈盡」。

## 構築工事（判例 §二十一）

僅 (6,4) 四個警衛營、BLU-2-rcn、BLU-3-rcn、以及紅軍三個師與兩個守備營續構工。
其餘編隊本回皆受命射擊或突擊。
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
assert s["global_hour"] == 48, f"t8.py 只能從 gh48 跑，現在是 gh{s['global_hour']}"
before = _audit.snapshot(s)
ZH = {"allies": "藍軍", "axis": "紅軍"}

NEW = [
    ("allies", "L1", "全軍火力任務一律改「壓制」，打到彈盡；BLU-AD-sp1 目標依敵情調整"),
    ("axis", "L2", "RED-AD 停止西進，撤至 (20,9) RED-2 工事內固守不交戰"),
    ("axis", "L2", "RED-SF 脫離接觸，撤至 (17,10)，抵達後偽裝固守"),
]
for side, lv, txt in NEW:
    hs.enqueue_order(s, side, lv, txt,
                     extra_delay=command.delay_tier_adjust(s, side, [0, 0]))

BLU_L1, RED_AD_GH, RED_SF_GH = 50, 50, 51
HOLD_HEX = (13, 8)
BLU_ASSAULT_GROUP = ("BLU-AD", "BLU-3", "BLU-3-a1", "BLU-3-a2")
CHASE = ("BLU-AD", "BLU-3")          # 第二段只有這兩個推進
DIG = {"BLU-2-3-r6", "BLU-2-1-r6", "BLU-2-2-r6", "BLU-2-3-r5",
       "BLU-2-rcn", "BLU-3-rcn", "RED-1", "RED-2", "RED-3",
       "RED-2-1-r4", "RED-2-2-r4"}
STATIC = {"BLU-1": (13, 3), "BLU-2": (13, 3), "BLU-AD-sp1": (13, 5),
          "BLU-SF": (15, 1), "BLU-1-a1": (13, 3), "BLU-1-a2": (13, 3)}
RED_DEST = {"RED-1": (20, 12), "RED-2": (20, 9), "RED-3": (20, 3),
            "RED-2-1-r4": (29, 8), "RED-2-2-r4": (22, 9),
            "RED-2-rcn": (20, 9), "RED-3-rcn": (20, 3)}
st = {"phase": 1}


def mission(gh):
    return "壓制" if gh >= BLU_L1 else "急襲"


def apply_fire(s, shooters, tgt, mis, ev):
    live = [u for u in shooters if tk.can_fire(s, u)]
    t = s["units"].get(tgt)
    if not live or not t or ar.status_of(t) not in ar.COMBAT_STATUSES:
        return
    # 不對含我方編隊之格射擊（藍 T8 第 2 條明文「以免誤擊自己」）
    if any(x.get("side") == "allies" and list(x["pos"]) == list(t["pos"])
           for x in s["units"].values()):
        return
    live = [u for u in live if tk.in_range(s, u, t["pos"])]
    if not live:
        return
    cas, tkl, gkl, msg = ar.bombard(s, live, tgt, mission=mis)
    if not (cas or tkl or gkl):
        ev.append((live[0], f"{'＋'.join(live)} → {tgt}［{mis}］：{msg}"))
        return
    org = ar.org_impact(s, tgt, 100.0 * cas / max(t.get("personnel", 1), 1))
    ar.hurt(s, tgt, personnel=cas, tanks=tkl, guns=gkl, org=org,
            fatigue=ar.fatigue_from_combat("light"), note=f"遭敵{mis}")
    ev.append((live[0], f"{'＋'.join(live)} → {tgt}［{mis}］：{msg}（組織度 -{org}）"))
    ev.append((tgt, f"{tgt} 遭敵{mis}：傷亡 {cas} 人"
                    + (f"、戰車 -{tkl}" if tkl else "")
                    + (f"、火砲 -{gkl}" if gkl else "") + f"、組織度 -{org}"))


def blue_assault(s, gh, ev):
    """藍軍應變第一段／第二段。回傳本小時已參與近戰的編隊集合。"""
    engaged = set()
    sf = s["units"].get("RED-SF")
    ad = s["units"].get("RED-AD")

    # 第一段：RED-SF 在 (13,8) ≤1 格 → 立即突擊，不先移動
    if sf and ar.status_of(sf) in ar.COMBAT_STATUSES and ar.dist(sf["pos"], HOLD_HEX) <= 1:
        atks = [u for u in BLU_ASSAULT_GROUP
                if u in s["units"] and list(s["units"][u]["pos"]) == list(HOLD_HEX)
                and ar.under_command(s, u)]
        if atks:
            defs = [uid for uid, x in s["units"].items()
                    if x.get("side") == "axis" and list(x["pos"]) == list(sf["pos"])
                    and ar.status_of(x) in ar.COMBAT_STATUSES]
            detail, push = ar.battle(s, atks, defs, list(sf["pos"]))
            ev.append((atks[0], f"★近戰突擊 {tuple(sf['pos'])}（應變第一段，鄰格發起、"
                                f"不吃行軍中接戰）：{detail}"))
            for d in defs:
                ev.append((d, f"★遭 {'／'.join(atks)} 近戰突擊：{detail}"))
            engaged |= set(atks)
            if push > 0:
                for d in defs:
                    if ar.status_of(s["units"][d]) in ar.COMBAT_STATUSES:
                        tk.forced_push(s, d, push, ev)
            return engaged

    # 第二段：RED-SF 已脫離 → 追擊 RED-AD，但該格若另有敵師級編隊則不推進
    if st["phase"] == 1:
        st["phase"] = 2
        ev.append(("allies", "應變第一段結束（RED-SF 已脫離 (13,8) 相鄰範圍），轉入第二段：追擊 RED-AD"))
    if not ad or ar.status_of(ad) not in ar.COMBAT_STATUSES:
        return engaged
    others = [uid for uid, x in s["units"].items()
              if x.get("side") == "axis" and uid != "RED-AD"
              and list(x["pos"]) == list(ad["pos"]) and tk.is_division(x)]
    if others:
        ev.append(("allies", f"應變第二段之禁止條件成立：RED-AD 所在格 {tuple(ad['pos'])} "
                             f"另有敵師級編隊 {'、'.join(others)} 會合，BLU-AD 與 BLU-3 "
                             f"不推進，留在 {HOLD_HEX} 固守並以壓制支援"))
        return engaged
    chasers = [u for u in CHASE if u in s["units"] and ar.under_command(s, u)]
    adj = [u for u in chasers if ar.dist(s["units"][u]["pos"], ad["pos"]) == 1]
    if adj:
        defs = [uid for uid, x in s["units"].items()
                if x.get("side") == "axis" and list(x["pos"]) == list(ad["pos"])
                and ar.status_of(x) in ar.COMBAT_STATUSES]
        detail, push = ar.battle(s, adj, defs, list(ad["pos"]))
        ev.append((adj[0], f"★近戰突擊 {tuple(ad['pos'])}（應變第二段）：{detail}"))
        for d in defs:
            ev.append((d, f"★遭 {'／'.join(adj)} 近戰突擊：{detail}"))
        engaged |= set(adj)
        if push > 0:
            for d in defs:
                if ar.status_of(s["units"][d]) in ar.COMBAT_STATUSES:
                    tk.forced_push(s, d, push, ev)
    return engaged


def resolve(s, gh):
    ev = []
    if gh == BLU_L1:
        ev.append(("allies", "藍軍新令生效：全軍火力任務改「壓制」，打到彈盡"))
    if gh == RED_AD_GH:
        ev.append(("axis", "RED-AD 新令生效：停止西進，撤向 (20,9) RED-2 工事內"))
    if gh == RED_SF_GH:
        ev.append(("axis", "RED-SF 新令生效：撤向 (17,10)"))

    engaged = blue_assault(s, gh, ev)

    # 藍軍火力：射程內已偵獲敵編隊，工事最低／覆蓋率最高者優先（其 T8 火力通則）
    mis = mission(gh)
    shooters = [u for u in ("BLU-1", "BLU-2", "BLU-AD-sp1", "BLU-1-a1", "BLU-1-a2",
                            "BLU-3-a1", "BLU-3-a2")
                if u in s["units"] and u not in engaged and tk.can_fire(s, u)]
    by = {}
    for sh in shooters:
        cands = []
        for e in tk.spotted(s, "allies"):
            x = s["units"].get(e)
            if not x or ar.status_of(x) not in ar.COMBAT_STATUSES:
                continue
            if not tk.in_range(s, sh, x["pos"]):
                continue
            if any(y.get("side") == "allies" and list(y["pos"]) == list(x["pos"])
                   for y in s["units"].values()):
                continue                      # 避免友軍誤擊（藍軍明文）
            cands.append((x.get("fortification", 0.0), -ar.impact_coverage(x), e))
        if cands:
            by.setdefault(min(cands)[2], []).append(sh)
    for tgt, shs in by.items():
        apply_fire(s, shs, tgt, mis, ev)

    # 紅軍撤退與固守（本回無射擊命令）
    dest = dict(RED_DEST)
    if gh >= RED_AD_GH:
        dest["RED-AD"] = (20, 9)
    if gh >= RED_SF_GH:
        dest["RED-SF"] = (17, 10)
    else:
        sf = s["units"].get("RED-SF")
        if sf and sf["flags"].get("hit"):     # 紅軍應變：遭擊即沿撤退路線東撤
            dest["RED-SF"] = (17, 10)
    for uid, dst in dest.items():
        u = s["units"].get(uid)
        if not u or not ar.under_command(s, uid) or u["flags"].get("fired"):
            continue
        if list(u["pos"]) != list(dst):
            _, m = ar.advance(s, uid, list(dst))
            ev.append((uid, m))
        elif uid in DIG:
            m = tk.try_dig(s, uid)
            if m:
                ev.append((uid, m))

    # 藍軍第二段的推進（未接敵者）
    ad = s["units"].get("RED-AD")
    if st["phase"] == 2 and ad and ar.status_of(ad) in ar.COMBAT_STATUSES:
        others = [uid for uid, x in s["units"].items()
                  if x.get("side") == "axis" and uid != "RED-AD"
                  and list(x["pos"]) == list(ad["pos"]) and tk.is_division(x)]
        if not others:
            for u in CHASE:
                x = s["units"].get(u)
                if not x or u in engaged or x["flags"].get("fired") or x["flags"].get("moved"):
                    continue
                if ar.dist(x["pos"], ad["pos"]) > 1:
                    _, m = ar.advance(s, u, list(ad["pos"]) if ar.dist(x["pos"], ad["pos"]) > 1
                                      else x["pos"])
                    ev.append((u, f"{u} 追擊：{m}"))
    # 靜止編隊的構工（僅明文受命者）
    for uid in DIG:
        u = s["units"].get(uid)
        if u and u.get("side") == "allies" and not u["flags"].get("moved") \
                and not u["flags"].get("fired"):
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
print("═" * 70)
print(f"★★ 終局計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']} ★★")
print(f"   藍軍造成 {sc['allies']['inflicted']}")
print(f"   紅軍造成 {sc['axis']['inflicted']}")
w = "藍軍" if sc["allies"]["points"] > sc["axis"]["points"] else (
    "紅軍" if sc["axis"]["points"] > sc["allies"]["points"] else "平手")
print(f"   → **{w}**" + ("" if w == "平手" else
      f"勝，差 {abs(sc['allies']['points'] - sc['axis']['points'])} 分"))
print("═" * 70)
for side in ("allies", "axis"):
    print(f"\n── {ZH[side]} ──")
    for uid, u in sorted(ar.own(s, side).items()):
        print(f"  {uid:14} {str(tuple(u['pos'])):9} 兵{u.get('personnel',0):>6}"
              f" 力{u.get('strength'):>5.1f} 組{u.get('org'):>5.1f}"
              f" 砲{u['equip']['guns']:>3} 車{u['equip']['tanks']:>3}"
              f" 損{u['losses']['personnel']:>5}/{u['losses']['tanks']}/{u['losses']['guns']}"
              f" {ar.status_of(u)}")
snap = HERE / "final_state.json"
snap.write_text(Path(ar.STATE).read_text())
print(f"\n✅ 終局狀態 {snap}")
