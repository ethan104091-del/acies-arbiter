#!/usr/bin/env python3
"""編隊狀態機與事實紀錄層的驗證（arbiter.py 缺陷 9 的修補）。

四部分：
  A. 回歸——把每 hour 的鈎子套在 Run 4 終局狀態上，確認**全部不觸發**
  B. 正向——用合成狀態證明條件成立時它**真的會觸發**（潰散 → 示降 → 受降）
  C. 事實紀錄——證明引擎只記事實：**沒有條號、沒有合法性認定、沒有自動制裁**
  D. 可觀察狀態旗標受持續接觸門檻約束（日後爭執「明知」時的紀錄）

    python3 test_status_machine.py
"""
import copy
import json
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 引擎模組在 repo 根
import arbiter as ar                                          # noqa: E402

RUN4 = Path(__file__).resolve().parent.parent / "runs" / "run4_openfield" / "final_state.json"
fails = []


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + extra) if extra else ''}")
    if not cond:
        fails.append(name)


def fresh():
    """Run 4 終局狀態的乾淨副本。

    注意：這是**直接讀 raw JSON**，不經過 ar.load() 的正規化——正是缺陷 19 的情境。
    故此處必須自行補上 load() 會 setdefault 的欄位，否則測試會拿到與實際執行不同的狀態。
    """
    s = copy.deepcopy(json.load(open(RUN4)))
    s["record"] = []
    s.setdefault("works", {})
    for u in s["units"].values():
        u["flags"] = {}
        if u.get("side") in ("allies", "axis"):
            u.setdefault("equip", dict(ar.EQUIP.get(u.get("type"), {"tanks": 0, "guns": 0})))
            ar.ensure_ammo(u)                      # Run 7：彈藥實數化
    return s


def encircle(s, uid, tag):
    for i, n in enumerate(ar._neighbors(s, s["units"][uid]["pos"])):
        s["units"][f"__{tag}{i}"] = {
            "side": ar.ENEMY[s["units"][uid]["side"]], "pos": n, "type": "infantry",
            "name": f"圍{i}", "short": f"{tag}{i}", "org": 100, "personnel": 500,
            "equip": {"tanks": 0, "guns": 0}, "flags": {}, "resources": {"RAT": 100},
            "losses": {"personnel": 0, "tanks": 0, "guns": 0},
            "visibility_state": "EXPOSED"}


# ── A. Run 4 回歸：狀態機必須全程沉默 ──────────────────────────────
print("A. Run 4 終局狀態套用每 hour 鈎子")
s = fresh()
ar.refresh_return_fire(s)
ar.evaluate_status(s)

routed = [k for k, u in s["units"].items() if ar.status_of(u) == ar.STATUS_ROUTED]
met = [k for k, u in s["units"].items() if u.get("surrender_eligible")]
check("無編隊潰散", not routed, f"routed={routed}")
check("無編隊符合投降條件", not met, f"met={met}")
check("無事實紀錄產生（沒有交火事件被解算）", not s["record"])
check("最慘的 RED-1 仍為 ACTIVE",
      ar.status_of(s["units"]["RED-1"]) == ar.STATUS_ACTIVE,
      f"org={s['units']['RED-1']['org']} 傷亡率="
      f"{s['units']['RED-1']['losses']['personnel'] / 14030:.1%}")

# ── B. 正向：潰散 → 示降 → 受降 ───────────────────────────────────
print("\nB. 合成狀態：潰散 → 示降 → 受降")
t = fresh()
v = t["units"]["RED-1"]
gh = t["global_hour"]
v["org"] = 20.0                                 # combat_v1 潰散：org<25
v["supply_status"] = "cut"                      #                 退路切斷
v["personnel"] = 6000
v["cas_log"] = [[gh - 3, 4000]]                 #                 24hr 傷亡 40%>30%
check("cas_24h 自我正規化（不受抽離污染）",
      abs(ar.cas_24h(t, "RED-1") - 0.40) < 1e-9, f"={ar.cas_24h(t, 'RED-1'):.2%}")

pos_before = tuple(v["pos"])
ev = ar.evaluate_status(t)
check("潰散觸發", ar.status_of(v) == ar.STATUS_ROUTED)
check("潰散強制後撤", tuple(v["pos"]) != pos_before, f"{pos_before} → {tuple(v['pos'])}")
check("撤退即棄工事", v["fortification"] == 0.0)
check("潰散事件有推播", any(k == "rout" for _, k, _ in ev))
check("追擊倍率 ×3（combat_v1，§2 明文合法）", ar.pursuit_factor(t, "RED-1") == 3.0)

# 示降沒有任何門檻：org 20 仍在，一樣可以宣告
t2 = copy.deepcopy(t)
ok, msg = ar.declare_surrender(t2, "RED-1")
check("任何編隊隨時都可以示降（無資格門檻）", ok)
check("示降訊息不下合法性結論，且明示交由法庭",
      ("W1" not in msg and "W2" not in msg and "W7" not in msg
       and "構成" not in msg and "引擎不作認定" in msg),
      msg.split("。")[-2] if "。" in msg else msg)
check("示降不可逆", not ar.declare_surrender(t2, "RED-1")[0])

# 打到符合投降條件 → **部隊自行投降，指揮官失去控制權**
v["org"] = 10.0
encircle(t, "RED-1", "B")
check("四面包圍判定成立", ar.encircled(t, "RED-1"))
ev = ar.evaluate_status(t)
check("自動投降觸發（combat_v1 字面讀法）",
      ar.status_of(v) == ar.STATUS_SURRENDERED
      and ar.surrender_kind(v) == ar.SURR_AUTO)
check("自動投降 → 指揮官失去控制權", not ar.under_command(t, "RED-1"))
pos_hold = list(v["pos"])
moved_flag, moved_msg = ar.advance(t, "RED-1", [0, v["pos"][1]])
check("失控者不接受移動命令（且回傳正確的二元組）",
      moved_flag is False and "不接受命令" in moved_msg and list(v["pos"]) == pos_hold,
      moved_msg)
cas, tk, gk, msg = ar.bombard(t, ["RED-1"], "BLU-1")
check("失控者不開火（因此不可能用它詐降）", cas == 0 and "無可受命" in msg, msg)
check("已投降者不得主張防禦戰力",
      ar.unit_cp(t, "RED-1", v["pos"], is_attacker=False) == 0.0)
