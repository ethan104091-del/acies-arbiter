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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arbiter as ar                                          # noqa: E402

RUN4 = Path(__file__).resolve().parent / "runs" / "run4_openfield" / "final_state.json"
fails = []


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + extra) if extra else ''}")
    if not cond:
        fails.append(name)


def fresh():
    s = copy.deepcopy(json.load(open(RUN4)))
    s["record"] = []
    for u in s["units"].values():
        u["flags"] = {}
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

# 缺陷 13：移動即棄工事
h4 = fresh()
h4["global_hour"] = 10
w = h4["units"]["RED-3"]
w["flags"] = {}
ar.dig(h4, "RED-3", hours=3.0)
had = w["fortification"]
ar.advance(h4, "RED-3", [0, w["pos"][1]])
check("★ 缺陷 13：移動即棄工事",
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
check("移動即棄工事（洞帶不走）", u6["fortification"] == 0.0 and u6["dig_hours"] == 0.0)

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

print(f"\n{'全部通過' if not fails else f'{len(fails)} 項失敗: {fails}'}")
sys.exit(1 if fails else 0)
