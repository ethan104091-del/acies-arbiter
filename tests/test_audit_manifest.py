#!/usr/bin/env python3
"""Phase 1 的回歸網 — 每一項都必須證明它抓得到 Run 7 那次**真實的**瑕疵。

`docs/plan_run8.md` 的 1-E。設計原則：
**光證明新程式能跑不算回歸測試，要證明舊錯誤現在會被擋下。**
故每個測試都先重現一次歷史錯誤，再斷言引擎或稽核把它攔住。

| 測試 | 重現的瑕疵 | 出處 |
|---|---|---|
| `t_ruling47_*` | 裁示 47 的護欄只套在一方身上／層級太高 | 判例 §二十四 錯誤一、二 |
| `t_push_not_march` | 「守方後退 N 格」被實作成行軍 | 判例 §二十五 |
| `t_push_attacker` | `push < 0`（攻方被逐回）四局從未執行 | `docs/TODO.md` R8-G1 |
| `t_a3_dig` | 構工批次化 `set(DEST)`，白給一方 13,988 man-hr | 判例 §二十一 |
| `t_a4_move` | 沿用已被新命令取代的目的地 | 判例 §二十四 錯誤三 |
| `t_a5_push` | 逼退沒真的執行 | 判例 §二十五 |
| `t_a6_fire` | 開火無命令出處 | 新增 |
| `t_a7_stale` | 從上一 tick 的腳本複製 | 判例 §二十四 定案 2 |
| `t_a8_mixed` | 敵我同格 | 裁示 47 |
| `t_combined_arms` | 協同第 4 級（`.get` 預設值）與手冊不符 | 判例 §二十六 |
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runs"))
import arbiter as ar          # noqa: E402
import _audit                 # noqa: E402
import _manifest              # noqa: E402

SNAP = ROOT / "runs" / "run7_openfield" / "snap_T8start.json"
FAILED = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILED.append(label)


def fresh():
    s = ar.load(SNAP)
    for u in s["units"].values():
        u["flags"] = {}
    s["push_ledger"] = []
    s["works_ledger"] = []
    return s


def mf_ok(tick=8):
    return _manifest.TickOrders(tick=tick)


# ── 裁示 47：敵佔格護欄在引擎內，對兩方都成立 ────────────────────────
print("\n── 裁示 47 護欄（判例 §二十四）──")
s = fresh()
# 找相鄰的敵我對
adj = [(a, b) for a, ua in s["units"].items() for b, ub in s["units"].items()
       if ua.get("side") == "allies" and ub.get("side") == "axis"
       and ar.dist(ua["pos"], ub["pos"]) == 1]
A, D = adj[0]
check("★ 相鄰時 advance 拒絕移入敵佔格（藍→紅）",
      ar.advance(s, A, list(s["units"][D]["pos"]))[0] is False)
check("★ 同一護欄對紅軍也成立（不是單方清單）",
      ar.advance(s, D, list(s["units"][A]["pos"]))[0] is False,
      "§二十四 錯誤一：初版只檢查藍軍的移動")

# 錯誤二：層級太高——遠處的編隊必須照樣前進，不得整個 tick 不動
s = fresh()
far = sorted((k for k, v in s["units"].items()
              if v.get("side") == "allies" and ar.dist(v["pos"], s["units"]["RED-SF"]["pos"]) >= 3),
             key=lambda k: ar.dist(s["units"][k]["pos"], s["units"]["RED-SF"]["pos"]))
FK = far[0]
was = list(s["units"][FK]["pos"])
ar.advance(s, FK, list(s["units"]["RED-SF"]["pos"]))
check("★ 三格外的編隊仍照常接近（只擋最後一步，不擋整段）",
      list(s["units"][FK]["pos"]) != was,
      f"§二十四 錯誤二：第二版寫成「目標格有敵軍就完全不動」　{tuple(was)}→"
      f"{tuple(s['units'][FK]['pos'])}")
check("　接近後未踏進敵佔格",
      list(s["units"][FK]["pos"]) != list(s["units"]["RED-SF"]["pos"]))


# ── 判例 §二十五：逼退是強制位移，不是行軍 ──────────────────────────
print("\n── 逼退＝強制位移（判例 §二十五）──")
s = fresh()
u = s["units"]["RED-SF"]
u["org"], u["fatigue"] = 0.0, 100        # 重現 T8 當時「org 歸零、疲勞爆表」
r_march = ar.move_rate(s, u, ".")
was = list(u["pos"])
n = ar.forced_push(s, "RED-SF", 3)
check("★ 逼退 3 格不受移動速率限制", n == 3,
      f"該編隊的行軍速率僅 {r_march:.2f} 格/hr（初版用 advance 因此只挪 {r_march:.2f} 格）")
check("　位移方向為該方補給源（axis 向東）",
      s["units"]["RED-SF"]["pos"][0] == was[0] + 3, f"{tuple(was)}→{tuple(u['pos'])}")
check("　逼退後工事防護歸零", u.get("fortification", 0) == 0)
check("　逼退記入 push_ledger（供 A5 對帳）",
      len(s["push_ledger"]) == 1 and s["push_ledger"][0]["moved"] == 3)

# battle 自行執行逼退，且舊寫法會大聲壞掉
s = fresh()
_, res = ar.battle(s, ["BLU-AD", "BLU-3"], ["RED-SF"], list(s["units"]["RED-SF"]["pos"]))
check("★ battle 自行執行逼退（不再交給解算腳本）",
      res.displaced.get("RED-SF", 0) > 0, repr(res))
try:
    _ = res > 0
    check("★ 舊寫法 `if push > 0` 會 raise", False)
except TypeError:
    check("★ 舊寫法 `if push > 0` 會 raise", True,
          "R8-G1：四局以來所有腳本都只寫 push > 0，攻方逼退從未執行")


# ── R8-G1：攻方被逼退（push < 0）現在真的會執行 ─────────────────────
print("\n── 攻方被逼退（R8-G1，四局從未執行過）──")
s = fresh()
weak = "RED-2-rcn"                        # 偵察營攻擊挖好工事的師 → 兵力比必然 <0.5
tgt = "BLU-1"
s["units"][weak]["pos"] = [x for x in s["units"][tgt]["pos"]]
s["units"][weak]["pos"][0] += 1
was = list(s["units"][weak]["pos"])
detail, res = ar.battle(s, [weak], [tgt], list(s["units"][tgt]["pos"]))
check("兵力比 <0.5 → 對照表判攻方退", res.push == -1, f"push={res.push}")
check("★ 攻方真的被逐回", res.side_pushed == "attacker" and res.displaced.get(weak, 0) == 1,
      f"{tuple(was)}→{tuple(s['units'][weak]['pos'])}")


# ── A3：構工須明確下令（判例 §二十一）─────────────────────────────
print("\n── A3 構工授權（判例 §二十一）──")
s = fresh()
b = _audit.snapshot(s)
ar.dig(s, "RED-AD")                       # 沒有登記構工令就挖
mf = mf_ok()
out = _audit.check_dig_authorized(s, b, mf)
check("★ 未經下令的構工被抓到", any(sev == "錯誤" for sev, _ in out),
      out[0][1][:78] if out else "（無發現）")
mf2 = mf_ok().dig_order("RED-AD", src="紅軍 T8 第 2 條")
check("　登記了構工令即通過", not _audit.check_dig_authorized(s, b, mf2))

s = fresh()
b = _audit.snapshot(s)
ar.camouflage(s, "RED-3")
check("★ 未經下令的偽裝作業也被抓到",
      any(sev == "錯誤" for sev, _ in _audit.check_dig_authorized(s, b, mf_ok())))


# ── A4：移動須有登記的目的地（判例 §二十四 錯誤三）──────────────────
print("\n── A4 移動授權（判例 §二十四）──")
s = fresh()
b = _audit.snapshot(s)
ar.advance(s, "BLU-1", [s["units"]["BLU-1"]["pos"][0] + 3, s["units"]["BLU-1"]["pos"][1]])
out = _audit.check_movement_authorized(s, b, mf_ok())
check("★ 無登記目的地的移動被抓到", any(sev == "錯誤" for sev, _ in out),
      out[0][1][:78] if out else "（無發現）")
mfm = mf_ok().march("BLU-1", (b["units"]["BLU-1"]["pos"][0] + 3, b["units"]["BLU-1"]["pos"][1]),
                    src="藍軍 T8 第 1 條")
check("　登記了目的地即通過", not _audit.check_movement_authorized(s, b, mfm))
# 朝反方向走（沿用舊目的地的典型症狀）
mfw = mf_ok().march("BLU-1", (b["units"]["BLU-1"]["pos"][0] - 5, b["units"]["BLU-1"]["pos"][1]),
                    src="藍軍 T8 第 1 條")
check("★ 移動後離登記目的地更遠 → 抓到",
      any(sev == "錯誤" for sev, _ in _audit.check_movement_authorized(s, b, mfw)))
# 逼退造成的位移不得被誤判
s = fresh()
b = _audit.snapshot(s)
ar.forced_push(s, "RED-SF", 2)
check("　逼退造成的位移不算違規（已有帳）",
      not _audit.check_movement_authorized(s, b, mf_ok()))


# ── A5：逼退必須真的執行（判例 §二十五）───────────────────────────
print("\n── A5 逼退執行（判例 §二十五）──")
s = fresh()
s["push_ledger"] = [{"gh": 48, "uid": "RED-SF", "ordered": 3, "moved": 0}]
out = _audit.check_push_executed(s, _audit.snapshot(s), mf_ok())
check("★ 應退 3 格卻只動 0 格且無說明 → 錯誤",
      any(sev == "錯誤" for sev, _ in out), out[0][1][:78] if out else "（無發現）")
s["push_ledger"] = [{"gh": 48, "uid": "RED-SF", "ordered": 3, "moved": 1,
                     "note": "地圖邊界"}]
out = _audit.check_push_executed(s, _audit.snapshot(s), mf_ok())
check("　載明受阻原因 → 降為注意，不阻斷",
      out and all(sev != "錯誤" for sev, _ in out))


# ── A6／A7／A8 ────────────────────────────────────────────────
print("\n── A6 射擊授權／A7 命令出處／A8 敵我同格 ──")
s = fresh()
b = _audit.snapshot(s)
s["units"]["BLU-1"]["flags"]["fired"] = True
check("★ 無命令出處的開火被抓到",
      any(sev == "錯誤" for sev, _ in _audit.check_fire_authorized(s, b, mf_ok())))
mff = mf_ok().fire_mission(["BLU-1"], target="RED-1", mission="壓制", src="藍軍 T8 第 4 條")
check("　登記了火力任務即通過", not _audit.check_fire_authorized(s, b, mff))
mfc = mf_ok().contingency_fired("BLU-1", src="藍軍 T8 應變第 1 條")
check("　應變觸發的開火亦通過（須登記哪一條）",
      not _audit.check_fire_authorized(s, b, mfc))

mfs = mf_ok().march("BLU-1", (10, 9), src="藍軍 T7 第 1 條")     # 抄上一 tick
check("★ 出處指向上一 tick → A7 錯誤",
      any(sev == "錯誤" for sev, _ in _audit.check_manifest_valid(s, b, mfs)))

s = fresh()
s["units"]["RED-SF"]["pos"] = list(s["units"]["BLU-3"]["pos"])   # 硬塞成同格
check("★ 敵我同格 → A8 錯誤",
      any(sev == "錯誤" for sev, _ in _audit.check_no_mixed_hex(s, None, None)))
s = fresh()
check("　正常狀態下 Run 7 T8 的實際部署無敵我同格",
      not _audit.check_no_mixed_hex(s, None, None))


# ── 漏查必須看得見 ────────────────────────────────────────────
print("\n── 不傳 manifest 時，漏查的項目必須發聲 ──")
s = fresh()
f = _audit.run(s, _audit.snapshot(s))
notes = [k for k, v in f.items() if any("未檢查" in m for _, m in v)]
check("★ 未提供命令清單時，需要它的檢查一律報「未檢查」",
      len(notes) >= 4, "／".join(notes))


# ── 判例 §二十六：協同第 4 級 ──────────────────────────────────
print("\n── 協同倍率（判例 §二十六）──")
check("引擎 4 兵種 = 1.7（不在 COMBINED dict 裡，是 .get 預設值）",
      ar.COMBINED.get(4, 1.7) == 1.7 and 4 not in ar.COMBINED)
check("★ 裝甲師 ∪ 步兵師 = 4 兵種（故 1.7 是常見情況，不是特例）",
      len(ar.ARM_OF_TYPE["armor"] | ar.ARM_OF_TYPE["infantry"]) == 4,
      "＝".join(sorted(ar.ARM_OF_TYPE["armor"] | ar.ARM_OF_TYPE["infantry"])))
check("5 兵種仍為 1.7（combined_arms_v1 的 1.85 不成立）",
      ar.COMBINED.get(5, 1.7) == 1.7)


print()
if FAILED:
    print(f"{len(FAILED)} 項失敗: {FAILED}")
    sys.exit(1)
print("ALL PHASE-1 REGRESSION TESTS PASS")