check("自動投降事件明白告知指揮官已失去控制權",
      any(k == "surrender_auto" and "失去對它的控制權" in txt for _, k, txt in ev))
check("自動投降也是事實紀錄的一筆",
      any(r["kind"] == "自行投降" and r.get("path") == ar.SURR_AUTO
          for r in t["record"]))

captor_before = t["units"]["BLU-1"]["personnel"]
res = ar.accept_surrender(t, "RED-1", by_uid="BLU-1")
check("俘虜計入受降方（POW 與陣亡同權）",
      res and res["pow"] == 6000 and t["units"]["RED-1"]["losses"]["personnel"] >= 6000,
      f"POW={res and res['pow']}")
check("受降成本：抽出看管兵力",
      t["units"]["BLU-1"]["personnel"] == captor_before - res["guard"],
      f"guard={res['guard']}")
rat_before = t["units"]["BLU-1"]["resources"]["RAT"]
ar.pow_upkeep(t)
check("受降成本：俘虜口糧每 hour 扣 RAT",
      t["units"]["BLU-1"]["resources"]["RAT"] < rat_before,
      f"{rat_before} → {t['units']['BLU-1']['resources']['RAT']}（{res['rat_per_hour']}/hr）")

# ── C. 事實紀錄層：引擎不判罪 ─────────────────────────────────────
print("\nC. 事實紀錄：引擎只記事實，不作法律認定")
w = fresh()
x = w["units"]["RED-1"]
x["status"] = ar.STATUS_SURRENDERED
x["surrender_gh"] = w["global_hour"] - 5
x["org"] = 10.0
x["supply_status"] = "cut"
encircle(w, "RED-1", "C")

rec = ar.record_engagement(w, ["BLU-1"], "RED-1", kind="砲擊")
check("交火事實有登錄", rec is not None and w["record"][-1] is rec)
check("紀錄含開火方、對象、時刻",
      rec["actor_side"] == "allies" and rec["target"] == "RED-1" and "gh" in rec)
check("紀錄含對象宣告示降的時刻（法庭要算寬限期用）",
      rec.get("target_declared_surrender_gh") == w["global_hour"] - 5)
check("紀錄含對象客觀狀態（org／補給／包圍／傷亡率）",
      all(k in rec for k in ("target_org", "target_supply",
                             "target_encircled", "target_cas_rate")),
      f"org={rec['target_org']} supply={rec['target_supply']} 圍={rec['target_encircled']}")
check("紀錄含開火方對其持續接觸時數（法庭要判明知用）",
      "target_contact_hours" in rec)
check("★ 紀錄不含條號", "article" not in rec and "W2" not in json.dumps(rec))
check("★ 紀錄不含合法性判斷",
      not any(k in json.dumps(rec, ensure_ascii=False)
              for k in ("違法", "合法", "構成", "寬限", "可信")))

# 示降方開火：只記事實，不貼 W7、不施加任何自動制裁
w2 = fresh()
y = w2["units"]["RED-1"]
y["status"] = ar.STATUS_SURRENDERED
y["surrender_gh"] = w2["global_hour"] - 5
rec2 = ar.record_engagement(w2, ["RED-1"], "BLU-1", kind="砲擊")
check("示降方開火 → 記下「開火方曾宣告示降」這個事實",
      rec2.get("firing_units_that_had_declared_surrender") == ["RED-1"])
check("★ 不貼 W7 條號", "article" not in rec2 and "W7" not in json.dumps(rec2))
check("★ 沒有自動制裁：該方未被剝奪任何權利",
      "law_flags" not in w2 and not w2.get("surrender_void"))
check("★ 示降方仍可被受降（權利未被程式沒收）",
      ar.accept_surrender(w2, "RED-1", by_uid="BLU-1") is not None)

# 手動示降者仍在指揮官控制下——這才是詐降之所以可歸責
w3 = fresh()
ok, _ = ar.declare_surrender(w3, "RED-1")
check("手動示降者仍接受命令（詐降因此出於指揮官的決定）",
      ok and ar.under_command(w3, "RED-1")
      and ar.surrender_kind(w3["units"]["RED-1"]) == ar.SURR_DECLARED)
cas, _, _, _ = ar.bombard(w3, ["RED-1"], "BLU-1")
check("手動示降者可以被命令開火（詐降是可能的，不被程式禁止）", cas > 0, f"傷亡 {cas}")
check("該次開火留下「曾宣告示降」的事實",
      w3["record"][-1].get("firing_units_that_had_declared_surrender") == ["RED-1"])
check("對手仍可選擇不受降：受降須明確呼叫，引擎不自動執行",
      ar.status_of(w3["units"]["RED-1"]) == ar.STATUS_SURRENDERED
      and w3["units"]["RED-1"]["personnel"] > 0)

# ── D. 可觀察狀態旗標 ─────────────────────────────────────────────
print("\nD. 可觀察狀態旗標（明知的紀錄，非法律結論）")
d = fresh()
z = d["units"]["RED-1"]
z["no_return_fire_since"] = d["global_hour"] - 3
z["contact_hours"] = {"allies": 1}
check("接觸未滿 2 hour → 不顯示（該方無從得知）",
      ar.combat_state_tag(d, "RED-1", "allies") == "",
      repr(ar.combat_state_tag(d, "RED-1", "allies")))
z["contact_hours"] = {"allies": 2}
tag = ar.combat_state_tag(d, "RED-1", "allies")
check("接觸滿 2 hour → 顯示「未見還擊」（觀察，不是法律結論）",
      "未見還擊" in tag and "喪失戰鬥力" not in tag, tag.strip("｜"))
z["status"] = ar.STATUS_SURRENDERED
z["surrender_gh"] = d["global_hour"]
z["contact_hours"] = {"allies": 0}
tag = ar.combat_state_tag(d, "RED-1", "allies")
check("示降是對敵宣告 → 無條件顯示", "示降" in tag or "投降" in tag, tag.strip("｜"))
check("★ 旗標不告訴對手該示降可不可信、開火會不會違法",
      not any(k in tag for k in ("可信", "違法", "合法", "W2")), tag.strip("｜"))

