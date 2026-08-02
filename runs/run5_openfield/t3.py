#!/usr/bin/env python3
"""Run 5 Tick 3 解算（gh18-23，1944-08-26 00:00-05:00，夜間，gh23 黎明）。

雙方主力全部靜止：紅軍完全休整、藍軍就地構築工事。動的只有偵察部隊。
兩軍的偵察軸線在 y=2-3 / x=16-20 一帶交會 → **本 tick 極可能首次接觸**。

延遲：藍軍前進指揮所 (4,10) 罩住主力（0 級，L1 → gh19）；BLU-SF 系列在半徑外（+1 → gh20）。
紅軍前進指揮所 (24,9) 已於 gh16 啟用且軍長進駐 → 其主力與偵察隊多在 6 格內（0 級，L1 → gh19）。
逐編隊計算（裁示 57）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import arbiter as ar          # noqa: E402
import hourstate as hs        # noqa: E402
import command                # noqa: E402

s = ar.load()
assert s["global_hour"] == 18, f"必須從 gh18 起始，現在 gh={s['global_hour']}"

# ── 下令：逐編隊依其發令時位置計算延遲（裁示 57 ＋ 缺陷 17 的修正）──────
ORDERS = [
    ("axis", "L1", "RED-2-2-r4", "留 (24,9) 續構築工事至有頂蓋級，不移動不追擊"),
    ("axis", "L2", "RED-3-rcn", "向 (16,3) 前進偵察，發現敵軍即停止前推、原地隱蔽觀察並回報"),
    ("axis", "L2", "RED-2-rcn", "向 (16,8) 前進偵察，發現敵軍即停止前推、原地隱蔽觀察並回報"),
    ("axis", "L1", "RED-3", "在 (24,3) 完全休整"),
    ("axis", "L1", "RED-2", "在 (24,9) 完全休整，維持前進指揮所近接支援"),
    ("axis", "L1", "RED-1", "在 (24,12) 完全休整"),
    ("axis", "L1", "RED-AD", "在 (23,10) 完全休整"),
    ("axis", "L1", "RED-SF", "在 (21,15) 完全休整並保持隱蔽"),
    ("allies", "L1", "BLU-1", "(4,7) 原地不動，續構築工事至有頂蓋級，達成後完全休整"),
    ("allies", "L1", "BLU-2", "(4,8) 原地不動，續構築工事至有頂蓋級，達成後完全休整"),
    ("allies", "L1", "BLU-3", "(4,11) 原地不動，續構築工事至有頂蓋級（維持與 (4,10) 相鄰）"),
    ("allies", "L1", "BLU-AD", "(7,9) 原地不動，續構築工事含戰車掩壕至有頂蓋級"),
    ("allies", "L1", "BLU-2-1-r4", "(4,10) 續構築工事至有頂蓋級，固守不得離格"),
    ("allies", "L1", "BLU-3-1-r7", "本 tick 就地完全休整，06:00 起進駐 (4,10) 並構築工事"),
    ("allies", "L1", "BLU-1-1-r1", "本 tick 就地完全休整清疲勞，06:00 起續行進駐 (5,9) 森林格"),
    ("allies", "L1", "BLU-1-rcn", "本 tick 全程完全休整，06:00 起入 (13,6) 森林格隱蔽觀測"),
    ("allies", "L1", "BLU-3-rcn", "本 tick 全程完全休整，06:00 起入 (16,11) 森林格隱蔽觀測"),
    ("allies", "L1", "BLU-AD-rcn", "本 tick 全程完全休整，06:00 起入 (10,13) 森林格隱蔽觀測"),
    ("allies", "L1", "BLU-2-rcn", "(5,15) 原地不動任後方警戒哨，構築工事至散兵壕級以上"),
    ("allies", "L1", "BLU-SF", "本 tick 全程隱蔽完全休整，06:00 起全速東進 (22,2)→(25,5)"),
    ("allies", "L1", "BLU-SF-rcn", "本 tick 即開始夜間東進沿 y=1-2 前往 (20,2)，不休整"),
]
EFF = {}
for side, lvl, uid, txt in ORDERS:
    extra = command.delay_tier_adjust(s, side, s["units"][uid]["pos"])
    o = hs.enqueue_order(s, side, lvl, f"{uid}：{txt}", extra_delay=extra)
    EFF[uid] = o["effective_global_hour"]

DIG = ["BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-2-1-r4", "BLU-2-rcn", "RED-2-2-r4",
       "RED-2-1-r4"]
REST = ["RED-1", "RED-2", "RED-3", "RED-AD", "RED-SF",
        "BLU-1-rcn", "BLU-3-rcn", "BLU-AD-rcn", "BLU-3-1-r7", "BLU-1-1-r1", "BLU-SF"]
MOVE = {"RED-3-rcn": (16, 3), "RED-2-rcn": (16, 8), "BLU-SF-rcn": (20, 2)}
halted = set()          # 依各自命令「發現敵軍即停止前推」


def resolve(s, gh):
    ev = []
    for uid in DIG:
        u = s["units"].get(uid)
        if not u or gh < EFF.get(uid, 0):
            continue
        if u.get("dig_hours", 0) >= 8.0:            # 已達有頂蓋 → 轉完全休整
            continue
        r = ar.dig(s, uid)
        if r:
            ev.append((uid, f"{uid} 構築工事 → {r[0]}（{u['dig_hours']:.2f}hr，暴露 {r[2]}）"))

    for uid, tgt in MOVE.items():
        u = s["units"].get(uid)
        if not u or gh < EFF.get(uid, 0) or uid in halted:
            continue
        seen = s.get("fog_of_war", {}).get(f"{u['side']}_spotted", [])
        near = [e for e in seen if ar.dist(s["units"][e]["pos"], u["pos"]) <= 3]
        if near and uid.startswith("RED"):
            halted.add(uid)
            ev.append((uid, f"{uid} 依命令停止前推、原地隱蔽觀察（3 格內偵獲 {', '.join(near)}）"))
            continue
        if near and uid == "BLU-SF-rcn":
            # 命令：遇敵繞行、不接戰。偵察營沿 y=1-2 東進，遇敵改走更北緣
            alt = (tgt[0], max(0, u["pos"][1] - 1))
            _, msg = ar.advance(s, uid, list(alt))
            ev.append((uid, f"{uid} 遇敵繞行（3 格內 {', '.join(near)}）改沿更北緣：{msg}"))
            continue
        if list(u["pos"]) != list(tgt):
            _, msg = ar.advance(s, uid, list(tgt))
            ev.append((uid, msg))
    return ev
    # REST 名單不做任何事 → 管線自動給完全休整 -10 疲勞


log = []
lines = ar.run_tick(s, resolve, hours=6, log=log)
ar.save(s)
print("=" * 78)
for line in lines:
    print(line)
print("=" * 78)
sc = ar.score(s)
print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}｜斬首：{command.decapitation(s)}")
print(f"事實紀錄：{len(s.get('record', []))} 筆")
for side in ("allies", "axis"):
    fo = s.get("fog_of_war", {}).get(f"{side}_spotted", [])
    print(f"{side:7} 已偵獲敵編隊：{fo or '（無）'}")
print()
print(f"{'編隊':13} {'位置':10} {'疲勞':>4} {'org':>6} {'工事':>6} {'工時':>5} {'暴露':>6}")
for uid, u in sorted(s["units"].items()):
    if u.get("side") not in ("allies", "axis"):
        continue
    print(f"{uid:13} {str(tuple(u['pos'])):10} {u.get('fatigue',0):4} {u.get('org',0):6} "
          f"{u.get('fortification',0):6.2f} {u.get('dig_hours',0):5.1f} "
          f"{ar.exposure_factor(u, ar.terr(s,u['pos'])):6}")