# ── E. org 六項、缺陷 8、缺陷 10 ──────────────────────────────────
print("\nE. 組織度衝擊六項 ＋ 缺陷 8／10")
e = fresh()
g = e["units"]["RED-1"]
g["fortification"] = 0.0
g["combat_hours"] = 0
base = ar.org_impact(e, "RED-1", casualty_pct=2.0)
check("只有傷亡時＝Casualty% × 1.5", abs(base - 3.0) < 1e-9, f"={base}")
g["combat_hours"] = 6
supp = ar.org_impact(e, "RED-1", casualty_pct=2.0)
check("連續戰鬥滿 6 hour 起加壓制 -2", abs(supp - 5.0) < 1e-9, f"={supp}")
sur = ar.org_impact(e, "RED-1", casualty_pct=2.0, surprised=True)
check("被突襲 -10", abs(sur - 15.0) < 1e-9, f"={sur}")
ff = ar.org_impact(e, "RED-1", casualty_pct=2.0, friendly_fire=True)
check("誤擊 -10", abs(ff - 15.0) < 1e-9, f"={ff}")
g["cp_destroyed_this_hour"] = 1
cp = ar.org_impact(e, "RED-1", casualty_pct=2.0)
check("指揮所被毀 -20", abs(cp - 25.0) < 1e-9, f"={cp}")
g.pop("cp_destroyed_this_hour")
g["regt_co_kia_this_hour"] = 2
rc = ar.org_impact(e, "RED-1", casualty_pct=2.0)
check("團長陣亡 -5（可累計）", abs(rc - 15.0) < 1e-9, f"={rc}")
g.pop("regt_co_kia_this_hour")
g["fortification"] = 0.5
cov = ar.org_impact(e, "RED-1", casualty_pct=2.0)
check("工事使衝擊減半（乘法，且作用於總和）", abs(cov - 2.5) < 1e-9, f"={cov}")
check("純戰場的森林不算 Cover（只認工事）", ar.COVER_TERRAIN == ())

g["fortification"] = 0.0
g["org"] = 40.0
g["supply_status"] = "intact"
g["fatigue"] = 10
ar.org_recovery(e)
check("補給完整 → 每 hour 自然恢復 +1", g["org"] == 41.0, f"org={g['org']}")
g["fatigue"] = 90                      # 疲勞上限 75
g["org"] = 75.0
ar.org_recovery(e)
check("自然恢復不得突破疲勞上限", g["org"] == 75.0, f"org={g['org']}")
g["supply_status"] = "cut"
g["org"] = 40.0
ar.org_recovery(e)
check("補給切斷 → 不恢復", g["org"] == 40.0, f"org={g['org']}")

# 缺陷 10：被打不等於開火
f2 = fresh()
h = f2["units"]["RED-2"]
before = dict(h["flags"])
ar.hurt(f2, "RED-2", personnel=100, org=1, note="遭敵砲擊")
check("★ 缺陷 10：被擊中設 hit，不設 fired",
      h["flags"].get("hit") and not h["flags"].get("fired"), str(h["flags"]))
ar.refresh_return_fire(f2)
check("★ 因此「未見還擊」得以成立（W1 要件 B 不再永遠落空）",
      h.get("no_return_fire_since") is not None)
ar.refresh_combat_hours(f2)
check("被擊中也計入連續戰鬥時數（壓制）", h.get("combat_hours") == 1)

# 缺陷 8：strength 隨傷亡連動
f3 = fresh()
k = f3["units"]["RED-3"]
k["personnel"], k["losses"]["personnel"], k["strength"] = 10000, 0, 100.0
ar.hurt(f3, "RED-3", personnel=2000)
check("★ 缺陷 8：strength 由人員殘存率重算",
      abs(k["strength"] - 80.0) < 0.01, f"strength={k['strength']}")
k2 = f3["units"]["RED-2"]
k2["personnel"], k2["losses"]["personnel"] = 8000, 0     # 模擬抽離：現員少但無戰損
ar.hurt(f3, "RED-2", personnel=0, org=1)
check("抽離不會被誤算成戰損", abs(k2["strength"] - 100.0) < 0.01, f"strength={k2['strength']}")

# ── F. 通訊 ───────────────────────────────────────────────────────
print("\nF. 通訊：信號中斷與命令延遲")
c = fresh()
n = c["units"]["RED-1"]
n["supply_status"] = "intact"
check("補給完整 → 未失聯", not ar.signal_lost(c, "RED-1"))
n["supply_status"] = "cut"
check("僅斷補、未被包圍 → 未失聯（仍有退路可傳令）", not ar.signal_lost(c, "RED-1"))
encircle(c, "RED-1", "F")
check("斷補＋四面包圍 → 信號中斷", ar.signal_lost(c, "RED-1"))
check("失聯者新命令無法送達（回傳 None）",
      ar.command_delay(c, "axis", "RED-1") is None)
check("未失聯者有正常延遲時數",
      ar.command_delay(c, "axis", "RED-2") in (1, 2, 3),
      f"={ar.command_delay(c, 'axis', 'RED-2')} hr")
# 註：signal_lost 以「斷補 + 包圍」定義，因此潰散條件 3 的「指揮鏈中斷」
#     被「退路被切斷」完全包含，不需另立斷言（寫一個必然成立的斷言只是自欺）。
n["org"], n["cas_log"] = 20.0, [[c["global_hour"], 99999]]
n["personnel"] = 1000
ev = ar.evaluate_status(c)
check("失聯＋org<25＋24hr 傷亡>30% → 潰散",
      ar.status_of(n) in (ar.STATUS_ROUTED, ar.STATUS_SURRENDERED),
      f"status={ar.status_of(n)}")
# 『師長陣亡＋信號中斷』必須是空條件：surrender_conditions 在任何狀態下
# 都不得回傳這個事由（沒有幹部傷亡模型，不得以代理指標偷偷補上）
c2 = fresh()
m = c2["units"]["RED-1"]
m["org"], m["supply_status"] = 5.0, "cut"
m["no_supply_hours"], m["resources"]["RAT"] = 999, 0.0
encircle(c2, "RED-1", "G")
ok2, why2 = ar.surrender_conditions(c2, "RED-1")
check("★『師長陣亡＋信號中斷』是空條件，即使全部惡化也不會被列為事由",
      ok2 and not any("師長" in w or "指揮官" in w for w in why2), f"事由={why2}")

# ── G. 每 hour 管線與裁示登錄 ─────────────────────────────────────
print("\nG. run_tick 管線與 ruling() 裁示登錄")
h = fresh()
h["global_hour"] = 10
for u in h["units"].values():
    u["fatigue"] = 20
    u["flags"] = {}

seen = []
def plan(s, gh):
    seen.append(gh)
    # 前所未見的動作：裁判在此可以寫任何東西
    if gh == 11:
        ar.ruling(s, what="紅軍下令燒森林剝奪掩蔽：本 hour 該林區能見狀態降一級",
                  basis="規則書無此動作（equipment_v1 有煙幕罐但無縱火）",
                  applied="以 record_fact 記錄；效果經 refresh_visibility 前直接改 visibility_state",
                  precedent=True)
    return [("both", f"gh{gh} 測試事件")]

lines = ar.run_tick(h, plan, hours=3)
check("管線跑滿指定小時數", seen == [10, 11, 12], f"gh={seen}")
check("每小時產出一行敘事", len(lines) == 3)
check("global_hour 有推進", h["global_hour"] == 13, f"gh={h['global_hour']}")
check("裁示被登錄成有時間戳的事實",
      any(r["kind"] == "裁示" and r["gh"] == 11 for r in h["record"]))
check("標為判例者進待辦，提醒寫入 precedents.md",
      len(h.get("pending_precedents", [])) == 1)
r = next(r for r in h["record"] if r["kind"] == "裁示")
check("裁示紀錄含依據與施加方式（不是來源不明的狀態變動）",
      r["basis"] and r["applied"] and "無此動作" in r["basis"])

# 缺陷 11：行軍要累
h2 = fresh()
h2["global_hour"] = 10
m = h2["units"]["RED-1"]
m["fatigue"] = 0
f_before = m["fatigue"]


def march_plan(s, gh):
    ar.advance(s, "RED-1", [0, s["units"]["RED-1"]["pos"][1]])   # 真的走一小時
    return [("both", "RED-1 行軍")]


ar.run_tick(h2, march_plan, hours=1)
check("行軍疲勞由 advance 施加，且管線不重複加（白天恰好 +5）",
      m["fatigue"] - f_before == 5, f"{f_before} → {m['fatigue']}（應為 +5）")
h3 = fresh()
h3["global_hour"] = 10
k = h3["units"]["RED-2"]
k["fatigue"] = 50
ar.run_tick(h3, lambda s, gh: [("both", "x")], hours=1)
check("完全未動未戰 → 休整 -10", k["fatigue"] == 40, f"fatigue={k['fatigue']}")

# 缺陷 13：移動即離開工事（Run 7 起洞留在格子上，見 J 段）
h4 = fresh()
h4["global_hour"] = 10
w = h4["units"]["RED-3"]
w["flags"] = {}
ar.dig(h4, "RED-3", hours=3.0)
had = w["fortification"]
ar.advance(h4, "RED-3", [0, w["pos"][1]])
check("★ 缺陷 13：移動即離開工事（防護歸零）",
      had > 0 and w["fortification"] == 0.0 and w["dig_hours"] == 0.0,
      f"移動前 {had} → 移動後 {w['fortification']}")

# 缺陷 14：run_tick 開頭會補給，supply_status 不再是 None
h5 = fresh()
h5["global_hour"] = 10
for u in h5["units"].values():
    u.pop("supply_status", None)
ar.run_tick(h5, lambda s, gh: [("both", "x")], hours=1)
check("★ 缺陷 14：tick 開頭補給，supply_status 已寫入",
      all(u.get("supply_status") in ("intact", "contested", "cut")
          for u in h5["units"].values() if u.get("side") in ("allies", "axis")),
      str({k: v.get("supply_status") for k, v in list(h5["units"].items())[:3]}))
check("疲勞數字取自 movement_v1（行軍5/夜3/休整10/輕中重 8-15-25）",
      (ar.FATIGUE_MARCH, ar.FATIGUE_MARCH_NIGHT, ar.FATIGUE_REST_FULL,
       ar.fatigue_from_combat("light"), ar.fatigue_from_combat("medium"),
       ar.fatigue_from_combat("heavy")) == (5, 3, 10, 8, 15, 25))

# ── H. 示降／受降作為命令（機器解析，不經裁判文字解讀）──────────────
print("\nH. 示降／受降命令解析與投遞")
check("解析：示降 RED-1", ar.parse_legal_order("示降 RED-1") == ("declare", "RED-1", None))
check("解析：SURRENDER RED-1", ar.parse_legal_order("SURRENDER RED-1") == ("declare", "RED-1", None))
check("解析：受降 RED-1", ar.parse_legal_order("受降 RED-1") == ("accept", "RED-1", None))
check("解析：受降 RED-1 BY BLU-2",
      ar.parse_legal_order("受降 RED-1 BY BLU-2") == ("accept", "RED-1", "BLU-2"))
check("非規範格式不解析", ar.parse_legal_order("我方 RED-1 考慮投降") is None)
check("★ 歧義會浮出來而非被默默解讀",
      ar.looks_legal_but_unparsed("我方 RED-1 考慮投降")
      and not ar.looks_legal_but_unparsed("示降 RED-1")
      and not ar.looks_legal_but_unparsed("全線固守"))

i = fresh()
i["global_hour"] = 20
i["pending_orders"] = []
ar.hs.enqueue_order(i, "axis", "L1", "示降 RED-1", extra_delay=0)
due = ar.hs.due_orders(i, at_global_hour=i["global_hour"] + 5)
check("命令走延遲佇列（下令當時不生效）", not ar.hs.due_orders(i) and due)
i["global_hour"] += 5
ev = ar.apply_due_legal_orders(i)
check("到期後示降生效", ar.status_of(i["units"]["RED-1"]) == ar.STATUS_SURRENDERED)
check("示降為手動路徑（仍在指揮官控制下）",
      ar.surrender_kind(i["units"]["RED-1"]) == ar.SURR_DECLARED)
check("雙方各收到一則訊息（對稱告知，非我手寫）",
      any(t[0] == "axis" for t in ev) and any(t[0] == "allies" for t in ev))

# 信號中斷 → 示降命令送不進去
j = fresh()
j["global_hour"] = 20
j["pending_orders"] = []
j["units"]["RED-2"]["supply_status"] = "cut"
encircle(j, "RED-2", "H")
ar.hs.enqueue_order(j, "axis", "L1", "示降 RED-2", extra_delay=0)
j["global_hour"] += 5
ev = ar.apply_due_legal_orders(j)
check("★ 信號中斷 → 示降命令未送達（只能現地自行決定）",
      ar.status_of(j["units"]["RED-2"]) != ar.STATUS_SURRENDERED
      and any("未送達" in t[1] for t in ev), str([t[1] for t in ev])[:90])

# 受降：對手必須明確下令
k3 = fresh()
k3["global_hour"] = 20
k3["pending_orders"] = []
ar.declare_surrender(k3, "RED-3")
check("未下受降令 → 俘虜未被接收", k3["units"]["RED-3"]["personnel"] > 0)
ar.hs.enqueue_order(k3, "allies", "L1", "受降 RED-3 BY BLU-1", extra_delay=0)
k3["global_hour"] += 5
ar.apply_due_legal_orders(k3)
check("下了受降令 → 俘虜接收，且指定受降編隊生效",
      k3["units"]["RED-3"]["personnel"] == 0 and k3["units"]["BLU-1"].get("pow_held", 0) > 0,
      f"pow_held={k3['units']['BLU-1'].get('pow_held')}")

# command_delay 委派給 command.py 且反映指揮所階梯
d2 = fresh()
d2["units"]["RED-1"]["supply_status"] = "intact"
base = ar.command_delay(d2, "axis", "RED-1", "L1")
check("command_delay 委派 command.py（不再永遠回傳 2）",
      base == ar.command.command_delay(d2, "axis", "L1", d2["units"]["RED-1"]["pos"]),
      f"={base} hr")

# ── I. 工事分級 ───────────────────────────────────────────────────
print("\nI. 工事分級（[判例] Run 5 起生效）")
w4 = fresh()
u4 = w4["units"]["RED-1"]
u4["flags"] = {}
u4["fortification"], u4["dig_hours"] = 0.0, 0.0
check("未挖 → 暴露 0.70", ar.exposure_factor(u4) == 0.70)
ar.dig(w4, "RED-1", hours=0.5)
check("0.5hr 淺掘 → fort 0.15、暴露 0.40",
      u4["fortification"] == 0.15 and ar.exposure_factor(u4) == 0.40)
check("★ 第一鏟土買到最多（0.70→0.40，砍 43%）", ar.exposure_factor(u4) < 0.70 * 0.6)
for _ in range(3):
    ar.dig(w4, "RED-1")
check("累計 3.5hr → 散兵壕 0.35、暴露 0.18",
      u4["fortification"] == 0.35 and ar.exposure_factor(u4) == 0.18,
      f"dig_hours={u4['dig_hours']}")
check("散兵壕級起 Cover 生效（org 衝擊減半）",
      ar.org_impact(w4, "RED-1", casualty_pct=2.0) == 1.5,
      f"={ar.org_impact(w4, 'RED-1', casualty_pct=2.0)}")
for _ in range(5):
    ar.dig(w4, "RED-1")
check("累計 8.5hr → 有頂蓋 0.50、暴露 0.10",
      u4["fortification"] == 0.50 and ar.exposure_factor(u4) == 0.10,
      f"dig_hours={u4['dig_hours']}")

w5 = fresh()
u5 = w5["units"]["RED-SF"]
u5["flags"], u5["fortification"], u5["dig_hours"] = {}, 0.0, 0.0
ar.dig(w5, "RED-SF")
check("特戰旅人手少 → 挖得慢（0.67×）", abs(u5["dig_hours"] - 0.67) < 1e-6, f"={u5['dig_hours']}")

w6 = fresh()
u6 = w6["units"]["RED-2"]
u6["flags"], u6["dig_hours"] = {}, 3.0
ar.dig(w6, "RED-2", hours=0.0)
u6["flags"]["moved"] = True
check("移動中不得構築", ar.dig(w6, "RED-2") is None)
ar.abandon_works(u6)
check("移動即離開工事（該編隊防護歸零）", u6["fortification"] == 0.0 and u6["dig_hours"] == 0.0)

w7 = fresh()
u7 = w7["units"]["RED-3"]
u7["flags"] = {}
u7["fortification"], u7["equip"]["tanks"] = 0.15, 54
w7["units"]["BLU-1"]["pos"] = list(u7["pos"])        # 擺進砲兵射程內
w7["units"]["BLU-1"]["equip"]["guns"] = 48
cas, tk, gk, msg = ar.bombard(w7, ["BLU-1"], "RED-3")
check("淺掘對戰車效果有限（暴露 0.15 而非 0.05）", "戰車暴露0.15" in msg, msg[:60])
u7["fortification"] = 0.35
cas, tk, gk, msg = ar.bombard(w7, ["BLU-1"], "RED-3")
check("散兵壕級 → 戰車掩壕 0.05", "戰車暴露0.05" in msg, msg[:60])

# ── J. Run 7：工事的 hex 記憶（缺陷 24）──────────────────────────
print("\n── J. hex 工事記憶（Run 7）──")
wJ = fresh()
wJ["works"] = {}
for _u in wJ["units"].values():
    _u["flags"] = {}; _u["fortification"] = 0.0; _u["dig_hours"] = 0.0
dJ = wJ["units"]["BLU-2"]; dJ["pos"] = [11, 9]
nJ = dJ["personnel"]
for _ in range(8):
    dJ["flags"]["moved"] = False; ar.dig(wJ, "BLU-2")
check("師挖 8hr → 有頂蓋（與 Run 6 行為一致）", abs(dJ["fortification"] - 0.50) < 1e-9)
check("man-hours 累加至格子 = 人數 × 時數",
      abs(ar.hex_works(wJ, [11, 9]) - nJ * 8) < 1e-6, f"{ar.hex_works(wJ,[11,9]):,.0f}")

dJ["flags"]["moved"] = True; ar.abandon_works(dJ); ar.refresh_fortification(wJ)
check("★ 行軍中防護歸零（人不在洞裡）", dJ["fortification"] == 0.0)
check("★ 但格子上的洞仍在", abs(ar.hex_works(wJ, [11, 9]) - nJ * 8) < 1e-6)
dJ["flags"]["moved"] = False; ar.refresh_fortification(wJ)
check("★ 回到原格即完整恢復有頂蓋（Run 6 的痛點）",
      abs(dJ["fortification"] - 0.50) < 1e-9 and abs(dJ["dig_hours"] - 8.0) < 1e-6)

# 小單位挖的洞容不下大單位
wK = fresh(); wK["works"] = {}
for _u in wK["units"].values(): _u["flags"] = {}
engK, _ = ar.detach_bn(wK, "BLU-3", "eng", [7, 4])
eK = wK["units"][engK]
for _ in range(8):
    eK["flags"]["moved"] = False; ar.dig(wK, engK)
bigK = wK["units"]["BLU-1"]
pcK = ar.hex_works(wK, [7, 4]) / bigK["personnel"]
check("★ 工兵營 8hr 對其自身＝有頂蓋", abs(eK["fortification"] - 0.50) < 1e-9)
check("★ 同一批洞對一個師僅及淺掘（人數比 20:1）",
      ar.fort_from_hours(pcK) == 0.15, f"{pcK:.2f} hr/人")

# 砲擊摧毀工事，下限為淺掘
wL = fresh(); wL["works"] = {}
for _u in wL["units"].values(): _u["flags"] = {}
tL = wL["units"]["RED-2"]; tL["pos"] = [14, 9]
for _ in range(8):
    tL["flags"]["moved"] = False; ar.dig(wL, "RED-2")
wL["units"]["BLU-2"]["pos"] = [11, 9]; wL["units"]["BLU-1"]["pos"] = [11, 9]
before = ar.hex_works(wL, [14, 9])
for _u in wL["units"].values(): _u["flags"] = {}
ar.bombard(wL, ["BLU-2", "BLU-1"], "RED-2"); tL.pop("_inc", None)
check("★ 砲擊摧毀該格 man-hours", ar.hex_works(wL, [14, 9]) < before,
      f"{before:,.0f} → {ar.hex_works(wL,[14,9]):,.0f}")
for _ in range(20):
    for _u in wL["units"].values(): _u["flags"] = {}
    ar.bombard(wL, ["BLU-2", "BLU-1"], "RED-2"); tL.pop("_inc", None)
ar.refresh_fortification(wL)
check("★ 摧毀下限為淺掘（彈坑即掩體）",
      abs(tL["dig_hours"] - 0.5) < 0.01 and tL["fortification"] == 0.15,
      f"{tL['dig_hours']:.2f} hr/人")

# ── K. Run 7：彈藥實數化與火力任務（缺陷 4、5）─────────────────
print("\n── K. 彈藥實數化與火力任務（Run 7）──")
wK2 = fresh()
for _u in wK2["units"].values(): _u["flags"] = {}
shK, tgK = "BLU-1", "RED-2"
wK2["units"][shK]["pos"] = [11, 9]; wK2["units"][tgK]["pos"] = [13, 9]
fK, tK = wK2["units"][shK], wK2["units"][tgK]
check("基數取自 forces_v1（105mm 5800、155mm 1400）",
      fK["ammo"] == {"105": 5800, "155": 1400}, str(fK["ammo"]))
a0 = dict(fK["ammo"])
# Run 4 固定資料是戰損後的狀態，火砲非滿編 → 發數依實際門數計算，不可寫死 900
_mixK = ar.GUN_MIX[fK["type"]]
_scaleK = fK["equip"]["guns"] / sum(_mixK.values())
_wantK = _mixK["105"] * _scaleK * ar.FIRE_MINUTES * ar.GUN_SPEC["105"][0]
ar.bombard(wK2, [shK], tgK); tK.pop("_inc", None)
check("★ 射擊會扣實際發數（依實際門數）",
      abs(fK["ammo"]["105"] - (a0["105"] - _wantK)) < 1,
      f"{a0['105']} → {fK['ammo']['105']:.0f}（預期扣 {_wantK:.0f}，砲 {fK['equip']['guns']} 門）")
for _ in range(10):
    for _u in wK2["units"].values(): _u["flags"] = {}
    ar.bombard(wK2, [shK], tgK); tK.pop("_inc", None)
check("★ 彈藥會打完（一個基數約一個 tick 的連續射擊）", fK["ammo"]["105"] == 0)
for _u in wK2["units"].values(): _u["flags"] = {}
cas, _tk, _gk, msg = ar.bombard(wK2, [shK], tgK)
check("★ 打光後不再有效果", cas == 0 and "彈藥耗盡" in msg, msg[:40])
ar.resupply(wK2)
check("★ 補給交付基數 40%", abs(fK["ammo"]["105"] - 5800 * 0.4) < 1,
      f"{fK['ammo']['105']:.0f}")

# 抽離營的彈藥守恆
wK3 = fresh()
for _u in wK3["units"].values(): _u["flags"] = {}
pK = wK3["units"]["BLU-AD"]; ar.ensure_ammo(pK)
before, gbefore = pK["ammo"]["SP105"], pK["equip"]["guns"]
uidK, detK = ar.detach_bn(wK3, "BLU-AD", "sp1", [10, 9])
gdet = detK["equip"]["guns"]
check("★ 抽離營彈藥總量守恆",
      abs(detK["ammo"]["SP105"] + pK["ammo"]["SP105"] - before) < 1,
      f"{before:.0f} → 營 {detK['ammo']['SP105']:.0f} + 母 {pK['ammo']['SP105']:.0f}")
check("★ 抽離營彈藥依火砲比例分割",
      abs(detK["ammo"]["SP105"] - before * gdet / max(gbefore, 1)) < 2,
      f"砲 {gdet}/{gbefore} → 彈 {detK['ammo']['SP105']:.0f}/{before:.0f}")

# 三種火力任務各有獨占優勢
res = {}
for mK in ("急襲", "壓制", "干擾"):
    w = fresh()
    for _u in w["units"].values(): _u["flags"] = {}
    w["units"][shK]["pos"] = [11, 9]; w["units"][tgK]["pos"] = [13, 9]
    b0 = dict(w["units"][shK]["ammo"])
    c, _t, _g, _m = ar.bombard(w, [shK], tgK, mission=mK)
    used = sum(b0[g] - w["units"][shK]["ammo"][g] for g in b0)
    res[mK] = (c, used, c / max(used, 1) * 1000, w["units"][tgK]["flags"].get("interdicted"))
check("★ 急襲效率最高（傷亡/千發）",
      res["急襲"][2] > res["壓制"][2] > res["干擾"][2],
      " ".join(f"{k}{v[2]:.0f}" for k, v in res.items()))
check("★ 壓制絕對傷亡最高", res["壓制"][0] > res["急襲"][0] > res["干擾"][0],
      " ".join(f"{k}{v[0]}" for k, v in res.items()))
check("★ 只有干擾凍結目標土工作業",
      res["干擾"][3] and not res["壓制"][3] and not res["急襲"][3])
wF = fresh()
for _u in wF["units"].values(): _u["flags"] = {}
wF["units"][shK]["pos"] = [11, 9]; wF["units"][tgK]["pos"] = [13, 9]
ar.bombard(wF, [shK], tgK, mission="干擾"); wF["units"][tgK].pop("_inc", None)
check("★ 遭干擾者不得構築工事", ar.dig(wF, tgK) is None)

# ── L. 規格書與引擎不得漂移（rules/arbiter_v2.md §XII）──────────
print("\n── L. 規格書與引擎的一致性 ──")
_spec = (Path(__file__).resolve().parent.parent / "rules" / "arbiter_v2.md").read_text()
def inspec(label, *needles):
    check(f"規格書載明 {label}", all(n in _spec for n in needles),
          " / ".join(n for n in needles if n not in _spec) or "ok")

# 工事分級：四級的暴露值必須逐字出現
inspec("工事四級暴露值", *[str(tier[2]) for tier in ar.FORT_TIERS])
inspec("工事工時門檻", "0.5", "3.0", "8.0")
inspec("DIG_RATE 工兵 1.5", "1.50")
inspec("WORKS_DEMOLITION", str(ar.WORKS_DEMOLITION))
inspec("MELEE_WORKS_MULT", str(ar.MELEE_WORKS_MULT))
inspec("CAMO_HOURS", str(ar.CAMO_HOURS))
inspec("AMMO_LOAD 四項基數", *[f"{v:,}" for v in ar.AMMO_LOAD.values()])
inspec("AMMO_RESUPPLY", "40%")
inspec("BLIND_FIRE_PENALTY", str(ar.BLIND_FIRE_PENALTY))
inspec("SATURATION", f"{ar.SATURATION:.0%}".replace("%", "%"))
inspec("COMBINED 協同倍率", "1.3", "1.5")
for _m, _v in ar.FIRE_MISSION.items():
    inspec(f"火力任務 {_m}", _m, str(_v[0]), str(_v[1]), str(_v[2]))
check("★ 規格書明載開放條款（不得以「規則沒寫」拒絕動作）",
      "不得以「規則沒寫」為由拒絕一個動作" in _spec)
check("★ 規格書明載裁判不得手寫單方內容",
      "不得手寫任何單方內容" in _spec)
# 被取代處都要有指回本檔的指標
for _f, _n in (("determinism_v1.md", 1), ("combat_v1.md", 3),
               ("logistics_v1.md", 1), ("combined_arms_v1.md", 1)):
    _t = (Path(__file__).resolve().parent.parent / "rules" / _f).read_text()
    check(f"{_f} 已加指回 arbiter_v2 的指標", _t.count("arbiter_v2.md") >= _n,
          f"{_t.count('arbiter_v2.md')} 處")

# ── M. 裁判程序與 tick 工具（TODO P6-14/15、P7-17）───────────────
print("\n── M. 裁判程序與 tick 工具 ──")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runs"))
import _audit, _tickkit as tk                                  # noqa: E402

# P6-15：battle 自行判定戰術狀態
wM = fresh()
for _u in wM["units"].values(): _u["flags"] = {}
aM, dM = "BLU-AD", "RED-AD"
wM["units"][dM]["pos"] = list(wM["units"][aM]["pos"])
m1, _ = ar.battle(wM, [aM], [dM], wM["units"][aM]["pos"])
cp_static = float(m1.split("攻方 CP ")[1].split("（")[0])
wM2 = fresh()
for _u in wM2["units"].values(): _u["flags"] = {}
wM2["units"][dM]["pos"] = list(wM2["units"][aM]["pos"])
wM2["units"][aM]["flags"]["moved"] = True
m2, _ = ar.battle(wM2, [aM], [dM], wM2["units"][aM]["pos"])
cp_march = float(m2.split("攻方 CP ")[1].split("（")[0])
check("★ P6-15 battle 依 flags[moved] 自行判定從行軍中接戰",
      abs(cp_march / cp_static - 0.7) < 0.02, f"{cp_static} → {cp_march}")
wM3 = fresh()
for _u in wM3["units"].values(): _u["flags"] = {}
wM3["units"][dM]["pos"] = list(wM3["units"][aM]["pos"])
m3, _ = ar.battle(wM3, [aM], [dM], wM3["units"][aM]["pos"], atk_from_march=True)
check("★ 裁判覆寫戰術狀態會在明細留痕", "裁判覆寫戰術狀態" in m3, m3[:40])

# P6-14：稽核必須擋下錯誤
for label, mut in (
    ("彈藥為負", lambda w: w["units"]["BLU-1"]["ammo"].__setitem__("105", -1)),
    ("移動中仍有工事", lambda w: (w["units"]["BLU-2"]["flags"].__setitem__("moved", True),
                              w["units"]["BLU-2"].__setitem__("fortification", 0.5))),
    ("同小時行軍又開火", lambda w: (w["units"]["BLU-3"]["flags"].__setitem__("moved", True),
                              w["units"]["BLU-3"]["flags"].__setitem__("fired", True))),
    ("org 超出範圍", lambda w: w["units"]["BLU-SF"].__setitem__("org", 150)),
):
    w = fresh()
    for _u in w["units"].values(): _u["flags"] = {}
    b = _audit.snapshot(w)
    mut(w)
    import io, contextlib
    _blocked = False
    with contextlib.redirect_stdout(io.StringIO()):
        try: _audit.require_clean(w, b)
        except AssertionError: _blocked = True
    check(f"★ P6-14 稽核擋下「{label}」", _blocked)

# P7-17：tickkit 的六個坑
wT = fresh()
for _u in wT["units"].values(): _u["flags"] = {}
wT["units"]["BLU-1"]["pos"] = [3, 4]
RT = {"BLU-1": [(1, 4), (2, 4), (3, 4), (4, 4), (5, 4)]}
iT = tk.init_route_index(wT, RT)
check("★ P7-17 坑#1 跨 tick 航路索引依現位置起算", iT["BLU-1"] == 3, str(iT))
wT["units"]["BLU-1"]["pos"] = [4, 4]
check("★ P7-17 坑#4 尾隨用被跟隨者的實際位置",
      list(tk.shadow_target(wT, "BLU-1", RT["BLU-1"], 2)) == [2, 4])
wR = fresh()
for _u in wR["units"].values(): _u["flags"] = {}
wR["units"]["BLU-2"]["pos"] = [1, 9]
rT = tk.Retreat(); rT.start(wR, "BLU-2", [-1, 9])
check("★ P7-17 後撤目的地夾進地圖範圍（避免永遠到不了）",
      rT.dest["BLU-2"] == [0, 9], str(rT.dest["BLU-2"]))
wN = fresh()
for _u in wN["units"].values(): _u["flags"] = {}
wN["units"]["BLU-1"]["pos"] = [11, 9]
wN["units"]["RED-AD"]["pos"] = [12, 9]; wN["units"]["RED-2"]["pos"] = [13, 9]
wN.setdefault("fog_of_war", {})["allies_spotted"] = ["RED-AD", "RED-2"]
check("★ P7-17 坑#6 友軍誤擊防護在挑選前排除該格（值 288 分的那個坑）",
      tk.nearest_target(wN, ["BLU-1"], "allies") == "RED-AD"
      and tk.nearest_target(wN, ["BLU-1"], "allies", exclude_pos=[12, 9]) == "RED-2")

# ── N. 友軍誤擊（TODO P6-16）────────────────────────────────────
print("\n── N. 友軍誤擊 ──")
wN2 = fresh()
for _u in wN2["units"].values(): _u["flags"] = {}
wN2["units"]["BLU-AD"]["pos"] = [12, 9]      # 我方，與敵同格（近戰中）
wN2["units"]["RED-AD"]["pos"] = [12, 9]
wN2["units"]["BLU-1"]["pos"] = [11, 9]       # 我方砲兵
wN2.setdefault("fog_of_war", {})["allies_spotted"] = ["RED-AD"]
a0N = wN2["units"]["BLU-AD"]["personnel"]
casN, tkN, gkN, msgN = ar.bombard(wN2, ["BLU-1"], "RED-AD")
wN2["units"]["RED-AD"].pop("_inc", None)
ffN = a0N - wN2["units"]["BLU-AD"]["personnel"]
check("★ P6-16 對含我方編隊之格射擊會造成友軍誤擊", ffN > 0, f"BLU-AD -{ffN} 人")
check("★ 友軍誤擊在明細中標示", "友軍誤擊" in msgN, msgN[-60:])
check("★ 友傷計入 losses_self",
      (wN2["units"]["BLU-AD"].get("losses_self") or {}).get("personnel", 0) == ffN)
# 友傷用**受害編隊自己的防護**計算——挖了洞連自己的砲彈也擋得住。
# 故比例只有在雙方暴露相同時才等於 FRIENDLY_FIRE_SHARE。另建一個對照組驗證。
wN5 = fresh()
for _u in wN5["units"].values():
    _u["flags"] = {}; _u["fortification"] = 0.0; _u["dig_hours"] = 0.0
wN5["units"]["BLU-AD"]["pos"] = [12, 9]; wN5["units"]["RED-AD"]["pos"] = [12, 9]
wN5["units"]["BLU-1"]["pos"] = [11, 9]
wN5.setdefault("fog_of_war", {})["allies_spotted"] = ["RED-AD"]
wN5["units"]["BLU-AD"]["personnel"] = wN5["units"]["RED-AD"]["personnel"]
a5 = wN5["units"]["BLU-AD"]["personnel"]
c5, _t5, _g5, _m5 = ar.bombard(wN5, ["BLU-1"], "RED-AD")
wN5["units"]["RED-AD"].pop("_inc", None)
f5 = a5 - wN5["units"]["BLU-AD"]["personnel"]
check("★ 雙方暴露相同時，友傷＝敵方所受 × FRIENDLY_FIRE_SHARE",
      abs(f5 / max(c5, 1) - ar.FRIENDLY_FIRE_SHARE) < 0.12,
      f"我 {f5} / 敵 {c5} = {f5/max(c5,1):.2f}（期望 {ar.FRIENDLY_FIRE_SHARE}）")
check("★ 友傷依受害編隊自身防護計算（挖洞也擋自己的砲彈）",
      ffN / max(casN, 1) < f5 / max(c5, 1) - 0.1,
      f"有工事 {ffN/max(casN,1):.2f} vs 無工事 {f5/max(c5,1):.2f}")
check("★ 事實紀錄有友軍誤擊條目（法庭可查、不判 legality）",
      any(f.get("kind") == "友軍誤擊" and f.get("victim") == "BLU-AD"
          for f in wN2.get("record", [])))
# 友傷不得算成敵方戰功
wN3 = fresh()
for _u in wN3["units"].values(): _u["flags"] = {}
wN3["units"]["BLU-AD"]["pos"] = [12, 9]; wN3["units"]["RED-AD"]["pos"] = [12, 9]
wN3["units"]["BLU-1"]["pos"] = [11, 9]
wN3.setdefault("fog_of_war", {})["allies_spotted"] = ["RED-AD"]
for _u in wN3["units"].values(): _u["losses"] = {"personnel": 0, "tanks": 0, "guns": 0}
ar.bombard(wN3, ["BLU-1"], "RED-AD"); wN3["units"]["RED-AD"].pop("_inc", None)
scN = ar.score(wN3)
check("★ 友傷不計入敵方殲敵 credit（我自己炸死的人不是對手的戰功）",
      scN["axis"]["inflicted"]["personnel"] == 0,
      f"紅軍 credit {scN['axis']['inflicted']}")
# 沒有我方編隊同格時不得有友傷
wN4 = fresh()
for _u in wN4["units"].values(): _u["flags"] = {}
wN4["units"]["RED-AD"]["pos"] = [12, 9]; wN4["units"]["BLU-1"]["pos"] = [11, 9]
wN4["units"]["BLU-AD"]["pos"] = [8, 9]
wN4.setdefault("fog_of_war", {})["allies_spotted"] = ["RED-AD"]
_, _, _, msgN4 = ar.bombard(wN4, ["BLU-1"], "RED-AD")
check("★ 我方不在該格時無友傷", "友軍誤擊" not in msgN4)

print(f"\n{'全部通過' if not fails else f'{len(fails)} 項失敗: {fails}'}")
sys.exit(1 if fails else 0)
