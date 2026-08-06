"""樞衡 Arbiter — 純戰場 PvP 的裁判解算核心（Run 4 實戰版）。

沿用 mapcore / hourstate / orbat / command，額外提供 Run 4 現場建立的解算層：
  refresh_visibility / spot   確定性能見狀態與對稱偵察判定
  plan_path / advance         Dijkstra 移動（成本=1/速度、同成本取最貼近命令直線者）
  consume / resupply          資源消耗與補給走廊
  bombard                     砲擊解算（determinism_v1 §III 的可執行化）
  battle                      地面戰解算（combat_v1 §II/§III 的可執行化）
  fatigue_effects             疲勞 → 組織度上限／戰鬥效力／移動（movement_v1 §IV）
  push_log                    各方可觀察日誌（防上帝視角外洩）
  brief_md / god_md / ascii_map   雙方戰報與地圖

★ 本檔是 **Run 4 當時實際跑的版本**，原樣保留以確保該局可完整重播
   （runs/run4_openfield/ 有逐 tick 腳本與每個 tick 的起始快照）。

★★ 已知需要重做的部分——動手前先讀 `precedents.md`：
   1. bombard() 缺「命中／彈著覆蓋」環節：每發殺戰車係數 0.005 的原文限定詞是
      「彈著點 100m 內」，Run 4 卻套用在整個 2km 格 → 全場 128 輛戰車有 83 輛死於砲擊，
      且戰車對戰車直射交戰 0 次（穿甲表整局未使用）。見 precedents.md §三。
   2. density_factor() 把「目標多疏」與「多少落在彈著區內」揉成一個數，且只看兵力不看姿態。
      應拆成「彈著區覆蓋率（判例）× 暴露係數」。見 precedents.md §二。
   3. exposure_factor() 的森林 ×0.7 可能是反的（樹爆使無頂蓋部隊更慘）。見 precedents.md §E8。
   4. 【2026-08-04 已修】彈藥用百分比 → 永遠打不完。改為實數發數（AMMO_LOAD 取自
      forces_v1）：步兵師 105mm 5,800／155mm 1,400、裝甲師 SP105 6,500、特戰旅 81mm 3,500。
      bombard 逐砲種扣發數、打光即不能再打；resupply 每 tick 補基數 40%（走廊完整）。
      抽離營的彈藥依火砲比例自母編隊守恆分割。連帶使《戰爭法》W1 要件 B 得以成立。
   4-舊. 原記述：forces_v1 已給實數（步兵師 105mm 5,800 發、155mm 1,400 發；
      裝甲師 105mm SP 6,500 發），應改為按發數扣。見 prompts/referee_pvp.md。
   5. 【2026-08-04 已修】FIRE_MINUTES 固定 10 分鐘。改為 FIRE_MISSION 三類，
      每類各有一件別人做不到的事（純懲罰倍率會讓選項退化）：
        急襲 3min 彈0.4× 殺傷1.5×  → 效率最高，一個基數撐 16 小時
        壓制 10min 彈1.0× 殺傷1.0× → 絕對傷亡最高，6 小時見底
        干擾 30min 彈0.4× 殺傷0.3× → 最省彈，且**該小時凍結目標的土工作業與休整**
      干擾的價值在工事有 hex 記憶之後才成立：六小時干擾可把對方釘在無工事（暴露 0.70）
      而只花 37% 彈藥，等於把對方的挨打倍率放大近四倍。
   6. 經驗只進地面戰 CP，沒有進命中 → 特戰旅的 ⭐⭐⭐⭐⭐ 幾乎全局無作用。見 precedents.md §八。
   7. 【2026-07-30 已修】org 損失只實作了 Casualty_% × 1.5。已補齊 combat_v1 的六項：
      Suppression（連續戰鬥 6+hr 每小時 -2）／Surprise -10／Leadership（CP -20、團長 -5）／
      Friendly_Fire -10／Resupply +1/hr 恢復／Cover 工事衝擊減半。見 org_impact / org_recovery /
      refresh_combat_hours。影響：Run 4 的 RED-AD 推估會掉到 org 26，潰散門檻 25 在旁邊。
   8. 【2026-07-30 已修】strength 與實際傷亡脫鉤。改由「現員 ÷（現員＋累計戰損）」推導，
      在 hurt() 內重算，分母不含抽離故不失真。str_pct 參數保留但不再權威。
  10. 【2026-07-30 已修】hurt() 在**被打的一方**設 flags["fired"]=True——把「被打」記成
      「開火」。後果：①挨砲即 EXPOSED；②refresh_return_fire 讀該旗標，於是從未還擊的編隊
      會被記成有還擊，law_of_war.md W1 要件 B 永遠不成立。改為 flags["hit"]，
      並由 bombard/battle 自行標記真正的開火方。
  11. 【2026-07-30 誤判，已更正】原記為「行軍完全不累」——**錯的**。advance() 自 Run 4
      就有 `fatigue += 8 if 夜間 else 5`，正好對上 movement_v1 的行軍 5 ＋夜間 3。
      我只讀了 tick 腳本（那裡只有 consume）沒讀 advance 內部就下結論。
      真正存在的是後半：Run 4 的 tick 腳本讓**開火方每 hour 恢復疲勞 -3**，
      而開火屬輕戰鬥（+8）不是接戰待命（-3）。現在戰鬥疲勞由 resolve 經
      hurt(fatigue=fatigue_from_combat(tier)) 施加，管線只管行軍消耗與完全休整。
      ★ 並且我在修這條時一度在管線重複加行軍疲勞，使其加倍，已移除。
  13. 【2026-07-30 已修】移動不棄工事：手冊 §11 與裁示 38 都寫「移動或潰散即棄工事」，
      但只有 force_retreat 呼叫 abandon_works，advance 沒有 → 部隊可以帶著散兵壕行軍。
      已在 advance 內加上。
  14. 【2026-07-30 已修】run_tick 未呼叫 resupply（那是 tick 邊界函式）→ supply_status
      全為 None，而 org_recovery、潰散條件 C、signal_lost 都讀它。已在 tick 開頭呼叫。
   9. 【2026-07-30 已修】完全沒有編隊狀態機——無 status、無潰散、無投降，org 掉到 0 也只會
      站在原地繼續挨打。已補：evaluate_status / force_retreat / surrender_eligible /
      declare_surrender / accept_surrender / pursuit_factor（combat_v1 §III 的可執行化），
      以及事實紀錄層（record_engagement / record_fact / refresh_return_fire /
      combat_state_tag）。
      驗證：test_status_machine.py ＋ runs/run4_openfield 全 8 tick 重播，
      終局仍為 8813:1790。

★★ 引擎不判合法性。 引擎只記事實（誰在第幾小時對誰開火、誰做了什麼宣告），
   合法與否是戰後法庭的辯論，由裁判判決。條號、寬限期、可信度、明知門檻
   一律寫在 law_of_war.md 給法官用，**不得寫成程式裡的自動認定或自動制裁**。
   2026-07-30 曾一度把 W1/W2/W7 的認定與「全軍喪失受降請求權」的自動制裁
   寫進引擎，已全部移除——那是未經審判就執行處罰。

  24. 【2026-08-02 Run 7 改動】工事改為 **hex 記憶**：state["works"]["x,y"]["man_hours"]。
      挖掘累加「人數 × 時數 × 兵種速率」；某編隊的防護 = fort_from_hours(該格 man-hours
      ÷ 該編隊人數)——一個 550 人的營挖的坑容不下一個師。移動不再摧毀工事，洞留在格子上；
      自己回來或敵方佔領皆完整取用（Run 6 指揮官裁定不打折）。
      間接火力以 WORKS_DEMOLITION=22.6 man-hr/殺傷單位摧毀之，近戰以攻方戰力損失%
      × MELEE_WORKS_MULT=3.0 摧毀之；下限為佔用編隊之淺掘級（彈坑即掩體）。
      偽裝不給 hex 記憶——帆布是隨隊裝備。
  23. 【2026-08-02 已修】抽離的砲兵營一發也打不出去。bombard() 以
      GUN_MIX[unit.type] 取砲種，而 GUN_MIX 只有 infantry/armor/ranger 三項；
      抽離的砲兵營兵種為 "artillery" → 取到空字典 → 發數 0。但 detach_bn 已
      把火砲從母師扣走，形成「砲被扣光又打不出去」的雙重損失。
      修法：detach_bn 依營級備註推導 gun_mix 寫入該營，bombard/record_crater 優先採用。
      同一問題亦影響任何「抽離砲兵營前置射擊」的戰術，雙方同等受益。
  22. 【2026-08-02 新增，非缺陷】裁示 18：該小時行軍過的編隊不得實施砲擊。
      手冊未規定、引擎原本亦未限制，屬規則缺口。以 flags["moved"] 過濾 bombard 的
      射擊方；近戰／戰車對戰車（battle）不受限。本局至今零次交火，故無追溯問題。
  21. 【2026-08-02 新增，非缺陷】裁示 17：偽裝作業（camouflage）。Run 6 T5 由一方
      提出「用帆布與木棍偽裝」此一規則未涵蓋之動作。合法性早已明定於
      law_of_war.md:278（偽裝為合法戰爭詭計）。引擎端以既有機制實作：
      camouflage() 累計工時，達 CAMO_HOURS 後靜止時能見狀態好一級（沿用 ranger 的
      同一張轉換表，不新增係數）；移動即失效；開火當小時仍 EXPOSED。
      **無法實作「誤判為他種裝備」**——戰報由程式產生且報告真實身分，而裁判不得
      手寫單方內容。該部分記入 precedents.md 留待 Run 7。
  20. 【2026-07-31 已修】advance() 把「每小時一次」的兩件事寫成了「每次呼叫一次」：
      行軍疲勞 +5、以及移動速率累加進 move_progress。後果分兩層——
      (a) tick 腳本若一小時只呼叫一次，速度 >1.0 格/hr 的兵種（偵察營 1.5）被硬卡成
          1 格/hr（advance 走到給定目標就停），速度優勢消失；
      (b) 腳本若為此在同一小時內連續呼叫，疲勞與速率雙雙重複計算，反而超速。
      兩者皆改為以 flags["moved"] 判定「本小時第一次移動」才施加（該旗標每小時由
      clear_flags 清空）。修正後同一小時內可安全連續呼叫以走完多格。
  19. 【2026-07-30 已修】state 檔從未寫入 units[*].equip —— 一直靠 load() 的
      setdefault 補上。後果：任何直接讀 raw JSON 的程式（orbat.py 的編制檢視器）
      在 bn_equip 取 parent["equip"] 時 KeyError。已在 bn_equip 內自行解析，
      並讓 openfield_setup.py 直接把 equip 寫進 state。
  18. 【2026-07-30 已修，屬 tick 腳本的解讀層】航路點以「第一個尚未到達的點」為目標
      會使部隊在兩個航路點之間來回振盪（走到 B 後發現 A 未到達 → 走回 A）。
      Run 5 T5 的 BLU-SF 因此白走四小時、卡在開闊地。已改為逐編隊記住航路索引，只前進。
      任何以航路點下令的 tick 腳本都必須用索引式追蹤，不可用「第一個未到達」。
  16. 【2026-07-30 已修】orbat.detach 不動 equip → 抽離戰車營時母師的戰車沒扣掉，
      54 輛變成 108 輛，守恆破了。已加 detach_bn / rejoin_bn 成對處理。
  15. 【2026-07-30 已修】ensure_unit/load 對缺 equip 的抽離營套用 EQUIP[type]，
      使一個 870 人步兵營拿到整師的 54 戰車與 48 門砲（戰力錯、計分錯、還能開砲）。
      Run 4 是靠 tick 腳本逐次手動歸零繞過，但那同樣錯（抽離戰車營/砲兵營會裝備蒸發）。
      已改為 bn_equip()：裝備依 ORBAT 跟著擁有它的營走。
  12. 【2026-07-30 已修】orbat.detach 造出的棋子缺 flags/losses/static_hours/
      move_progress（只有 load() 會補）→ 中途抽離的營一移動就 KeyError。
      已加 ensure_unit()；任何在 tick 中新增單位的地方都必須呼叫它。

★ 每 hour 迴圈的呼叫順序（新增部分）：
   spot → …移動/砲擊/地面戰… → refresh_return_fire → evaluate_status → pow_upkeep
   （refresh_return_fire 必須在戰鬥後、evaluate_status 前，因為它讀 flags["fired"]）

★★★ 標示 [判例] 的常數不是規則書的，是裁判當場裁定的，須依 precedents.md 的制度處理：
   FIRE_MINUTES、SATURATION、density_factor 的四段值、森林 ×0.7、BASE_POWER 的 ranger 45、
   組織度損失的 ×150（此項其實源自 combat_v1，非裁判自訂）。
"""
import json, sys, math
from pathlib import Path

GAME = Path(__file__).resolve().parent
sys.path.insert(0, str(GAME))
import mapcore as mc, hourstate as hs, orbat, command          # noqa: E402

STATE = GAME / "maps" / "open_field_state.json"

# ── 裝備編制（本局定義，鏡像對稱）────────────────────────────────
EQUIP = {
    "infantry": {"tanks": 54, "guns": 48},     # 配屬戰車營54 + 105×36 + 155×12
    "armor":    {"tanks": 216, "guns": 54},    # 4戰車營×54 + 自走榴砲×54
    "ranger":   {"tanks": 0,  "guns": 12},     # 迫擊砲
}
SCORE_W = {"personnel": 1, "tanks": 20, "guns": 10}   # 殲敵計分權重

# ── 移動速率（hex/hour，movement_v1）───────────────────────────
RATE = {
    "infantry":  {".": 0.67, "F": 0.33},
    "armor":     {".": 1.00, "F": 0.00},       # 無路，戰車不進林
    "mech_inf":  {".": 0.83, "F": 0.50},
    "ranger":    {".": 1.00, "F": 0.50},
    "recon":     {".": 1.50, "F": 0.50},
    "artillery": {".": 0.83, "F": 0.00},
    "engineer":  {".": 0.83, "F": 0.50},
    "aa":        {".": 0.83, "F": 0.00},
    "hq":        {".": 0.83, "F": 0.33},
}
# 偵察視距（hex，白天/夜間）
SIGHT = {"div": (3, 2), "ranger": (4, 3), "recon": (5, 3)}
# 目標能見狀態 → 被發現所需最大距離
VIS_REQ = {"EXPOSED": None, "STANDARD": None, "CAMOUFLAGED": 2, "CONCEALED": 1, "HIDDEN": 0}

# ── 消耗（logistics_v1 §2，步兵師基準 %/hour）────────────────────
CONS = {
    "L0": {"POL": .3, "SA": .1, "HE": 0,  "AT": 0,  "RAT": .7, "MED": .1, "PARTS": .2},
    "L1": {"POL": 2., "SA": .2, "HE": 0,  "AT": 0,  "RAT": .7, "MED": .2, "PARTS": .5},
    "L2": {"POL": 1., "SA": .5, "HE": .3, "AT": .2, "RAT": .7, "MED": .5, "PARTS": .3},
    "L3": {"POL": 2.5, "SA": 2., "HE": 1.5, "AT": 1.5, "RAT": .9, "MED": 2., "PARTS": 1.},
    "L4": {"POL": 4., "SA": 4., "HE": 3.5, "AT": 4., "RAT": 1., "MED": 5., "PARTS": 2.},
}
MULT = {"armor": {"POL": 3.0, "AT": 2.5, "PARTS": 2.0, "HE": 1.5},
        "mech_inf": {"POL": 2.0}}


# ── 基本 I/O ─────────────────────────────────────────────────────
def load(path=STATE):
    s = json.loads(Path(path).read_text())
    hs.ensure_hour_fields(s)
    orbat.ensure_orbat(s)
    for uid, u in s["units"].items():
        if "equip" not in u:                      # 缺陷 15：抽離營依 ORBAT 決定裝備
            if u.get("is_detachment") and u.get("parent") in s["units"]:
                u["equip"] = bn_equip(s["units"][u["parent"]], u.get("bn_code"))
            else:
                u["equip"] = dict(EQUIP.get(u["type"], {"tanks": 0, "guns": 0}))
        u.setdefault("losses", {"personnel": 0, "tanks": 0, "guns": 0})
        u.setdefault("static_hours", 0)
        if u.get("side") in ("allies", "axis"):
            ensure_ammo(u)                        # Run 7：彈藥實數化
        u.setdefault("move_progress", 0.0)
        u.setdefault("flags", {})
    return s


def bn_equip(parent, code):
    """抽離營應攜行的裝備。

    缺陷 15（2026-07-30，我造成的）：ensure_unit / load 對缺 equip 的單位套用
    EQUIP[type]，於是一個 870 人的**步兵營**拿到了整個師的 54 戰車與 48 門砲
    ——不但戰力錯，被擊毀時還值 54×20+48×10=1,560 分，而且能用 48 門砲射擊。
    Run 4 是靠每個 tick 腳本手動把 equip 歸零繞過的，但那同樣是錯的：
    抽離**戰車營**或**砲兵營**時也會被歸零，等於裝備人間蒸發。

    正確做法是依 ORBAT 決定：裝備跟著擁有它的那個營走。
    """
    import re
    ob = parent.get("orbat", {})
    info = ob.get(code, {})
    # 缺陷 19：state 檔從未寫入 equip（一直靠 arbiter.load() 的 setdefault 補），
    # 所以任何直接讀 raw JSON 的消費者（orbat.py 的檢視器）都會 KeyError。
    # 此處自行解析，不假設母編隊已被正規化。
    peq = parent.get("equip") or dict(EQUIP.get(parent.get("type"),
                                                {"tanks": 0, "guns": 0}))
    typ, note = info.get("type"), info.get("note", "")
    m = re.search(r"×(\d+)", note)
    n = int(m.group(1)) if m else None
    if typ == "armor":
        if n:
            return {"tanks": n, "guns": 0}
        carriers = [k for k, v in ob.items() if v.get("type") == "armor"]
        return {"tanks": peq["tanks"] // max(1, len(carriers)), "guns": 0}
    if typ == "artillery" or "迫擊" in note:
        if n:
            return {"tanks": 0, "guns": n}
        carriers = [k for k, v in ob.items()
                    if v.get("type") == "artillery" or "迫擊" in v.get("note", "")]
        return {"tanks": 0, "guns": peq["guns"] // max(1, len(carriers))}
    # 步兵營、裝步營、偵察營、工兵營、防空營：不攜行計分用的戰車與野戰砲
    # （防空營的 40mm 不是 GUN_MIX 裡的 105/155 榴砲，不計入「火砲」）
    return {"tanks": 0, "guns": 0}


def bn_gun_mix(parent, code, guns):
    """自營級備註推導該營的砲種（缺陷 23）。回傳 {砲種: 門數}。

    備註中的口徑字樣即為權威：'M2A1 105mm×12' → 105、'M1 155mm×12' → 155、
    '自走榴砲×18' → 母師為裝甲師故為 SP105、'迫擊' → mortar81。
    推不出來時退回母師 GUN_MIX 中門數最多的那一種（保守且可驗算）。
    """
    note = parent.get("orbat", {}).get(code, {}).get("note", "")
    if "155" in note:
        return {"155": guns}
    if "自走" in note:
        return {"SP105": guns}
    if "105" in note:
        return {"105": guns}
    if "迫擊" in note:
        return {"mortar81": guns}
    pm = GUN_MIX.get(parent.get("type"), {})
    return {max(pm, key=pm.get): guns} if pm else {}


def detach_bn(s, div_uid, code, pos):
    """抽離一個營，並維持裝備守恆。回傳 (uid, 棋子)。

    orbat.detach 只搬人員與 strength，**不動 equip**。若抽離的是戰車營或砲兵營，
    不扣母師就等於把裝備複製一份（54 輛變 108 輛）。本函式補上兩件事：
      ① 依 bn_equip 決定該營攜行的裝備；② 從母師的 equip 等量扣除。
    歸建時由 rejoin_bn 精確還原。
    """
    parent = s["units"][div_uid]
    eq = bn_equip(parent, code)
    uid, det = orbat.detach(s, div_uid, code, pos)
    det["equip"] = dict(eq)
    # 缺陷 23：抽離的砲兵營兵種為 "artillery"，而 GUN_MIX 只有 infantry/armor/ranger，
    # 於是 bombard() 取到空字典、發數為零——54 門砲被扣出母師卻一發打不出去。
    # 此處自營級備註推導其砲種，寫入 det["gun_mix"]，由 bombard 優先採用。
    if eq.get("guns"):
        det["gun_mix"] = bn_gun_mix(parent, code, eq["guns"])
        # Run 7：彈藥與火砲同步守恆分割。母編隊等量扣除。
        pa = ensure_ammo(parent)
        # 此處尚未從母編隊扣除裝備（那在本函式尾端），故 parent.equip.guns 已是扣除前的值。
        # 早期版本在此又加了一次 eq["guns"]，造成分母重複計算、抽離營少拿彈藥。
        pg = max(1, parent["equip"]["guns"])
        pmax = parent.setdefault("ammo_max", dict(pa))
        det["ammo"], det["ammo_max"] = {}, {}
        for g in det["gun_mix"]:
            share = round(pa.get(g, 0) * eq["guns"] / pg, 1)
            smax = round(pmax.get(g, 0) * eq["guns"] / pg, 1)
            det["ammo"][g], det["ammo_max"][g] = share, smax
            pa[g] = round(max(0.0, pa.get(g, 0) - share), 1)
            pmax[g] = round(max(0.0, pmax.get(g, 0) - smax), 1)
    for k in ("tanks", "guns"):
        parent["equip"][k] = max(0, parent["equip"][k] - eq[k])
    ensure_unit(s, uid)
    det["supply_status"] = parent.get("supply_status")
    return uid, det


def rejoin_bn(s, det_uid):
    """營歸建：裝備加回母師（與 detach_bn 對稱，維持守恆）。回傳母師 uid。"""
    det = s["units"][det_uid]
    eq = dict(det.get("equip", {"tanks": 0, "guns": 0}))
    parent_uid = orbat.rejoin(s, det_uid)
    for k in ("tanks", "guns"):
        s["units"][parent_uid]["equip"][k] += eq.get(k, 0)
    return parent_uid


def ensure_unit(s, uid):
    """把中途生成的單位（例如 orbat.detach 拉出的營）補上引擎必需欄位。

    缺陷 12：orbat.detach 造出的棋子沒有 flags / losses / static_hours /
    move_progress，而這些只有 load() 會補 → 中途抽離的營一移動就 KeyError。
    任何在 tick 中新增單位的地方都必須呼叫本函式。
    """
    u = s["units"][uid]
    if "equip" not in u:
        if u.get("is_detachment") and u.get("parent") in s["units"]:
            u["equip"] = bn_equip(s["units"][u["parent"]], u.get("bn_code"))
        else:
            u["equip"] = dict(EQUIP.get(u.get("type"), {"tanks": 0, "guns": 0}))
    u.setdefault("losses", {"personnel": 0, "tanks": 0, "guns": 0})
    u.setdefault("static_hours", 0)
    u.setdefault("move_progress", 0.0)
    u.setdefault("flags", {})
    u.setdefault("fatigue", 0)
    u.setdefault("fortification", 0.0)
    u.setdefault("dig_hours", 0.0)
    u.setdefault("status", STATUS_ACTIVE)
    return u


def save(s, path=STATE):
    Path(path).write_text(json.dumps(s, ensure_ascii=False, indent=2))


def terr(s, pos):
    x, y = int(pos[0]), int(pos[1])
    row = s["map"]["terrain"][y]
    return row[x] if x < len(row) else "."


def dist(a, b):
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def is_night(s):
    return hs.daynight(s["global_hour"]) in ("夜間", "黎明")


def own(s, side):
    return {uid: u for uid, u in s["units"].items() if u.get("side") == side}


ENEMY = {"allies": "axis", "axis": "allies"}


# ── 能見狀態（確定性，對稱）──────────────────────────────────────
def refresh_visibility(s):
    """依 地形 + 是否移動/開火 + 靜止時數 決定能見狀態（recon_v1 §I 的可執行化）。"""
    for uid, u in s["units"].items():
        t = terr(s, u["pos"])
        moved = u["flags"].get("moved")
        fired = u["flags"].get("fired")
        if fired:
            v = "EXPOSED"
        elif moved:
            v = "CAMOUFLAGED" if t == "F" else "EXPOSED"
        else:
            if t == "F":
                v = "CONCEALED" if u["static_hours"] >= 2 else "CAMOUFLAGED"
            else:
                v = "STANDARD"
        BETTER = {"EXPOSED": "STANDARD", "STANDARD": "CAMOUFLAGED",
                  "CAMOUFLAGED": "CONCEALED", "CONCEALED": "CONCEALED"}
        if u["type"] == "ranger":      # 特戰滲透隱蔽：好一級
            v = BETTER[v]
        # 裁示 17：完成偽裝作業者靜止時好一級。開火當小時仍為 EXPOSED（槍口焰、揚塵），
        # 但偽裝物留存——故只在未開火時生效。
        if u.get("camouflaged") and not fired:
            v = BETTER[v]
        u["visibility_state"] = v
        u["hidden"] = v in ("CONCEALED", "HIDDEN")
    return s


def sight_of(u, night):
    k = "recon" if u["type"] == "recon" else ("ranger" if u["type"] == "ranger" else "div")
    return SIGHT[k][1 if night else 0]


def spot(s):
    """對稱偵察判定 → 重寫 fog_of_war。回傳 {side: 新偵獲uid列表}。"""
    night = is_night(s)
    newly = {}
    for side in ("allies", "axis"):
        obs = list(own(s, side).values())
        seen = []
        for uid, e in own(s, ENEMY[side]).items():
            req = VIS_REQ[e["visibility_state"]]
            for o in obs:
                d = dist(o["pos"], e["pos"])
                lim = sight_of(o, night) if req is None else min(req, sight_of(o, night))
                if d <= lim:
                    seen.append(uid)
                    break
        prev = set(s.get("fog_of_war", {}).get(f"{side}_spotted", []))
        newly[side] = sorted(set(seen) - prev)
        s.setdefault("fog_of_war", {})[f"{side}_spotted"] = sorted(seen)
        # 持續接觸時數（law_of_war.md §3.1 的「明知」門檻，逐方分別計）
        for uid, e in own(s, ENEMY[side]).items():
            ch = e.setdefault("contact_hours", {})
            ch[side] = ch.get(side, 0) + 1 if uid in seen else 0
        # 指揮所偵獲：敵單位靠近 2 格(夜1)內才看得出指揮所徵候；一經發現永久記錄
        cps = set(s["fog_of_war"].get(f"{side}_spotted_cps", []))
        for kind, pos in command.cp_hexes(s, ENEMY[side]).items():
            lim = 1 if night else 2
            if any(dist(o["pos"], pos) <= lim for o in obs):
                cps.add(f"{kind}@{pos[0]},{pos[1]}")
        s["fog_of_war"][f"{side}_spotted_cps"] = sorted(cps)
    s["fog_of_war"]["_note"] = "由 of.spot 每 hour 重算（對稱、確定性）"
    return newly


# ── 移動 ────────────────────────────────────────────────────────
def move_rate(s, u, dest_t):
    r = RATE.get(u["type"], RATE["infantry"]).get(dest_t, 0.0)
    f = u.get("fatigue", 0)
    r *= 0.9 if 40 <= f < 60 else 0.8 if 60 <= f < 80 else 0.7 if f >= 80 else 1.0
    pol = u.get("resources", {}).get("POL", 100)
    if pol < 10:
        r = 0.0
    elif pol < 20:
        r *= 0.5
    if is_night(s):
        r *= 0.5
    # precedents §三 T3：前一小時遭砲擊 → 本小時機動受阻（就地臥倒、疏散、後送）
    _sup = (SUPPRESS_MOVE_MULT
            if u.get("suppressed_gh") == s.get("global_hour", 0) - 1 else 1.0)
    return (r) * _sup


def step_toward(a, b):
    dx = (b[0] > a[0]) - (b[0] < a[0])
    dy = (b[1] > a[1]) - (b[1] < a[1])
    return [a[0] + dx, a[1] + dy]


def _passable(u, t):
    """該編隊能否通行此地形。

    裁示 38（Run 5）：**師級編隊的路徑不得穿越森林**——其建制內的戰車營與牽引
    火砲在無路森林是不可通行的（RATE 的 armor/artillery 於 F 為 0）。抽離的營級
    單位、特戰、偵察不受此限，照各自速率入林。
    """
    if t == "F" and not u.get("is_detachment") and u["type"] in ("infantry", "armor", "mech_inf"):
        return False
    return RATE.get(u["type"], RATE["infantry"]).get(t, 0.0) > 0


def plan_path(s, uid, target):
    """Dijkstra 最短路徑（成本 = 1/該兵種在該地形的速度；不可通行 = 不可走）。

    目標不可達（例如戰車的目標在森林）→ 自動改走「離目標最近的可達格」。
    回傳 [下一步, ..., 終點]；已在終點回傳 []。裁判不再逐案手動繞路。
    """
    import heapq
    u = s["units"][uid]
    W, H = s["map"]["width"], s["map"]["height"]
    start = (int(u["pos"][0]), int(u["pos"][1]))
    goal = (int(target[0]), int(target[1]))
    if start == goal:
        return []
    if not _passable(u, terr(s, goal)):          # 目標本身不可通行 → 找最近可達替代格
        cands = [(dist(p, goal), p) for p in
                 [(x, y) for x in range(W) for y in range(H)
                  if _passable(u, terr(s, (x, y)))]]
        cands.sort()
        goal = cands[0][1] if cands else start
        if start == goal:
            return []
    pq = [(0.0, start, [])]
    seen = {}
    while pq:
        cost, cur, path = heapq.heappop(pq)
        if cur in seen and seen[cur] <= cost:
            continue
        seen[cur] = cost
        if cur == goal:
            return path
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = cur[0] + dx, cur[1] + dy
                if not (0 <= nx < W and 0 <= ny < H):
                    continue
                t = terr(s, (nx, ny))
                if not _passable(u, t):
                    continue
                step_cost = 1.0 / RATE.get(u["type"], RATE["infantry"])[t]
                # 同成本路徑的決勝：偏離「出發→目標」直線越遠，加越多微小懲罰。
                # 這讓部隊沿命令指定的軸線前進、不會為了繞森林而無意義蛇行（確定性、雙方同一套）。
                dxg, dyg = goal[0] - start[0], goal[1] - start[1]
                norm = (dxg * dxg + dyg * dyg) ** 0.5 or 1.0
                dev = abs(dxg * (ny - start[1]) - dyg * (nx - start[0])) / norm
                heapq.heappush(pq, (cost + step_cost + 0.02 * dev, (nx, ny), path + [(nx, ny)]))
    return []


def advance(s, uid, target, note=""):
    """把單位朝 target 推進 1 hour。回傳 (是否移動, 訊息)。避開不可通行地形。"""
    if not under_command(s, uid):            # 自行投降／解散 → 不接受命令
        return False, f"{uid} 不接受命令（{status_of(s['units'][uid])}）"
    u = s["units"][uid]
    if list(u["pos"]) == list(target):
        return False, f"{uid} 已在 {tuple(target)}"
    path = plan_path(s, uid, target)
    if not path:
        return False, f"{uid} 無可行路徑至 {tuple(target)}（地形阻擋）"
    nxt = list(path[0])
    t = terr(s, nxt)
    r = move_rate(s, u, t)
    if r <= 0:
        return False, f"{uid} 無法機動（油料/疲勞）"
    if not u["flags"].get("moved"):       # 缺陷 20：移動速率每小時只累加一次
        u["move_progress"] = u.get("move_progress", 0.0) + r
    moved = False
    while u["move_progress"] >= 1.0 and list(u["pos"]) != list(target):
        u["pos"] = nxt
        u["move_progress"] -= 1.0
        moved = True
        if list(u["pos"]) != list(target):
            path = plan_path(s, uid, target)
            if not path:
                break
            nxt = list(path[0])
    first_move_this_hour = not u["flags"].get("moved")
    u["flags"]["moved"] = True
    u["static_hours"] = 0
    abandon_works(u)                     # 行軍中的部隊不在洞裡；洞留在格子上（缺陷 24）
    if first_move_this_hour:             # 缺陷 20：行軍疲勞是「每小時 +5」，不是「每次呼叫 +5」。
        u["fatigue"] = min(100, u.get("fatigue", 0) + (8 if is_night(s) else 5))
    u["last_action"] = note or f"機動朝 {tuple(target)}"
    return moved, f"{uid} → {tuple(u['pos'])} (進度 {u['move_progress']:.2f}, {t})"


# ── 消耗 / 補給 ─────────────────────────────────────────────────
def consume(s, uid, level="L1"):
    u = s["units"][uid]
    m = MULT.get(u["type"], {})
    res = u.setdefault("resources", {})
    for k, v in CONS[level].items():
        res[k] = round(max(0.0, res.get(k, 100) - v * m.get(k, 1.0)), 2)
    return res


def resupply(s):
    """tick 邊界呼叫：依補給走廊狀態補給（混合車隊 22%；受威脅半量；切斷 0）。"""
    sup = mc.compute_supply(s)
    out = {}
    for uid, u in s["units"].items():
        if u.get("side") not in ("allies", "axis"):
            continue
        src = 0 if u["side"] == "allies" else s["map"]["width"] - 1
        ux, uy = u["pos"]
        step = -1 if src < ux else 1
        corridor = [(cx, uy) for cx in range(ux + step, src + step, step)] or [(ux, uy)]
        worst = "intact"
        for c in corridor:
            st = sup.get(c, "intact")
            if st == "cut":
                worst = "cut"
                break
            if st == "contested":
                worst = "contested"
        f = {"intact": 1.0, "contested": 0.5, "cut": 0.0}[worst]
        # Run 7：彈藥以**實數發數**補給，每 tick 基數的 AMMO_RESUPPLY（走廊完整）。
        # 連續射擊一個 tick 即見底，補給追不上——指揮官必須挑時機開火。
        ensure_ammo(u)
        amax = u.get("ammo_max", {})
        for g, cap in amax.items():
            got = cap * AMMO_RESUPPLY * f
            u["ammo"][g] = round(min(cap, u["ammo"].get(g, 0) + got), 1)
        res = u.setdefault("resources", {})
        for k, amt in (("POL", 22), ("SA", 22), ("HE", 22), ("AT", 22), ("RAT", 22),
                       ("MED", 10), ("PARTS", 10)):
            res[k] = round(min(100.0, res.get(k, 0) + amt * f), 2)
        u["supply_status"] = worst
        out[uid] = worst
    return out


def supply_status(s):
    sup = mc.compute_supply(s)
    out = {}
    for uid, u in s["units"].items():
        src = 0 if u["side"] == "allies" else s["map"]["width"] - 1
        ux, uy = u["pos"]
        step = -1 if src < ux else 1
        worst = "intact"
        for cx in range(ux + step, src + step, step):
            st = sup.get((cx, uy), "intact")
            if st == "cut":
                worst = "cut"
                break
            if st == "contested":
                worst = "contested"
        out[uid] = worst
    return out


# ── 傷害 / 計分 ─────────────────────────────────────────────────
def hurt(s, uid, personnel=0, tanks=0, guns=0, org=0, str_pct=0.0, fatigue=0, note="",
         self_inflicted=False):
    """就地套用損失。

    ★ self_inflicted=True（友軍誤擊）另計入 losses_self。
      score() 會從敵方的殲敵credit中扣除——我自己炸死的人不是對手的戰功。

    ★ str_pct 自 2026-07-30 起**不再權威**：strength 由人員殘存率重算（缺陷 8）。
      保留參數是為了舊腳本相容；FR_TABLE 的戰力% 已經透過人員傷亡反映，
      若再獨立扣 strength 會雙重計算。
    """
    u = s["units"][uid]
    personnel = min(personnel, u.get("personnel", 0))
    tanks = min(tanks, u["equip"]["tanks"])
    guns = min(guns, u["equip"]["guns"])
    u["personnel"] = u.get("personnel", 0) - personnel
    u["equip"]["tanks"] -= tanks
    u["equip"]["guns"] -= guns
    for k, v in (("personnel", personnel), ("tanks", tanks), ("guns", guns)):
        u["losses"][k] += v
        if self_inflicted:
            u.setdefault("losses_self", {"personnel": 0, "tanks": 0, "guns": 0})[k] += v
    if personnel:                                     # 潰散條件 2 需要 24 hour 傷亡窗
        u.setdefault("cas_log", []).append([s["global_hour"], personnel])
    if str_pct:
        u["strength"] = round(max(0.0, u.get("strength", 100) - str_pct), 2)
    if org:
        u["org"] = round(max(0.0, u.get("org", 100) - org), 2)
    if fatigue:
        u["fatigue"] = min(100, u.get("fatigue", 0) + fatigue)
    # 缺陷 10 修正（2026-07-30）：原本這裡設 flags["fired"]=True——把「被打」
    # 記成「開火」。後果有兩個：①挨砲的編隊被判定為 EXPOSED（開火才會暴露，
    # 挨砲不會）；②更嚴重，refresh_return_fire 讀這個旗標，於是一個從頭到尾
    # 沒還擊的編隊會被記成有還擊，law_of_war.md W1 要件 B 永遠不可能成立。
    u["flags"]["hit"] = True
    # 缺陷 8 修正：strength 改為由實際人員殘存率推導，不再是與傷亡脫鉤的獨立欄位。
    # 分母用「現員 + 累計戰損」，因此**不受抽離影響**（抽離減 personnel 但不記 losses）。
    est = u.get("personnel", 0) + u["losses"]["personnel"]
    if est:
        u["strength"] = round(100.0 * u["personnel"] / est, 2)
    if note:
        u["last_action"] = note
    return u


# ── 砲擊解算（determinism_v1 §III 的可執行化，雙方同一套）──────────
# 各編隊的火砲組成（門數依 equip["guns"] 等比縮放，戰損會反映）
GUN_MIX = {
    "infantry": {"105": 36, "155": 12},          # 3×105榴砲營(12門) + 1×155榴砲營
    "armor":    {"SP105": 54},                   # 3×自走砲營(18門)
    "ranger":   {"mortar81": 12},                # 輕支援分隊迫擊砲
}
GUN_SPEC = {   # (每分持續射速, 每發殺傷力人/發, 最大射程hex, 每發殺戰車係數)
    "105":      (2.5, 0.30, 4, 0.005),
    "155":      (1.5, 0.55, 5, 0.020),
    "SP105":    (2.5, 0.30, 5, 0.005),
    "mortar81": (4.0, 0.18, 1, 0.001),
}
# ── 彈藥（Run 7 起改為實數發數，非百分比）───────────────────────────
# 基數取自 rules/forces_v1.md 的開戰時彈藥表。一個基數約等於一個 tick 的連續射擊：
#   步兵師 105mm 5,800 發 ÷ (36 門 × 2.5 發/min × 10 min) = 6.4 次任務
#   裝甲師 SP105 6,500 發 ÷ (54 門 × 2.5 × 10)            = 4.8 次任務
AMMO_LOAD = {"105": 5800, "155": 1400, "SP105": 6500, "mortar81": 3500}
AMMO_RESUPPLY = 0.40      # 每 tick 補給基數的 40%（走廊完整）；受威脅半量、切斷為零
                          # 依 rules/logistics_v1.md「彈藥車隊 SA+HE+AT 共 40%／趟」

# 火力任務類型（Run 7 起，取代固定 10 分鐘）。
# 三種各有一件別人做不到的事——純懲罰的倍率會讓選項退化，故每種都有補償。
#   代號: (佔用分鐘, 彈量倍率, 每發殺傷倍率, 組織度衝擊倍率, 凍結對方土工作業, 說明)
#
# 彈量倍率是「相對標準任務（FIRE_MINUTES）的總彈量」，**不與佔用時長相乘**。
FIRE_MISSION = {
    "急襲": (3,  0.4, 1.5, 1.0, False,
             "火力急襲（TOT）：全部彈著同時落地，目標來不及進洞。每發殺傷最高、最省彈，"
             "但總量小。史實上 1944 年發展 TOT 正是為此。"),
    "壓制": (10, 1.0, 1.0, 1.0, False,
             "持續壓制：標準火力任務。絕對傷亡最高。"),
    "干擾": (30, 0.4, 0.3, 2.0, True,
             "干擾射擊：長時間低速率。目的不是殺人，是讓對方無法工作——"
             "該小時視為交火，對方不得構築工事、不得完全休整，且組織度衝擊加倍。"),
}
FIRE_MINUTES = 10        # [判例] 「集中砲擊」每 hour 每門砲的實際射擊分鐘數（其餘為修正/裝填/補彈）
SATURATION = 0.08        # [判例] 單一目標編隊每 hour 傷亡上限＝其兵力 8%（散布飽和、彈坑重疊）


# ── 彈著覆蓋率（缺陷 1、2 已修，2026-08-04）───────────────────────────
# precedents.md §二 判定舊 density_factor 有結構性錯誤：它用單一數字同時代表
# 「目標本身多疏」與「目標有多少落在彈著區內」，且依兵力給 0.12–0.30。
# §二 的幾何論證是 1–6%，舊值是它的 3–20 倍。
#
# 為何 0.12–0.30 一定錯：引擎的「每發殺傷力 0.30 × 暴露 0.70 = 0.21」，
# 恰好等於手冊 §8 的「開闊地散開步兵每發 0.21 人」。也就是說那 0.21 是
# **落在部隊之間的每一發**的殺傷力，而覆蓋率的唯一職責是把「發射的發數」
# 換算成「落在部隊之間的發數」——那是純幾何量，不該再帶任何殺傷力資訊。
#
# 校準錨點（WWII 野戰砲兵持續作戰統計）：**每 100–300 發造成 1 人傷亡**。
# 舊值下引擎是 1 人 / 21 發，高出史實 5–14 倍。
#
# 彈著區面積（precedents §二）：
# 火砲相對戰車的易損倍率（P5-13，2026-08-04）。原式為 ×0.5，方向是反的：
# 牽引火砲無裝甲，破片即可毀掉照準具、輪組、制退機；戰車需近失彈直接命中。
# 由有效殺傷半徑推導——對戰車約 5m（面積 78 m²）、對牽引火砲約 15m（700 m²）
# → 易損面積比 700/78 ≈ 9。
GUN_VS_TANK_VULN = 9.0
# 火砲的暴露亦不同於戰車：牽引火砲挖砲坑（gun pit）只能遮住下半，
# 且射擊時必須露出砲身。故其工事減免弱於戰車掩壕。
GUN_EXPOSURE = {"moved": 1.0, "none": 0.6, "shallow": 0.45, "dug": 0.30}
SUPPRESS_MOVE_MULT = 0.5   # 前一小時遭砲擊者本小時移動 ×0.5（precedents §三 T3）。
                           # 史實依據：遭砲擊的部隊就地臥倒、疏散、後送傷員、重整隊形，
                           # 該時段失去行軍節奏。這是砲兵在 1944 年的**主要**價值——
                           # 直接擊毀裝備的比例極低（諾曼第 ORS 調查），癱瘓機動才是。
IMPACT_KM2_STATIC = 0.08   # 靜止目標、觀測射擊：280×280m 等效
IMPACT_KM2_COLUMN = 0.25   # 行軍縱隊：沿路軸鋪開，500×500m 等效
# 戰車須用「彈著點 100m 內」（determinism_v1 §III 的原文限定詞，Run 4 把它吃掉了）。
# 彈著區向外膨脹 100m：280→480m（0.23 km²）、500→700m（0.49 km²）。
IMPACT_KM2_STATIC_TANK = 0.23
IMPACT_KM2_COLUMN_TANK = 0.49
# 各級編隊佔地（1944 部署密度，FM 100-5 與各師戰史）：
#   步兵師展開防禦 正面 5–10km／縱深 5km → 於一格內視為填滿 4 km²
#   步兵營 正面 800m／縱深 600m ≈ 0.5 km²；孤立的連級／偵察隊為求安全更疏散
UNIT_AREA_KM2 = ((10000, 4.00), (2000, 1.50), (600, 0.50), (0, 0.25))


def unit_area(u):
    p = u.get("personnel", 0)
    for lim, a in UNIT_AREA_KM2:
        if p >= lim:
            return a
    return UNIT_AREA_KM2[-1][1]


def impact_coverage(u, for_tanks=False):
    """彈著區對該編隊的覆蓋率＝彈著區面積 ÷ 編隊佔地面積。純幾何，無殺傷力資訊。

    行軍中的編隊擠在一條路軸上，彈著區可沿其鋪開 → 覆蓋率高（precedents §二 C1）。
    戰車另用「彈著點 100m 內」的膨脹面積（§三 T1 的原文限定詞）。
    """
    moving = u["flags"].get("moved")
    if for_tanks:
        area = IMPACT_KM2_COLUMN_TANK if moving else IMPACT_KM2_STATIC_TANK
    else:
        area = IMPACT_KM2_COLUMN if moving else IMPACT_KM2_STATIC
    return round(min(1.0, area / unit_area(u)), 4)


def density_factor(u):
    """★ 已棄用（缺陷 2）。保留為 impact_coverage 的別名，供舊腳本相容。"""
    return impact_coverage(u)


# ── 工事分級（[判例] 2026-07-30，Run 5 起生效）─────────────────────
# Run 4 是單一線性斜坡：每 hour +0.1875，2.7 hour 吃滿 0.5，暴露 0.70 → 0.10。
# 效果的**量級**保留不動（散兵坑對砲擊 5-10 倍防護，符合史實）；改的是**時間結構**：
# 真實土工作業是分階段的，而且**第一鏟土買到的防護最多**（遞減報酬），
# 所以暴露係數改為逐級查表，不再線性內插。這讓「你有多少時間」成為真變數：
# 半小時的淺掘就把暴露砍掉四成強，但完整掩體是 8 小時的重投資。
#
# 工時基準：淺掘＝單兵工兵鏟 15-30 分；散兵壕＝2-4 hr；有頂蓋掩體＝需木材與工兵，
# 史實上要一整個工作日以上。以下取各區間下限，對雙方對稱、且在 Run 5 開局前裁定。
FORT_TIERS = [
    # (累計工時 hr, fortification 值, 砲擊暴露係數, 名稱, 說明)
    (0.0, 0.00, 0.70, "無工事", "開闊地散開，無任何遮蔽"),
    (0.5, 0.15, 0.40, "淺掘",   "臥射掩體。擋破片，不擋近失彈；起身射擊時保護大減"),
    (3.0, 0.35, 0.18, "散兵壕", "標準散兵坑，可站立射擊，能承受一般彈幕"),
    (8.0, 0.50, 0.10, "有頂蓋", "完整掩體，可擋空爆與樹爆"),
]
FRIENDLY_FIRE_SHARE = 0.5  # 對含我方編隊之格射擊時，我方編隊承受同一波火力的比例。
                           # 砲彈不分敵我；砲兵知道大概位置會試圖偏開，但一格 ≈2km，
                           # 近戰中的雙方無法分離。0.5 是「試圖偏開但只能偏一半」。
WORKS_DEMOLITION = 22.6   # Run 7：每「殺傷單位」摧毀的 man-hours（校準見 precedents §十三）
MELEE_WORKS_MULT = 3.0    # 近戰對工事的摧毀＝攻方戰力損失% × 此倍率
CAMO_HOURS = 3.0        # 偽裝作業門檻（裁示 17，Run 6 T5 起）：達此工時 → 能見狀態好一級
FORT_COVER_TIER = 0.35   # [判例] combat_v1 的 Cover（org 衝擊減半）自「散兵壕」級起適用
FORT_TANK_TIER  = 0.35   # [判例] 戰車掩壕（暴露 0.05）需挖到散兵壕級；淺掘對戰車無用
DIG_RATE = {"infantry": 1.0, "armor": 1.0, "mech_inf": 1.0,
            "engineer": 1.5, "ranger": 0.67, "recon": 0.67, "artillery": 0.67}


def fort_tier(fort):
    """回傳該工事值所屬的級距 (工時, fort, 暴露, 名稱, 說明)。取不超過 fort 的最高級。"""
    best = FORT_TIERS[0]
    for tier in FORT_TIERS:
        if fort >= tier[1] - 1e-9:
            best = tier
    return best


def dig(s, uid, hours=1.0):
    """構築工事一小時（須明確下令、且該 hour 未移動——裁示 33：固守不等於挖工事）。

    回傳 (級名, fortification, 暴露係數)。工時依兵種速率累計：工兵 1.5×、
    步兵/裝甲 1.0×、特戰/偵察/砲兵 0.67×（人手少）。
    """
    u = s["units"][uid]
    if u["flags"].get("moved") or not under_command(s, uid):
        return None
    if u["flags"].get("interdicted"):
        # Run 7：遭干擾射擊者該小時不得構築工事。干擾射擊是 30 分鐘低速率的連續
        # 落彈，刻意鋪開使目標無法出洞作業；10 分鐘的集中壓制則留下 50 分鐘可工作。
        return None
    rate = DIG_RATE.get(u["type"], 1.0)
    # Run 7：累加 man-hours 至**格子**。人數 × 時數 × 兵種速率。
    add_works(s, u["pos"], u.get("personnel", 0) * hours * rate, u.get("side"))
    pc = hex_works(s, u["pos"]) / max(1, u.get("personnel", 1))
    u["dig_hours"] = round(pc, 3)
    u["fortification"] = fort_from_hours(pc)
    tier = fort_tier(u["fortification"])
    return tier[3], u["fortification"], tier[2]


def ammo_load(unit):
    """整編隊的彈藥基數 {砲種: 發數}，取自 AMMO_LOAD（rules/forces_v1.md 的開戰時數量）。

    抽離營不用此函式——其彈藥由 detach_bn 依火砲比例自母編隊守恆分割。
    基數是**編制存量**，不隨戰損火砲數縮減：砲被打掉了砲彈還在，
    只是能發射的管數變少，射速自然下降（bombard 已依 equip.guns 縮放）。
    """
    mix = GUN_MIX.get(unit.get("type"), {})
    return {g: AMMO_LOAD.get(g, 0) for g in mix}


def ensure_ammo(unit):
    """補上 ammo 欄位。整編隊給滿載；抽離營若無此欄位則依其 gun_mix 給滿（保守）。冪等。"""
    if "ammo" in unit:
        return unit["ammo"]
    mix = unit.get("gun_mix") or GUN_MIX.get(unit.get("type"), {})
    if not mix:
        return {}
    unit["ammo"] = {g: AMMO_LOAD.get(g, 0) for g in mix}
    unit.setdefault("ammo_max", dict(unit["ammo"]))
    return unit["ammo"]


def ammo_total(unit):
    return sum(unit.get("ammo", {}).values())


def works_key(pos):
    return f"{int(pos[0])},{int(pos[1])}"


def hex_works(s, pos):
    """該格已累積的 man-hours（Run 7：工事記在格子上，不記在單位上）。"""
    return s.setdefault("works", {}).get(works_key(pos), {}).get("man_hours", 0.0)


def add_works(s, pos, man_hours, side=None):
    w = s.setdefault("works", {}).setdefault(works_key(pos), {"man_hours": 0.0, "by": side})
    w["man_hours"] = max(0.0, w["man_hours"] + man_hours)
    if side and man_hours > 0:
        w["by"] = side
    return w["man_hours"]


def fort_from_hours(per_capita):
    """每人累計工時 → fortification 值。"""
    val = FORT_TIERS[0][1]
    for need, fv, _e, _n, _d in FORT_TIERS:
        if per_capita >= need - 1e-9:
            val = fv
    return val


def refresh_fortification(s):
    """每 hour 依所在格的 man-hours 重算各編隊的工事值。

    Run 7 的核心改動：工事屬於**格子**不屬於單位。
      · 該編隊的防護 = fort_from_hours(該格 man-hours ÷ 該編隊人數)
        ——一個 550 人的營挖出來的坑容不下一個 14,030 人的師，故必須除以人數。
      · 該小時移動過者防護為 0（行軍中的部隊不在洞裡）。
      · 離開後洞還在；自己回來、或敵方佔領，都完整取用（Run 6 指揮官裁定：不打折）。
    """
    for uid, u in s["units"].items():
        if u.get("side") not in ("allies", "axis"):
            continue
        if u["flags"].get("moved"):
            u["fortification"] = 0.0
            u["dig_hours"] = 0.0
            continue
        n = max(1, u.get("personnel", 1))
        pc = hex_works(s, u["pos"]) / n
        u["dig_hours"] = round(pc, 3)
        u["fortification"] = fort_from_hours(pc)
    return s


def damage_works(s, pos, man_hours, occupant=None):
    """砲擊／近戰摧毀該格工事。下限為佔用編隊的「淺掘」級——彈坑本身即掩體。"""
    if man_hours <= 0:
        return 0.0
    cur = hex_works(s, pos)
    floor = FORT_TIERS[1][0] * max(1, occupant.get("personnel", 1)) if occupant else 0.0
    new = max(floor, cur - man_hours)
    removed = cur - new
    if removed > 0:
        s.setdefault("works", {}).setdefault(works_key(pos), {"man_hours": 0.0})["man_hours"] = new
    return removed


def camouflage(s, uid, hours=1.0):
    """偽裝作業一小時（裁示 17）。須明確下令、且該 hour 未移動。

    達 CAMO_HOURS 工時後，該編隊靜止時的能見狀態**好一級**——沿用引擎既有的
    「特戰滲透隱蔽」轉換，不新增係數。工時速率與構築工事同表（DIG_RATE）。

    與構築工事**共用同一個工時池**：一小時只能擇一，由 tick 腳本依命令決定。
    移動即失效（abandon_works 一併清除）；開火當小時仍為 EXPOSED，但偽裝物本身留存。
    """
    u = s["units"][uid]
    if u["flags"].get("moved") or not under_command(s, uid):
        return None
    rate = DIG_RATE.get(u["type"], 1.0)
    u["camo_hours"] = round(u.get("camo_hours", 0.0) + hours * rate, 3)
    u["camouflaged"] = u["camo_hours"] >= CAMO_HOURS - 1e-9
    return u["camo_hours"], u["camouflaged"]


def abandon_works(u):
    """移動或潰散即離開工事。

    Run 7 起：**洞留在格子上**（見 refresh_fortification），此處只把該編隊當下的
    防護歸零——行軍中的部隊不在洞裡。回到該格即重新取用。
    偽裝則是隨隊裝備，帶得走也帶得壞，移動即真正歸零（Run 6 指揮官裁定：不給 hex 記憶）。
    """
    u["fortification"] = 0.0
    u["dig_hours"] = 0.0
    u["camo_hours"] = 0.0
    u["camouflaged"] = False


FOREST_NO_COVER = 1.3     # 缺陷 3（precedents §E8）：樹爆使**無頂蓋**部隊在林中更慘
FOREST_WITH_COVER = 0.5   # 有頂蓋則反過來：樹木遮蔽 + 頂蓋擋住樹爆


def exposure_factor(u, terrain="."):
    """砲擊暴露係數，依工事級距查表（遞減報酬，非線性內插）。

    ★ 缺陷 3 已修（2026-08-04）：森林原為一律 ×0.7，**方向是反的**。
    WWII 的樹爆（tree burst）在林中引信提前起爆，破片由上而下灑進散兵坑——
    無頂蓋部隊在林中挨砲**比在開闊地更慘**，這正是當時準則規定「進林必挖有頂蓋掩體」的原因。
    依 precedents.md §E8 拆兩段：
      · 未達有頂蓋級 → ×1.3（樹爆）
      · 已達有頂蓋級 → ×0.5（樹木遮蔽 + 頂蓋擋住樹爆）

    副作用是森林變成一個真正的取捨：它藏得住你（CAMOUFLAGED／CONCEALED），
    但被找到並砲擊時，沒挖頂蓋反而更慘。

    ★開火不影響此係數——工事是實體掩體，EXPOSED 只影響「是否被偵獲」（裁示 36）。
    """
    fort = u.get("fortification", 0.0)
    e = fort_tier(fort)[2]
    if terrain == "F":
        e *= FOREST_WITH_COVER if fort >= FORT_TIERS[-1][1] - 1e-9 else FOREST_NO_COVER
    return round(e, 3)


def bombard(s, firing_uids, target_uid, minutes=None, mission="壓制"):
    """回傳 (人員傷亡, 戰車損失, 火砲損失, 明細字串)。多編隊集中射擊時效果相加、受飽和上限。

    Run 7：彈藥為**實數發數**（unit["ammo"][砲種]），打完就不能再打。
    火力任務類型（FIRE_MISSION）決定時長、彈量倍率與效果倍率——指揮官以彈藥換效果。
    預設「壓制」= 10 分鐘、彈量 1.0×、效果 1.0×，與 Run 6 行為完全一致。
    """
    mmin, ammo_mult, eff_mult, org_mult, freeze, _desc = \
        FIRE_MISSION.get(mission, FIRE_MISSION["壓制"])
    if minutes is None:
        minutes = mmin
    firing_uids = [u for u in firing_uids if under_command(s, u)]
    # 裁示 18：該小時行軍過的編隊不得實施砲擊。1944 年一次師屬集中射擊需佔領陣地、
    # 測地標定、開設觀測所與通信——一小時內無法既走完行軍又打完火力任務。
    # 近戰與戰車對戰車交戰（battle）不受此限：那本來就是機動接觸的產物。
    moved_out = [u for u in firing_uids if s["units"][u]["flags"].get("moved")]
    firing_uids = [u for u in firing_uids if not s["units"][u]["flags"].get("moved")]
    if not firing_uids:
        why = ("（本小時行軍中，無法實施砲擊：" + "、".join(moved_out) + "）") if moved_out \
            else "（無可受命之砲兵）"
        return 0, 0, 0, why
    tgt = s["units"][target_uid]
    for fu in firing_uids:                       # 開火者自己暴露（缺陷 10 相關）
        s["units"][fu]["flags"]["fired"] = True
    record_engagement(s, firing_uids, target_uid, kind="砲擊")   # 只記事實，不判罪
    record_crater(s, firing_uids, target_uid)                    # 裁示 25：落彈分析
    detail, rounds_by = [], {}
    for fu in firing_uids:
        f = s["units"].get(fu)
        if not f:
            continue
        d = dist(f["pos"], tgt["pos"])
        mix = f.get("gun_mix") or GUN_MIX.get(f["type"], {})   # 缺陷 23
        total_nominal = sum(mix.values()) or 1
        scale = f["equip"]["guns"] / total_nominal          # 戰損後的實際門數比例
        for gtype, n in mix.items():
            rate, leth, rng, tk = GUN_SPEC[gtype]
            if d > rng:
                continue
            guns = n * scale
            # 彈量倍率是「相對標準任務（FIRE_MINUTES）的總彈量」，不與時長相乘——
            # 時長只描述該任務佔用多久，不決定發數。兩者相乘會雙重計算。
            want = guns * FIRE_MINUTES * rate * ammo_mult
            # Run 7：受彈藥存量限制。打不滿就只打得出存量那麼多。
            store = ensure_ammo(f)
            avail = store.get(gtype, 0)
            r = min(want, avail)
            store[gtype] = round(max(0.0, avail - r), 1)
            if r <= 0:
                detail.append(f"{fu} {gtype} 彈藥耗盡（0 發）")
                continue
            lf = leth * (0.5 if d > 0.8 * rng else 1.0)      # 逼近最大射程 → 散布增大 ×0.5
            lf *= eff_mult                                    # 火力任務效果倍率
            # 缺陷 6 已修（2026-08-04）：經驗進命中。precedents §八 明定經驗有兩個
            # **互不重疊**的入口——CP 乘數用於地面戰（該公式無「發數」），
            # 命中率用於所有計算發數的射擊。原本經驗只進前者，
            # 使特戰旅的 ⭐⭐⭐⭐⭐ 幾乎全局無作用。
            lf *= VET.get(f.get("xp", 3), 1.0)
            rounds_by[gtype] = rounds_by.get(gtype, 0) + r
            short = "（存量不足）" if r < want - 0.5 else ""
            detail.append(f"{fu} {gtype}×{guns:.0f} 距{d} 發數{r:.0f}{short} "
                          f"殺傷力{round(lf, 4)} 餘彈{store[gtype]:.0f}")
            tgt.setdefault("_inc", [0.0, 0.0])
            tgt["_inc"][0] += r * lf
            tgt["_inc"][1] += r * tk
    if "_inc" not in tgt:
        dry = [u for u in firing_uids if not any(ensure_ammo(s["units"][u]).values())]
        return 0, 0, 0, ("（彈藥耗盡：" + "、".join(dry) + "）") if dry else "（無砲兵在射程內）"
    # ── 友軍誤擊（TODO P6-16）：目標格內的我方編隊承受同一波火力 ──────
    _side = s["units"][firing_uids[0]]["side"]
    _ff = [uid for uid, u in s["units"].items()
           if u.get("side") == _side and list(u["pos"]) == list(tgt["pos"])
           and uid not in firing_uids]
    # precedents §三 T3：砲擊對目標的壓制——下一小時機動受阻。
    tgt["suppressed_gh"] = s.get("global_hour", 0)
    if freeze:
        # 干擾射擊：目標該小時視為交火 → 不得構築工事、不得完全休整（管線依 flags 判定）
        tgt["flags"]["hit"] = True
        tgt["flags"]["interdicted"] = True
    tgt["_org_mult"] = org_mult          # 由呼叫方經 org_impact 取用
    # Run 7：間接火力摧毀該格工事（下限為佔用編隊的淺掘級——彈坑本身即掩體）
    _rm = damage_works(s, tgt["pos"], tgt["_inc"][0] * WORKS_DEMOLITION, tgt)
    ef, df = exposure_factor(tgt, terr(s, tgt["pos"])), impact_coverage(tgt)
    cas = tgt["_inc"][0] * ef * df
    cap = tgt.get("personnel", 0) * SATURATION
    capped = cas > cap
    cas = int(min(cas, cap))
    # Tank_Exposure（determinism_v1 §III 的分級化，雙方同一套）：
    #   移動/行軍中 1.0；靜止且未構工事（開闊地散開停放）0.3；已構工事/hull-down 0.05
    if tgt["flags"].get("moved"):
        texp = 1.0
    elif tgt.get("fortification", 0) >= FORT_TANK_TIER - 1e-9:
        texp = 0.05                      # 戰車掩壕：需挖到散兵壕級
    elif tgt.get("fortification", 0) > 0:
        texp = 0.15                      # 淺掘只夠遮車體下半，效果有限
    else:
        texp = 0.3
    ecap_t = max(1, int(tgt["equip"]["tanks"] * SATURATION))
    ecap_g = max(1, int(tgt["equip"]["guns"] * SATURATION))
    # 缺陷 1：戰車那條原本**完全沒有覆蓋率項**——determinism_v1 §III 的
    # 「0.005/發」限定詞是「彈著點 100m 內」，Run 4 把它套在整個 2km 格的編隊上。
    # 後果：Run 4 有 65% 的戰車損失死於砲擊，理性的裝甲師永遠不該前進，
    # 全局戰車對戰車直射交戰 0 次。
    tcov = impact_coverage(tgt, for_tanks=True)
    tank_kill = min(int(tgt["_inc"][1] * texp * tcov), tgt["equip"]["tanks"], ecap_t)
    # P5-13：火砲用自己的易損倍率與暴露表，不再沿用戰車的並乘 0.5（方向是反的）。
    gexp = (GUN_EXPOSURE["moved"] if tgt["flags"].get("moved") else
            GUN_EXPOSURE["dug"] if tgt.get("fortification", 0) >= FORT_TANK_TIER - 1e-9 else
            GUN_EXPOSURE["shallow"] if tgt.get("fortification", 0) > 0 else
            GUN_EXPOSURE["none"])
    gun_kill = min(int(tgt["_inc"][1] * gexp * tcov * GUN_VS_TANK_VULN),
                   tgt["equip"]["guns"], ecap_g)
    _inc0, _inc1 = tgt["_inc"][0], tgt["_inc"][1]   # 友軍誤擊要用，須在 del 之前取值
    del tgt["_inc"]
    if _ff:
        _fi = _inc0 * FRIENDLY_FIRE_SHARE
        _ft = _inc1 * FRIENDLY_FIRE_SHARE
        for _u in _ff:
            _v = s["units"][_u]
            _fef, _fdf = exposure_factor(_v, terr(s, _v["pos"])), impact_coverage(_v)
            _fcas = int(min(_fi * _fef * _fdf, _v.get("personnel", 0) * SATURATION))
            _ftexp = 1.0 if _v["flags"].get("moved") else (
                0.05 if _v.get("fortification", 0) >= FORT_TANK_TIER - 1e-9
                else 0.15 if _v.get("fortification", 0) > 0 else 0.3)
            _fk = int(round(min(_ft * _ftexp * impact_coverage(_v, for_tanks=True),
                               _v["equip"]["tanks"] + _v["equip"]["guns"])))
            _ftk = min(_fk, _v["equip"]["tanks"])
            _fgk = min(_fk - _ftk, _v["equip"]["guns"])
            if _fcas or _ftk or _fgk:
                _forg = org_impact(s, _u, 100.0 * _fcas / max(_v.get("personnel", 1), 1),
                                   friendly_fire=True)
                hurt(s, _u, personnel=_fcas, tanks=_ftk, guns=_fgk, org=_forg,
                     note="友軍誤擊", self_inflicted=True)
                record_fact(s, kind="友軍誤擊", actor_side=_side,
                            firing=list(firing_uids), victim=_u,
                            target=target_uid, hex=list(tgt["pos"]),
                            cas=_fcas, tanks=_ftk, guns=_fgk)
                detail.append(f"★友軍誤擊 {_u}：-{_fcas} 人"
                              + (f"、-{_ftk} 戰車" if _ftk else "")
                              + (f"、-{_fgk} 火砲" if _fgk else "")
                              + f"、組織 -{_forg}")
    msg = (f"[{mission}{minutes}min] 暴露{ef} 覆蓋{df} 戰車暴露{texp} 戰車覆蓋{tcov}"
           + (f" 工事-{_rm:,.0f}man-hr" if _rm > 0 else "")
           + f" → 傷亡 {cas} 人" + ("（觸飽和上限 8%）" if capped else "")
           + (f"、戰車 -{tank_kill}" if tank_kill else "") + (f"、火砲 -{gun_kill}" if gun_kill else "")
           + "｜" + "；".join(detail))
    return cas, min(tank_kill, tgt["equip"]["tanks"]), min(gun_kill, tgt["equip"]["guns"]), msg


BLIND_FIRE_PENALTY = 0.30   # [判例] 無觀測校射的攔阻／擾亂射擊，每發殺傷力 ×0.30


def bombard_hex(s, firing_uids, pos, minutes=None, mission="壓制"):
    """對**格面**射擊（攔阻／擾亂射擊）。不需偵獲目標。

    Run 6 新增。Run 5 的裁示 58 是「完全未偵獲者不得射擊」，因為引擎只能對
    「目標編隊」開火。後果是「打掉對方的眼睛」成為比打主力更有效率的策略——
    Run 5 紅軍 237 分全部來自這個機制。但史實上 1944 年的砲兵確實會對疑似位置
    實施攔阻與擾亂射擊，所以那是引擎缺陷而非規則意圖。

    代價（[判例]）：
      ① 無觀測校射 → 每發殺傷力 ×0.30。
      ② 該格若無敵方編隊 → 彈藥與暴露照付、效果為零。
      ③ 開火方一律標記 fired → 該小時 EXPOSED（暴露自己的位置）。

    回傳 (人員傷亡, 戰車損失, 火砲損失, 明細字串, 命中的目標 uid 或 None)。
    """
    firing_uids = [u for u in firing_uids if under_command(s, u)]
    # 裁示 18：該小時行軍過的編隊不得實施砲擊。1944 年一次師屬集中射擊需佔領陣地、
    # 測地標定、開設觀測所與通信——一小時內無法既走完行軍又打完火力任務。
    # 近戰與戰車對戰車交戰（battle）不受此限：那本來就是機動接觸的產物。
    moved_out = [u for u in firing_uids if s["units"][u]["flags"].get("moved")]
    firing_uids = [u for u in firing_uids if not s["units"][u]["flags"].get("moved")]
    if not firing_uids:
        why = ("（本小時行軍中，無法實施砲擊：" + "、".join(moved_out) + "）") if moved_out \
            else "（無可受命之砲兵）"
        return 0, 0, 0, why, None
    side = s["units"][firing_uids[0]]["side"]
    for fu in firing_uids:
        s["units"][fu]["flags"]["fired"] = True
    tgt = next((uid for uid, u in s["units"].items()
                if u.get("side") == ENEMY[side] and list(u["pos"]) == list(pos)
                and status_of(u) in COMBAT_STATUSES), None)
    record_fact(s, "攔阻射擊", actor_side=side, firing=list(firing_uids),
                target_hex=list(pos), hit=tgt)
    if tgt is None:
        return 0, 0, 0, f"對格面 {tuple(pos)} 實施攔阻射擊：該格無敵方編隊，彈藥與暴露照付", None
    cas, tk, gk, msg = bombard(s, firing_uids, tgt, minutes=minutes, mission=mission)
    cas = int(cas * BLIND_FIRE_PENALTY)
    tk = int(tk * BLIND_FIRE_PENALTY)
    gk = int(gk * BLIND_FIRE_PENALTY)
    return cas, tk, gk, (f"對格面 {tuple(pos)} 攔阻射擊（無觀測校射 ×{BLIND_FIRE_PENALTY}）"
                         f"命中 {tgt}：{msg}"), tgt


# ── 地面戰解算（combat_v1 §II/§III 的可執行化，雙方同一套）─────────
BASE_POWER = {"infantry": 100, "armor": 150, "ranger": 45}   # ranger 45 為 [判例]
VET = {1: 0.75, 2: 0.85, 3: 1.00, 4: 1.15, 5: 1.30}
ARM_OF_TYPE = {"infantry": {"步兵", "戰車", "砲兵"}, "armor": {"戰車", "裝步", "砲兵"},
               "ranger": {"特戰", "迫砲"}, "recon": {"偵察"}, "engineer": {"工兵"},
               "mech_inf": {"裝步"}, "artillery": {"砲兵"}, "aa": {"防空"}}
COMBINED = {1: 1.0, 2: 1.3, 3: 1.5}          # 4 種以上 → 1.7（本劇本上限）
FR_TABLE = [   # (上限, 攻方str%, 攻方org, 守方str%, 守方org, 守方後退格)
    (0.5, 4.0, 12, 0.5, 2, -1), (1.0, 3.0, 10, 1.0, 4, 0), (1.5, 2.0, 7, 2.0, 7, 0),
    (2.0, 1.5, 5, 3.5, 12, 1), (3.0, 1.0, 3, 6.0, 20, 2), (5.0, 0.5, 2, 10.0, 30, 2),
    (9e9, 0.5, 1, 15.0, 40, 3),
]


def base_power(u):
    if u.get("is_detachment"):
        return round(u.get("personnel", 0) / 1000 * 7.1, 1)      # 營級按人數等比
    return BASE_POWER.get(u["type"], 60)


# ── 組織度衝擊（combat_v1〈組織度衝擊計算〉完整實作）────────────────
# Run 4 只做了第一項（Casualty_% × 1.5），其餘六項全漏。org 是潰散(<25)與
# 投降(<15)的門檻，漏掉這些等於讓編隊永遠崩不掉——Run 4 最低 org 是 50.2。
SUPPRESS_AFTER_H = 6      # combat_v1：連續戰鬥 6+ hour
SUPPRESS_PER_H   = 2      # combat_v1：每小時 -2
SURPRISE_PEN     = 10     # combat_v1：被突襲方 -10
CP_DESTROYED_PEN = 20     # combat_v1：指揮所被毀 -20
REGT_CO_KIA_PEN  = 5      # combat_v1：團長陣亡 -5
FRIENDLY_FIRE_PEN = 10    # combat_v1：誤擊 -10
RESUPPLY_RECOVER = 1      # combat_v1：補給線完整 +1/hour 自然恢復
COVER_FACTOR     = 0.5    # combat_v1：在城鎮/工事 -50% 衝擊
COVER_TERRAIN    = ()     # 本劇本無城鎮地形（純戰場只有 . 與 F）；城戰劇本再加


def org_impact(s, uid, casualty_pct, surprised=False, friendly_fire=False):
    """回傳本 hour 應扣的組織度點數（只含衝擊，不含自然恢復）。

    casualty_pct 為本 hour 傷亡佔現有兵力的百分比（0-100）。

    [判例] 公式的套用順序：combat_v1 把 Cover 寫成「-50% 衝擊」而把 Resupply 寫成
    「+1/hour 自然恢復」。前者是乘法（作用於衝擊總和），後者是加法且**不應被 Cover
    減半**——恢復不是衝擊。因此：
        impact = (傷亡×1.5 + 壓制 + 突襲 + 指揮 + 誤擊) × (工事 ? 0.5 : 1)
    自然恢復另由 org_recovery() 每 hour 施加。
    """
    u = s["units"][uid]
    imp = casualty_pct * 1.5
    if u.get("combat_hours", 0) >= SUPPRESS_AFTER_H:
        imp += SUPPRESS_PER_H
    if surprised:
        imp += SURPRISE_PEN
    if friendly_fire:
        imp += FRIENDLY_FIRE_PEN
    imp += CP_DESTROYED_PEN * u.get("cp_destroyed_this_hour", 0)
    imp += REGT_CO_KIA_PEN * u.get("regt_co_kia_this_hour", 0)
    # combat_v1 的 Cover 是「在城鎮/工事」。純戰場地圖只有 '.' 與 'F'（森林），
    # 沒有城鎮；森林不是城鎮，且 precedents.md §E8 已質疑森林是否真的減傷
    # （樹爆對無頂蓋部隊更慘）。因此本劇本的 Cover 只認**工事**。
    # 城戰劇本啟用時再把城鎮地形字元加進 COVER_TERRAIN。
    in_cover = (u.get("fortification", 0) >= FORT_COVER_TIER - 1e-9
                or terr(s, u["pos"]) in COVER_TERRAIN)
    if in_cover:
        imp *= COVER_FACTOR
    _m = s["units"][uid].pop("_org_mult", 1.0)  # 干擾射擊的組織度衝擊倍率（Run 7）
    return round((round(imp, 2)) * _m, 2)


def org_recovery(s):
    """每 hour：補給線完整者組織度自然恢復 +1（combat_v1），受疲勞上限約束。"""
    for uid, u in s["units"].items():
        if u.get("side") not in ("allies", "axis"):
            continue
        if status_of(u) in (STATUS_SURRENDERED, STATUS_DISBANDED):
            continue
        if u.get("supply_status") != "intact":
            continue
        cap, _, _ = fatigue_effects(u)
        u["org"] = round(min(cap, u.get("org", 100) + RESUPPLY_RECOVER), 2)


def refresh_combat_hours(s):
    """每 hour：維護「連續戰鬥時數」（供 Suppression 用）。開火或被擊中皆計入。"""
    for u in s["units"].values():
        if u.get("side") not in ("allies", "axis"):
            continue
        if u["flags"].get("fired") or u["flags"].get("hit"):
            u["combat_hours"] = u.get("combat_hours", 0) + 1
        else:
            u["combat_hours"] = 0
        u.pop("cp_destroyed_this_hour", None)
        u.pop("regt_co_kia_this_hour", None)


def fatigue_effects(u):
    """movement_v1 §IV：疲勞 → (組織度上限, 戰鬥效力倍率, 移動倍率)。"""
    f = u.get("fatigue", 0)
    if f < 20:  return 100, 1.00, 1.00
    if f < 40:  return 95,  1.00, 1.00
    if f < 60:  return 90,  1.00, 0.90
    if f < 80:  return 85,  0.90, 0.80
    return 75, 0.80, 0.70


def apply_fatigue_caps(s):
    """把疲勞造成的組織度上限就地套用（每 hour 呼叫）。"""
    for u in s["units"].values():
        cap, _, _ = fatigue_effects(u)
        if u.get("org", 100) > cap:
            u["org"] = cap
    return s


def supply_factor(u):
    r = u.get("resources", {})
    vals = [r.get(k, 100) for k in ("POL", "SA", "HE", "AT", "RAT")]
    if min(vals) < 10:
        return 0.4
    if min(vals) < 30:
        return 0.7
    return 1.0


def arms_present(s, uids, pos):
    """該場戰鬥可投入的兵種種類（含相鄰 8 格內能支援的友軍）。"""
    arms = set()
    side = s["units"][uids[0]]["side"]
    for uid, u in own(s, side).items():
        if uid in uids or dist(u["pos"], pos) <= 1:
            arms |= ARM_OF_TYPE.get(u["type"], set())
    return arms


def unit_cp(s, uid, pos, is_attacker, spotted_by_enemy=True, sees_enemy=True,
            from_march=False, passive=False, arms_count=None):
    u = s["units"][uid]
    # 已投降（兩條路皆同）者不得主張抵抗：放下武器就不能再算防禦戰力。
    # 但手動示降者若被指揮官命令**主動攻擊**，攻方戰力照算——那正是詐降的內容。
    if status_of(u) == STATUS_SURRENDERED and not is_attacker:
        return 0.0
    t = terr(s, pos if is_attacker else u["pos"])
    cp = base_power(u)
    cp *= u.get("strength", 100) / 100
    cp *= u.get("org", 100) / 100
    cp *= supply_factor(u)
    cp *= VET.get(u.get("xp", 3), 1.0)
    cp *= fatigue_effects(u)[1]          # 疲勞 → 戰鬥效力（60-80 ×0.9、80+ ×0.8）
    if is_attacker:
        cp *= 0.7 if t == "F" else 1.0
    else:
        cp *= (1.5 if t == "F" else 1.0) + u.get("fortification", 0.0)
    if not is_attacker and not spotted_by_enemy:
        cp *= 2.0                       # 守方伏擊（攻方沒發現守方）
    if is_attacker and not sees_enemy:
        pass
    n = arms_count or 1
    cp *= COMBINED.get(n, 1.7)
    if from_march:
        cp *= 0.7
    if passive:
        cp *= 0.85
    return round(cp, 1)


def battle(s, atk_uids, def_uids, hexpos, atk_from_march=None, def_passive=True):
    """一個 hour 的地面戰。回傳 (明細字串, 守方應後退格數)。就地套用損失。

    **atk_from_march 預設 None＝由引擎自行判定**（裁示 32 + TODO P6-15）。
    判準為「攻方是否於該小時移動過」（flags["moved"]）——戰術狀態是該小時的姿態，
    不是整場交戰的持久標籤。

    仍可傳入明確的 True/False 覆寫，但覆寫會在明細字串中留下記錄，
    使裁判的任何裁量都出現在雙方看得到的日誌裡。Run 6 終局的教訓：
    裁判在看到計分後才發現此參數被誤用為持久標籤，而修正翻轉了勝負。
    """
    _auto = any(s["units"][u]["flags"].get("moved") for u in atk_uids if u in s["units"])
    _override = atk_from_march is not None and bool(atk_from_march) != _auto
    if atk_from_march is None:
        atk_from_march = _auto
    atk_uids = [u for u in atk_uids if under_command(s, u)]
    if not atk_uids:
        return "（無可受命之攻擊部隊）", 0
    for uid in atk_uids + list(def_uids):        # 地面戰雙方都在交火
        s["units"][uid]["flags"]["fired"] = True
    for duid in def_uids:                        # 只記事實，不判罪
        record_engagement(s, atk_uids, duid, kind="地面戰")
    a_arms = len(arms_present(s, atk_uids, hexpos))
    d_arms = len(arms_present(s, def_uids, hexpos))
    a_cp = sum(unit_cp(s, u, hexpos, True, from_march=atk_from_march, arms_count=a_arms) for u in atk_uids)
    d_cp = sum(unit_cp(s, u, hexpos, False, passive=def_passive, arms_count=d_arms) for u in def_uids)
    fr = a_cp / max(d_cp, 0.1)
    for cap, astr, aorg, dstr, dorg, push in FR_TABLE:
        if fr < cap:
            break
    lines = []
    if _override:
        lines.append(f"⚠️ 裁判覆寫戰術狀態：從行軍中接戰＝{atk_from_march}"
                     f"（引擎自動判定為 {_auto}）")
    lines += [f"攻方 CP {a_cp}（{a_arms} 兵種、協同 {COMBINED.get(a_arms,1.7)}）"
             f" vs 守方 CP {d_cp}（{d_arms} 兵種"
             + (f"、工事 +{s['units'][def_uids[0]].get('fortification',0):.3f}" if def_uids else "") + "）"
             f" → **兵力比 {fr:.2f}** → 對照表：攻方 -{astr}% 戰力/-{aorg} 組織、守方 -{dstr}% 戰力/-{dorg} 組織"]
    # Run 7：近戰亦摧毀工事，但量遠小於砲擊（爆破組、噴火器、手榴彈）
    _occ = s["units"][def_uids[0]] if def_uids else None
    _mrm = damage_works(s, hexpos, hex_works(s, hexpos) * astr / 100.0 * MELEE_WORKS_MULT, _occ)
    if _mrm > 0:
        lines.append(f"　近戰摧毀該格工事 -{_mrm:,.0f} man-hr")
    for uids, spct, org, is_def in ((atk_uids, astr, aorg, False), (def_uids, dstr, dorg, True)):
        for uid in uids:
            u = s["units"][uid]
            # combat_v1：追擊潰散部隊 ×3 傷亡。只乘人員（規則寫「×3 傷亡」），不乘裝備與戰力%。
            # 砲擊不套用此倍率——bombard 已透過「移動中暴露 1.0」反映縱列失去疏散。
            pm = pursuit_factor(s, uid) if is_def else 1.0
            cas = int(round(u.get("personnel", 0) * spct / 100 * pm))
            tk = int(round(u["equip"]["tanks"] * spct / 100))
            gk = int(round(u["equip"]["guns"] * spct / 100))
            hurt(s, uid, personnel=cas, tanks=tk, guns=gk, org=org, str_pct=spct,
                 fatigue=15, note="地面戰")
            lines.append(f"　{uid}：-{cas} 人"
                         + (f"、-{tk} 戰車" if tk else "") + (f"、-{gk} 火砲" if gk else "")
                         + f"、戰力 {u['strength']}%、組織 {u['org']}")
    return "；".join(lines), push


# ── 編隊狀態機（combat_v1 §III 潰散／投降的可執行化）─────────────────
# 缺陷 9 的修補：Run 4 版本完全沒有 status，一個編隊 org 掉到 0 也只會站在原地
# 繼續挨打——既不潰散、不強制後退、不解散、也不投降。本節實作 combat_v1.md
# 〈潰散(Rout)〉〈投降(Surrender)〉兩套**既有**規則，並依 law_of_war.md §1.W2.0
# 把投降拆成「資格（自動、可逆、無法律效果）／示降（宣告、不可逆）」兩段。
#
# 全部門檻數字取自 combat_v1.md，非裁判自訂；標 [判例] 者為規則書未給而必須裁定的。

ROUT_ORG       = 25     # combat_v1：Org < 25
ROUT_CAS_24H   = 0.30   # combat_v1：24 hour 內傷亡 > 30%
ROUT_RETREAT   = 2      # combat_v1：強制撤退 2-3 hex。[判例] 取確定值 2：
                        #   撤得少對潰散方不利（更易被追擊）、對追擊方有利，兩面都不偏。
PURSUIT_MULT   = 3.0    # combat_v1：撤退途中可被追擊，×3 傷亡
ROUT_RECOVER_H = 6      # combat_v1：6 hour 後補給恢復 + 整補 → Org 回到 30
ROUT_DISBAND_H = 12     # combat_v1：12 hour 未恢復 → 解散（殘部成為散兵）
SURR_ORG       = 15     # combat_v1：Org < 15
SURR_RAT       = 5.0    # combat_v1：食物 < 5%（且戰役 > 7 天，48 hour 劇本永不成立）
SURR_NOSUP_H   = 48     # combat_v1：連續 48 hour 無補給
POW_GUARD_RATIO = 0.05  # [判例] 看管兵力＝俘虜數 5%（1 名押解兵對 20 名俘虜，近史實押解比）

STATUS_ACTIVE, STATUS_ROUTED = "ACTIVE", "ROUTED"
STATUS_SURRENDERED, STATUS_DISBANDED = "SURRENDERED", "DISBANDED"
COMBAT_STATUSES = (STATUS_ACTIVE, STATUS_ROUTED)     # 仍具戰鬥／被攻擊資格

# 投降有兩條路（combat_v1 的字面讀法 ＋ 指揮官的決定）：
#   "auto"     org<15 且四條之一 → **部隊自行投降，指揮官失去該編隊控制權**。
#              它不再接受命令、不移動、不開火。因此不可能用它詐降——
#              沒有人能命令它開火，也就沒有可歸責的人。
#   "declared" 指揮官主動宣告示降，**該編隊仍在其控制之下**。
#              因此它仍可被命令開火——那就是詐降，而且必然出於指揮官的決定。
# 兩條路的共同點：不可逆，且**對手都可以選擇不受降**。
SURR_AUTO, SURR_DECLARED = "auto", "declared"


def surrender_kind(u):
    return u.get("surrender_kind")


def under_command(s, uid):
    """該編隊是否仍接受命令。自行投降者為 False——指揮官對它已無控制權。"""
    u = s["units"][uid]
    if status_of(u) == STATUS_DISBANDED:
        return False
    return not (status_of(u) == STATUS_SURRENDERED and surrender_kind(u) == SURR_AUTO)


def status_of(u):
    return u.get("status", STATUS_ACTIVE)


def _neighbors(s, pos):
    w, h = s["map"]["width"], s["map"]["height"]
    return [[pos[0] + dx, pos[1] + dy]
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if (dx, dy) != (0, 0)
            and 0 <= pos[0] + dx < w and 0 <= pos[1] + dy < h]


def encircled(s, uid):
    """四面包圍（無退路）：每個相鄰格都被敵方編隊佔據或本兵種不可通行。

    地圖邊緣不算退路（往圖外不是撤退）。與 combat_v1 的「退路被切斷」互為
    幾何判準與補給判準兩條路，任一成立即滿足潰散條件 3。
    """
    u = s["units"][uid]
    hostile = {tuple(v["pos"]) for v in own(s, ENEMY[u["side"]]).values()
               if status_of(v) in COMBAT_STATUSES}
    ns = _neighbors(s, u["pos"])
    if not ns:
        return True
    for n in ns:
        if tuple(n) in hostile:
            continue
        if not _passable(u, terr(s, n)):
            continue
        return False                     # 找到一條可走且無敵的相鄰格 → 未被包圍
    return True


def cas_24h(s, uid):
    """24 hour 內傷亡佔「該窗起始兵力」之比例（分母＝現兵力＋窗內傷亡）。

    用滑動窗自我正規化，因此不受抽離營影響——抽離會減少 personnel 但不記 losses，
    若拿建制當分母，抽離過的編隊會被誤判為高傷亡。
    """
    u = s["units"][uid]
    gh = s["global_hour"]
    win = sum(n for g, n in u.get("cas_log", []) if gh - g < 24)
    base = u.get("personnel", 0) + win
    return (win / base) if base else 0.0


def surrender_eligible(s, uid):
    """combat_v1〈投降觸發條件〉：Org < 15 且四條之一。回傳 (bool, 事由列表)。

    ★ 這**不是**能不能示降的門檻——任何編隊隨時都可以宣告示降（現實裡隨時能舉白旗，
      史實上的詐降本來就常出自仍有戰力的部隊）。本函式給的是**可信度**：
      條件成立 → 該示降可信，對手繼續攻擊構成 W2；
      條件不成立 → 對手「合理不信任」，繼續攻擊合法（law_of_war.md §1.W2.0）。
      信或不信是對手的決定，不是規則書的決定。
    """
    if status_of(s["units"][uid]) not in COMBAT_STATUSES:
        return False, []
    return surrender_conditions(s, uid)


def surrender_conditions(s, uid):
    """同上，但不看 status——已宣告示降的編隊也要能持續重算可信度。

    示降當時不可信、其後被打到真的崩了 → 可信度隨狀態變化而成立，
    敵方的停火義務自那時起發生。這是「情況曖昧時攻方有裁量餘地」的正確實作。
    """
    u = s["units"][uid]
    if u.get("org", 100) >= SURR_ORG:
        return False, []
    why = []
    if encircled(s, uid):
        why.append("被四面包圍")
    if u.get("resources", {}).get("RAT", 100) < SURR_RAT and s["global_hour"] >= 7 * 24:
        why.append("食物耗盡且戰役逾 7 日")
    if u.get("no_supply_hours", 0) >= SURR_NOSUP_H:
        why.append(f"連續 {SURR_NOSUP_H} hour 無補給")
    # combat_v1 的第三條是「整師指揮官陣亡 + 信號中斷」。信號中斷已實作
    # （signal_lost），但**師長陣亡沒有任何模型**：本引擎沒有幹部傷亡，
    # 而斬首在本劇本是即時勝利、遊戲會直接結束。因此這一條是**空條件**，
    # 與 law_of_war.md 的 W3 同樣處理：明文標示、不得以代理指標偷偷補上。
    # （要啟用它得先做幹部傷亡模型，見 precedents.md §8。）
    return bool(why), why


def signal_lost(s, uid):
    """通訊中斷：被四面包圍**且**補給走廊切斷 → 與司令部失聯。

    效果是**新命令送不進去**，不是失去戰鬥力——該編隊繼續執行最後一道
    既有命令（史實上就是這樣）。這也是「自行投降」這條路存在的機械理由：
    失聯的部隊要投降，只能由現地部隊自己決定，司令部下不了令。

    [判例]：包圍與斷補同時成立即視為失聯，不設緩衝時數。孤立就是孤立；
    加一個計時器只是多一個我可以調的旋鈕。
    """
    u = s["units"][uid]
    return u.get("supply_status") == "cut" and encircled(s, uid)


def command_delay(s, side, uid, level="L1"):
    """該編隊此刻的命令延遲時數；信號中斷 → 回傳 None（新命令送不進去）。

    延遲本體委派給 command.command_delay（基準 L1/L2/L3 ＋ 指揮所階梯調整：
    前進指揮所罩內 0／有主指揮所 +1／無指揮所 +2，依該編隊與指揮所的距離）。

    初稿在這裡自己讀 `command.delay_level`——那個欄位不存在，所以永遠回傳 2。
    等於把「前進指揮所買到的節奏優勢」整個抹掉，而 law_of_war.md §4 的寬限期
    引用本函式，連法律免責期也一起算錯。

    通訊在這套規則裡是雙重承重：前進指揮所買到的不只是機動節奏，
    也是更快的示降／受降與更短的法律免責期。
    """
    if signal_lost(s, uid):
        return None
    return command.command_delay(s, side, level, s["units"][uid]["pos"])


# ── 具法律後果的命令：機器解析，不經裁判的文字解讀 ──────────────────
# 「有沒有下示降」如果由我讀自由文字認定，那就是一個我可以偏袒而無人查得出來的
# 地方。因此這兩個動作採規範格式、由程式解析；不符格式者**不自動執行**，
# 而是留下一筆事實供裁判以 ruling() 逐案處理——歧義因此是可見的，不是被我默默解決的。
SURRENDER_FORMS = ("示降", "SURRENDER")
ACCEPT_FORMS = ("受降", "ACCEPT")
# 只要命令文字裡出現這些詞、卻不符規範格式，就必須浮出來由裁判裁示——
# 不能因為「我看得懂它的意思」就替它執行。
SURRENDER_HINTS = ("示降", "受降", "投降", "白旗", "繳械", "請降",
                   "SURRENDER", "ACCEPT", "CAPITULAT", "WHITE FLAG")


def parse_legal_order(text):
    """解析規範格式。回傳 (kind, uid, by_uid) 或 None。

      示降 RED-1              → ("declare", "RED-1", None)
      受降 RED-1              → ("accept",  "RED-1", None)
      受降 RED-1 BY BLU-2     → ("accept",  "RED-1", "BLU-2")
    """
    if not text:
        return None
    parts = text.replace("　", " ").split()
    if not parts:
        return None
    head = parts[0].upper()
    kind = ("declare" if parts[0] in SURRENDER_FORMS or head in SURRENDER_FORMS else
            "accept" if parts[0] in ACCEPT_FORMS or head in ACCEPT_FORMS else None)
    if kind is None or len(parts) < 2:
        return None
    uid, by = parts[1], None
    if kind == "accept" and len(parts) >= 4 and parts[2].upper() == "BY":
        by = parts[3]
    return kind, uid, by


def looks_legal_but_unparsed(text):
    """文字裡有投降字樣但不符規範格式——歧義要浮出來，不能被默默解讀。"""
    if not text:
        return False
    if parse_legal_order(text):
        return False
    up = text.upper()
    return any(w in text or w in up for w in SURRENDER_HINTS)


def apply_due_legal_orders(s):
    """每 hour 於 resolve 之前呼叫：把到期的示降／受降命令付諸執行。

    延遲已由 enqueue_order 在下令當時算入（含指揮所階梯），故此處只處理到期者。
    投遞檢查：目標編隊信號中斷 → 命令未送達，記錄事實。
    """
    ev = []
    for o in hs.due_orders(s):
        parsed = parse_legal_order(o.get("text", ""))
        if parsed is None:
            if looks_legal_but_unparsed(o.get("text", "")):
                record_fact(s, "命令待裁", side=o.get("side"), text=o.get("text"),
                            note="含投降字樣但不符規範格式，未自動執行，待裁判裁示")
                ev.append((o.get("side"),
                           f"命令「{o.get('text')}」含投降字樣但不符規範格式（示降 <UID>／"
                           f"受降 <UID> [BY <UID>]），未自動執行，已送裁判裁示"))
            continue
        kind, uid, by = parsed
        # 示降的對象是本方編隊；受降的對象是**敵方**編隊——歸屬檢查兩者相反。
        want = o.get("side") if kind == "declare" else ENEMY[o.get("side")]
        if uid not in s["units"] or s["units"][uid].get("side") != want:
            ev.append((o.get("side"),
                       f"命令「{o.get('text')}」指涉的編隊不存在，或歸屬不符"
                       f"（示降須為本方編隊、受降須為敵方編隊），未執行"))
            continue
        if kind == "declare":
            if signal_lost(s, uid):
                record_fact(s, "命令未送達", unit=uid, side=o.get("side"),
                            text=o.get("text"), note="該編隊信號中斷")
                ev.append((o.get("side"), f"示降命令未送達 {uid}：該編隊信號中斷（若要投降只能現地自行決定）"))
                continue
            ok, msg = declare_surrender(s, uid)
            ev.append((o.get("side"), msg))
            if ok:
                ev.append((ENEMY[o["side"]], f"敵 {uid} 宣告示降（gh{s['global_hour']}）"))
        else:
            res = accept_surrender(s, uid, by_uid=by)
            if res is None:
                ev.append((o.get("side"), f"受降 {uid} 未成立：該編隊未處於已投降狀態，或本方無編隊可執行受降"))
            else:
                ev.append((o.get("side"),
                           f"受降 {uid}：俘虜 {res['pow']} 人由 {res['captor']} 接收，"
                           f"抽出 {res['guard']} 人看管，口糧 -{res['rat_per_hour']}%/hr"))
                ev.append((ENEMY[o["side"]], f"我方 {uid} 已被敵受降，全員成為戰俘"))
    return ev


def force_retreat(s, uid, note="潰散後撤"):
    """強制撤退 ROUT_RETREAT 格，朝本方補給源方向（x=0 / x=width-1）。"""
    u = s["units"][uid]
    src_x = 0 if u["side"] == "allies" else s["map"]["width"] - 1
    for _ in range(ROUT_RETREAT):
        nxt = step_toward(u["pos"], [src_x, u["pos"][1]])
        if nxt == u["pos"] or not _passable(u, terr(s, nxt)):
            break
        u["pos"] = nxt
    abandon_works(u)                     # 撤退即棄工事
    u["static_hours"] = 0
    u["last_action"] = note
    return u["pos"]


def evaluate_status(s):
    """每 hour 呼叫一次。回傳事件列表 [(uid, kind, text)]，由呼叫方決定推播給誰。"""
    ev = []
    for uid, u in list(s["units"].items()):
        if u.get("side") not in ("allies", "axis"):
            continue
        st = status_of(u)
        u.setdefault("status", STATUS_ACTIVE)
        if st in (STATUS_SURRENDERED, STATUS_DISBANDED):
            continue

        # 無補給時數計數（供投降條件用）
        if u.get("supply_status") == "cut":
            u["no_supply_hours"] = u.get("no_supply_hours", 0) + 1
        else:
            u["no_supply_hours"] = 0

        if st == STATUS_ACTIVE:
            # combat_v1〈潰散〉：3 條同時成立
            c1 = u.get("org", 100) < ROUT_ORG
            c2 = cas_24h(s, uid) > ROUT_CAS_24H
            c3 = (u.get("supply_status") == "cut" or encircled(s, uid)
                      or signal_lost(s, uid))   # combat_v1：退路被切斷 OR 指揮鏈中斷
            if c1 and c2 and c3:
                u["status"] = STATUS_ROUTED
                u["rout_gh"] = s["global_hour"]
                pos = force_retreat(s, uid)
                ev.append((uid, "rout",
                           f"{u['name']} 潰散（org {u['org']}、24hr 傷亡 "
                           f"{cas_24h(s, uid):.0%}）→ 強制後撤至 {tuple(pos)}"))
        elif st == STATUS_ROUTED:
            since = s["global_hour"] - u.get("rout_gh", s["global_hour"])
            if since >= ROUT_RECOVER_H and u.get("supply_status") == "intact":
                u["status"] = STATUS_ACTIVE
                u["org"] = max(u.get("org", 0), 30.0)
                u.pop("rout_gh", None)
                ev.append((uid, "rally", f"{u['name']} 收攏重整，org 恢復至 {u['org']}（殘廢但可戰）"))
            elif since >= ROUT_DISBAND_H:
                u["status"] = STATUS_DISBANDED
                ev.append((uid, "disband", f"{u['name']} 逾 {ROUT_DISBAND_H} hour 未收攏 → 解散，殘部成為散兵"))

        # combat_v1〈投降觸發條件〉：org<15 且四條之一 → **部隊自行投降**
        ok, why = surrender_eligible(s, uid)
        u["surrender_eligible"] = ok
        u["surrender_why"] = why
        if ok:
            u["status"] = STATUS_SURRENDERED
            u["surrender_kind"] = SURR_AUTO
            u["surrender_gh"] = s["global_hour"]
            u["fortification"] = 0.0
            u.pop("rout_gh", None)
            record_fact(s, "自行投降", unit=uid, side=u["side"], path=SURR_AUTO,
                        org=u.get("org"), supply=u.get("supply_status"),
                        encircled=encircled(s, uid), conditions=why)
            ev.append((uid, "surrender_auto",
                       f"{u['name']} 符合 combat_v1〈投降觸發條件〉（{'、'.join(why)}）"
                       f"→ **該編隊自行投降，你已失去對它的控制權**：不再接受命令、"
                       f"不移動、不開火。對手可以受降，也可以不受降"))
    return ev


def declare_surrender(s, uid):
    """指揮官宣告示降。**任何編隊、任何時候都可以**，一經宣告即不可逆。

    不設資格門檻是刻意的：禁止詐降會讓受降變成零風險，「不許射殺投降者」就成了
    沒有成本的規則，而戰爭法真正的張力在於保護是可以被利用的。唯一的閘門是
    不可逆——濫用示降當戰術探測，一次就永久廢掉該編隊，且開火即觸 W7。

    回傳 (True, 訊息)。訊息只陳述宣告當時的客觀狀態，不含任何合法性認定。
    """
    u = s["units"][uid]
    if status_of(u) == STATUS_SURRENDERED:
        return False, "已於先前宣告示降，不可重複"
    u["status"] = STATUS_SURRENDERED
    u["surrender_kind"] = SURR_DECLARED
    u["surrender_gh"] = s["global_hour"]
    u["fortification"] = 0.0
    # 用 surrender_conditions 而非 surrender_eligible：上一行已把 status 設為
    # SURRENDERED，而 surrender_eligible 會因「非戰鬥狀態」直接回 False。
    # 這裡只是把客觀條件記進事實紀錄，不是判定可信度。
    cond, why = surrender_conditions(s, uid)
    record_fact(s, "示降", unit=uid, side=u["side"], path=SURR_DECLARED,
                org=u.get("org"), supply=u.get("supply_status"),
                encircled=encircled(s, uid), conditions_met=cond, conditions=why)
    return True, (f"{u['name']} 於 gh{s['global_hour']} 宣告示降（不可逆）。"
                  f"當時客觀狀態：org {u.get('org')}、補給 {u.get('supply_status')}、"
                  f"符合 combat_v1 投降條件＝{cond}"
                  f"{'（' + '、'.join(why) + '）' if why else ''}。"
                  "★ 此示降是否可信、敵方不受降是否違法，屬戰後法庭爭點，引擎不作認定。")


def accept_surrender(s, uid, by_uid=None):
    """受降：人員轉 POW 計入受降方，裝備繳獲；受降方負擔口糧與看管兵力。

    by_uid 為執行受降的敵方編隊（預設取距離最近者）。
    """
    u = s["units"][uid]
    if status_of(u) != STATUS_SURRENDERED:
        return None
    foe = own(s, ENEMY[u["side"]])
    if by_uid is None:
        cand = [(dist(v["pos"], u["pos"]), k) for k, v in foe.items()
                if status_of(v) in COMBAT_STATUSES]
        if not cand:
            return None
        by_uid = min(cand)[1]
    captor = s["units"][by_uid]
    pow_n = u.get("personnel", 0)

    # 計分：POW 與陣亡同權（受降在分數上不吃虧 → W2 沒有「不得不犯」的藉口）
    u["losses"]["personnel"] += pow_n
    u["losses"]["tanks"] += u["equip"]["tanks"]
    u["losses"]["guns"] += u["equip"]["guns"]
    u["personnel"] = 0
    u["equip"]["tanks"] = u["equip"]["guns"] = 0
    u["org"] = 0.0

    # 受降成本 1：俘虜要吃飯。按人頭等比推導，非裁判自訂常數——
    # 受降方基準 RAT 消耗對應其建制人數，俘虜按同一人均值加計。
    est = captor.get("personnel", 0) + captor["losses"]["personnel"] or 1
    captor["pow_held"] = captor.get("pow_held", 0) + pow_n
    captor["pow_rat_per_hour"] = round(CONS["L1"]["RAT"] * captor["pow_held"] / est, 3)
    # 受降成本 2：看管兵力自戰鬥序列扣除（不計為傷亡，僅不能作戰）
    guard = int(pow_n * POW_GUARD_RATIO)
    captor["guard_detached"] = captor.get("guard_detached", 0) + guard
    captor["personnel"] = max(0, captor.get("personnel", 0) - guard)

    return {"pow": pow_n, "captor": by_uid, "guard": guard,
            "rat_per_hour": captor["pow_rat_per_hour"]}


def pow_upkeep(s):
    """每 hour 呼叫：扣除看管俘虜的口糧。"""
    for u in s["units"].values():
        r = u.get("pow_rat_per_hour", 0)
        if r:
            res = u.setdefault("resources", {})
            res["RAT"] = round(max(0.0, res.get("RAT", 100) - r), 2)


def pursuit_factor(s, target_uid):
    """combat_v1：追擊潰散部隊 ×3 傷亡。§2 明文合法——潰散不等於投降。"""
    return PURSUIT_MULT if status_of(s["units"][target_uid]) == STATUS_ROUTED else 1.0


# ── 事實紀錄（不作任何法律判斷）─────────────────────────────────
# ★ 引擎只記事實。合法與否是**戰後法庭的辯論**，由裁判判決，不由程式認定。
#   本節刻意不含：條號、合法／不合法、寬限期、可信度、以及任何自動制裁。
#   那些是 law_of_war.md 給法官的標準，不是給機器的算式。
#
#   每個 tick 的快照本來就存了全部客觀狀態（org、傷亡、補給、位置、工事、
#   各方偵獲清單），法庭可直接查。引擎唯一需要額外記的是快照抓不到的兩件事：
#     ① 誰在第幾小時對誰開了火（交火／突擊）
#     ② 誰做了什麼宣告（示降、受降）
#   其餘一律由法庭從快照推導，避免引擎替法官預先認定。

def record_fact(s, kind, gh=None, **fields):
    """把一件事實寫進 s["record"]。無條號、無評價。"""
    e = {"gh": s["global_hour"] if gh is None else gh, "kind": kind}
    e.update(fields)
    s.setdefault("record", []).append(e)
    return e


BEARING8 = {(0, -1): "正北", (1, -1): "東北", (1, 0): "正東", (1, 1): "東南",
            (0, 1): "正南", (-1, 1): "西南", (-1, 0): "正西", (-1, -1): "西北"}


def bearing_from(target_pos, firer_pos):
    """自目標看向射擊方的八向方位（裁示 25 落彈分析）。彈坑犁溝可測出方位角。"""
    dx = firer_pos[0] - target_pos[0]
    dy = firer_pos[1] - target_pos[1]
    return BEARING8.get((0 if dx == 0 else (1 if dx > 0 else -1),
                         0 if dy == 0 else (1 if dy > 0 else -1)), "同格")


# 一格的實距（km）。由 105mm 射程 4 格 = 8.5 km 反推（rules/combat_v1.md §VI）。
HEX_KM = 8.5 / 4
SOUND_MPS = 340.0          # 聲速，用於 flash-to-bang 測距的說明文字
RANGE_BAND = ((2, "近距"), (4, "中距"), (99, "接近最大射程"))


def range_band(d):
    """白天可得的粗略距離帶（彈著散佈判定）。"""
    for lim, name in RANGE_BAND:
        if d <= lim:
            return name
    return RANGE_BAND[-1][1]


def record_crater(s, firing_uids, target_uid):
    """裁示 25 + 34：落彈分析。目標編隊自彈坑取得方位、口徑，以及距離資訊。

    1944 年砲兵以彈坑犁溝測方位、以彈坑尺寸與破片判口徑。

    ★ 裁示 34（Run 7，取代裁示 25 的「一律不給距離」）：
      距離改為**依晝夜給不同精度**。裁示 25 排除距離的理由是「聲測需專門觀測營編制」，
      但 combat_v1.md §VI-4 明文把聲測列為反砲擊的標準手段，該理由不成立
      （見 rules/arbiter_v2.md §VIII）。

      實際可用的方法是 **flash-to-bang**——量砲口焰與聲響的時間差，聲速約 340 m/s。
      一名軍官加一支碼錶即可，不需要編制。但**前提是看得見砲口焰**：
        · 夜間／黎明 → 砲口焰在 8–10 km 清晰可見 → 距離 ±1 格
        · 白天       → 砲口焰幾乎看不見 → 只能由彈著散佈判粗略距離帶
      （最大射程附近散佈明顯放大，這是白天唯一可靠的距離線索。）

      零擲骰：兩者皆為目標距離的確定函數。
    """
    tgt = s["units"][target_uid]
    for fu in firing_uids:
        f = s["units"].get(fu)
        if not f:
            continue
        cal = sorted((f.get("gun_mix") or GUN_MIX.get(f["type"], {})).keys())
        d = dist(tgt["pos"], f["pos"])
        night = is_night(s)
        e = {
            "gh": s.get("global_hour", 0),
            "bearing": bearing_from(tgt["pos"], f["pos"]),
            "caliber": "、".join(cal) or "不明",
            "night": night,
        }
        if night:
            e["range_hex"] = d                    # 報告時以「約 d 格（±1）」呈現
        else:
            e["range_band"] = range_band(d)
        tgt.setdefault("crater_log", []).append(e)


def record_engagement(s, firing_uids, target_uid, kind="交火"):
    """記錄一次火力／突擊事實。**不判斷任何一方是否違法。**

    只記「誰、對誰、第幾小時、當時對方處於什麼可查狀態」。
    起訴方日後要主張這是 W1 或 W2，須自行從此紀錄與快照舉證；
    寬限期是否已過、示降是否可信、該方是否明知，全部是法庭的爭點。
    """
    if not firing_uids:
        return None
    tgt = s["units"][target_uid]
    actor = s["units"][firing_uids[0]]["side"]
    f = {"actor_side": actor, "firing": list(firing_uids), "target": target_uid,
         "target_status": status_of(tgt)}
    # 只記客觀讀值，不記結論
    if tgt.get("surrender_gh") is not None:
        f["target_declared_surrender_gh"] = tgt["surrender_gh"]
    if tgt.get("no_return_fire_since") is not None:
        f["target_no_return_fire_since"] = tgt["no_return_fire_since"]
    f["target_org"] = tgt.get("org")
    est = tgt.get("personnel", 0) + tgt["losses"]["personnel"] or 1
    f["target_cas_rate"] = round(tgt["losses"]["personnel"] / est, 4)
    f["target_supply"] = tgt.get("supply_status")
    f["target_encircled"] = encircled(s, target_uid)
    f["target_contact_hours"] = tgt.get("contact_hours", {}).get(actor, 0)
    # 開火方自己若曾宣告示降，記下這個事實（是否構成背信由法庭認定）
    declared = [u for u in firing_uids
                if s["units"][u].get("surrender_gh") is not None]
    if declared:
        f["firing_units_that_had_declared_surrender"] = declared
    return record_fact(s, kind, **f)


def refresh_return_fire(s):
    """每 hour 呼叫：記錄「自何時起未再實施攻擊」這個**事實**。

    這不是「已喪失戰鬥力」的認定——那是法律結論，屬 law_of_war.md W1 要件 B，
    由法庭在辯論中與傷亡率、補給狀態合併判斷。此處只記可觀察到的停火事實。
    """
    for uid, u in s["units"].items():
        if u.get("side") not in ("allies", "axis"):
            continue
        if u["flags"].get("fired"):
            u.pop("no_return_fire_since", None)
        else:
            u.setdefault("no_return_fire_since", s["global_hour"])


def combat_state_tag(s, uid, viewer_side):
    """給該方的可觀察狀態旗標。只給定性事實，不給 org／傷亡原始數字。

    示降是對敵宣告，故 SURRENDERED 無條件顯示；其餘須「持續接觸 ≥2 hour」。
    ★ 全部是**觀察結果**，不是法律結論——「未見還擊」不等於「已喪失戰鬥力」，
      後者是 law_of_war.md W1 的要件結論，由法庭合併傷亡率與補給狀態認定。
      這一欄同時是日後爭執「該方是否明知」時的紀錄。
    """
    u = s["units"][uid]
    st = status_of(u)
    pre = ""
    if st == STATUS_SURRENDERED:
        gh_txt = f"（gh{u['surrender_gh']}）" if u.get("surrender_gh") is not None else ""
        pre = ("自行投降" if surrender_kind(u) == SURR_AUTO else "已宣告示降") + gh_txt
        # ★ 不告訴對手該示降「可不可信」，也不告訴他開火會不會違法。
        #   給的是他本來就觀察得到的事實；判斷與後果都是他自己的。
    if u.get("contact_hours", {}).get(viewer_side, 0) < 2:
        return ("｜" + pre) if pre else ""
    if pre:
        pre += "、"
    if st == STATUS_DISBANDED:
        return f"｜戰鬥力狀態 {pre}已解散"
    if u.get("no_return_fire_since") is not None:
        return f"｜戰鬥力狀態 {pre}未見還擊（自 gh{u['no_return_fire_since']} 起）"
    if st == STATUS_ROUTED:
        return f"｜戰鬥力狀態 {pre}潰散中"
    est = u.get("personnel", 0) + u["losses"]["personnel"] or 1
    if u.get("org", 100) < 40 or u["losses"]["personnel"] / est >= 0.30:
        return f"｜戰鬥力狀態 {pre}殘破"
    return f"｜戰鬥力狀態 {pre}有效"


# ── 裁示登錄（開放性的稽核機制）──────────────────────────────────
def ruling(s, what, basis, applied, precedent=False, gh=None):
    """把「裁判在第幾小時、基於什麼、裁了什麼、用什麼原語施加」寫進事實紀錄。

    引擎表達不了的狀況（前所未見的陣型、姿態、戰術）由裁判逐案裁示，但裁示不能
    變成戰史裡來源不明的狀態變動。本函式讓它成為一條**有時間戳**的紀錄：
    任何人都能拿時間戳對照結果，檢查該裁示是否在「還不知道誰受益」之前作出。

      what      裁了什麼
      basis     依據（規則書某節，或明白承認規則書沒寫）
      applied   用哪些引擎原語施加效果
      precedent True → 這是新判例，須寫進 precedents.md
    """
    r = record_fact(s, "裁示", gh=gh, what=what, basis=basis, applied=applied,
                    precedent=bool(precedent))
    if precedent:
        s.setdefault("pending_precedents", []).append(r)
    return r


# ── 每 hour 管線 ────────────────────────────────────────────────
# 迴圈只固定「每小時一定要做的事」，不固定「可以做什麼事」——動作那一格是空的，
# 由 resolve(s, gh) 注入，裁判在裡面可以寫任何東西。
# 「引擎做不到」永遠不是裁示的理由：表達不了的用 ruling() + 原語打進去。
FATIGUE_MARCH       = 5    # movement_v1：連續行軍每 hour +5（正常天氣）
FATIGUE_MARCH_NIGHT = 3    # movement_v1：夜間額外 +3
FATIGUE_REST_FULL   = 10   # movement_v1：完全休整 -10（睡覺）
FATIGUE_COMBAT = {"light": 8, "medium": 15, "heavy": 25}   # movement_v1：輕/中/重戰鬥


def fatigue_from_combat(tier="light"):
    """給 resolve 用：戰鬥強度 → 疲勞增量（movement_v1）。

    砲擊對受擊方是輕戰鬥（探查級）＝ +8；地面戰預設陣地 ＝ 中戰鬥 +15；
    重戰鬥 +25 由裁判判定。缺陷 11 的修正：Run 4 對受砲擊方只加 3，
    且讓**開火方每小時恢復 -3** ——開火不是休息，方向是反的。
    """
    return FATIGUE_COMBAT.get(tier, FATIGUE_COMBAT["light"])


def run_tick(s, resolve, hours=6, log=None):
    """跑一個 tick 的 N 個小時。回傳每小時的敘事行。

    resolve(s, gh) 是**裁判的裁示注入點**，回傳 [(target, text)] 事件清單
    （target 須為 uid／陣營／both，見 push_log 的禁用預設）。

    管線順序有依賴，不可調動：
      1 activate_due_cps / hour_brief
      2 ★ resolve —— 移動、砲擊、地面戰、任何前所未見的動作
      3 行軍疲勞與休整、消耗
      4 apply_fatigue_caps
      5 refresh_visibility → spot
      6 refresh_return_fire → refresh_combat_hours   （讀 flags，須在戰鬥後）
      7 org_recovery → evaluate_status               （見下方 [判例]）
      8 pow_upkeep
      9 push_log → clear_flags → end_hour

    [判例] org_recovery 排在 evaluate_status **之前**：組織度的自然恢復是連續過程，
    潰散/投降的門檻判定應該用該小時的**淨值**。若倒過來，等於把該小時的傷害
    重複計一次。此裁示對雙方對稱、且在任何對局開始前作出。
    """
    resupply(s)                          # tick 邊界補給（logistics_v1；同時寫入 supply_status）
    lines = []
    for _ in range(hours):
        gh = s["global_hour"]
        command.activate_due_cps(s)
        hs.hour_brief(s)

        ev = apply_due_legal_orders(s)          # 具法律後果的命令：機器解析先行
        ev += list(resolve(s, gh) or [])

        night = is_night(s)
        for uid, u in s["units"].items():
            if u.get("side") not in ("allies", "axis"):
                continue
            if u["flags"].get("moved"):
                # 行軍疲勞由 advance() 施加（白天 +5／夜間 +8，= movement_v1 的 5 + 3），
                # 此處**不得再加**——2026-07-30 曾在這裡重複加一次，導致行軍疲勞加倍。
                consume(s, uid, "L1")
            elif u["flags"].get("fired") or u["flags"].get("hit"):
                consume(s, uid, "L3")          # 交戰中的消耗由 resolve 視情況再加
            else:
                u["fatigue"] = max(0, u.get("fatigue", 0) - FATIGUE_REST_FULL)
                consume(s, uid, "L0")
        apply_fatigue_caps(s)
        refresh_fortification(s)      # Run 7：依所在格的 man-hours 重算各編隊工事值

        refresh_visibility(s)
        for side, lst in spot(s).items():
            for uid in lst:
                ev.append((side, f"★我方偵獲敵 {uid} 於 {tuple(s['units'][uid]['pos'])}"))

        refresh_return_fire(s)
        refresh_combat_hours(s)
        org_recovery(s)
        for uid, kind, txt in evaluate_status(s):
            ev.append((uid, txt))
        pow_upkeep(s)

        push_log(s, ev, gh_label=f"[gh{gh}] ")
        line = f"[gh{gh} {hs.game_time_str(gh)}] " + ("；".join(x for _, x in ev) if ev else "無事件")
        lines.append(line)
        if log is not None:
            log.append(line)
        clear_flags(s)
        hs.end_hour(s, line)
    return lines


def score(s):
    out = {}
    for side in ("allies", "axis"):
        infl = {"personnel": 0, "tanks": 0, "guns": 0}
        for u in own(s, ENEMY[side]).values():           # 敵方的損失 = 我方殲敵
            slf = u.get("losses_self") or {}
            for k in infl:
                # 扣除敵方的友軍誤擊自傷——那不是我方造成的（TODO P6-16）
                infl[k] += u["losses"][k] - slf.get(k, 0)
        pts = sum(infl[k] * SCORE_W[k] for k in infl)
        out[side] = {"inflicted": infl, "points": pts}
    return out


# ── 渲染 ────────────────────────────────────────────────────────
TYPE_INI = {"recon": "r", "infantry": "i", "armor": "t", "artillery": "a",
            "engineer": "e", "mech_inf": "m", "aa": "f", "ranger": "s", "hq": "h"}


def tok(uid, u, viewer):
    """3 字寬單位標記。師/旅=BLU-2→B2、BLU-AD→BA；拉出的營=母師+兵種字母（B2r=藍2偵察）。"""
    base = "B" if u["side"] == "allies" else "R"
    if u.get("is_detachment"):
        parent = u.get("parent", "").split("-", 1)[-1][:2]
        t = base + parent[:1 if parent[:1].isdigit() else 2] + TYPE_INI.get(u["type"], "?")
    else:
        t = base + uid.split("-", 1)[1][:2]
    return t[:3].ljust(3)


def ascii_map(s, viewer="god", show_cp=True):
    W, H = s["map"]["width"], s["map"]["height"]
    pos_unit, _, _ = mc.index_state(s, viewer_side=viewer)
    sup = supply_status(s)
    cpmark = {}
    if show_cp:
        sides = ("allies", "axis") if viewer == "god" else (viewer,)
        for sd in sides:
            for kind, p in command.cp_hexes(s, sd).items():
                cpmark[tuple(p)] = ("主" if kind == "main" else "前") + ("★" if s["command"][sd].get("commander_at") == kind else "")
        if viewer != "god":                      # 敵方已偵獲的指揮所
            for tagstr in s.get("fog_of_war", {}).get(f"{viewer}_spotted_cps", []):
                kind, xy = tagstr.split("@")
                x, y = [int(v) for v in xy.split(",")]
                cpmark[(x, y)] = "敵" + ("主" if kind == "main" else "前")
    if viewer == "god":
        vis_ids = set(s["units"])
    else:
        spotted = set(s.get("fog_of_war", {}).get(f"{viewer}_spotted", []))
        vis_ids = {uid for uid, u in s["units"].items() if u["side"] == viewer} | spotted
    stack = {}
    for uid, u in s["units"].items():
        if uid in vis_ids:
            stack.setdefault(tuple(u["pos"]), []).append(uid)
    lines = []
    head = "    " + "".join(f"{x:<4}" if x % 5 == 0 else "    " for x in range(W))
    lines.append(head)
    for y in range(H):
        row = f"{y:>2}  "
        for x in range(W):
            if (x, y) in pos_unit:
                uid, u = pos_unit[(x, y)]
                vis_here = stack.get((x, y), [])
                t = tok(uid, u, viewer)
                if len(vis_here) > 1:
                    t = (t.strip()[:2] + "+").ljust(3)   # 同格多單位（+ = 還有其他）
                row += t + " "
            elif (x, y) in cpmark:
                row += cpmark[(x, y)].ljust(3)[:3] + " "
            else:
                t = s["map"]["terrain"][y][x]
                row += ("林  " if t == "F" else ".   ")
        lines.append(row + f" {y}")
    lines.append(head)
    return "\n".join(lines)


def _res_str(r):
    return " ".join(f"{k}{int(r.get(k,0))}" for k in ("POL", "SA", "HE", "AT", "RAT", "MED", "PARTS"))


def _ammo_str(u):
    """彈藥實數。Run 7：彈藥會打完，指揮官必須看得到剩幾發，否則無法決定何時開火。"""
    am = u.get("ammo") or {}
    if not am:
        return "彈藥: （無火砲）"
    mx = u.get("ammo_max") or {}
    parts = []
    for g, v in sorted(am.items()):
        cap = mx.get(g) or 1
        pct = 100.0 * v / cap
        mark = "　**⚠ 見底**" if pct < 15 else ("　⚠ 偏低" if pct < 35 else "")
        parts.append(f"{g} {v:,.0f}/{cap:,.0f}發（{pct:.0f}%）{mark}")
    return "彈藥: " + "｜".join(parts)


def _works_str(s, u):
    """該格的工事記憶與偽裝進度。工事記在格子上，離開再回來還在（Run 7 §9）。"""
    mh = hex_works(s, u["pos"])
    per = mh / max(u.get("personnel", 1), 1)
    tier = fort_tier(fort_from_hours(per))[0] if mh > 0 else "無"
    camo = u.get("camo_hours", 0.0)
    ct = ("**偽裝完成**" if u.get("camouflaged")
          else (f"偽裝 {camo:.2f}/{CAMO_HOURS}工時" if camo > 0 else "未偽裝"))
    return (f"本格工事記憶: {mh:,.0f} man-hours（÷本編隊 {u.get('personnel',0)} 人 "
            f"= {per:.2f}hr/人 → {tier}）｜{ct}")


def unit_lines(s, side, full=True):
    sup = supply_status(s)
    out = []
    for uid, u in sorted(own(s, side).items()):
        out.append(
            f"- **{uid}** {u['name']}｜位置 {tuple(u['pos'])}｜兵 {u.get('personnel',0)}"
            f"｜戰力 {u.get('strength')}%｜組織 {u.get('org')}｜疲勞 {u.get('fatigue')}"
            f"｜戰車 {u['equip']['tanks']}｜火砲 {u['equip']['guns']}"
            f"｜補給線 {sup.get(uid,'?')}｜能見 {u['visibility_state']}"
            f"｜工事 {u.get('fortification',0):.3f}/0.5"
            f"{own_state_tag(s, uid)}\n"
            f"  　{_ammo_str(u)}｜{_works_str(s, u)}\n"
            f"  　資源: {_res_str(u.get('resources',{}))}｜上一動作: {u.get('last_action','')}"
            + (f"\n  　可抽離營級代號: {orbat_codes(u)}" if u.get("orbat") else ""))
    return "\n".join(out)


def orbat_codes(u):
    """列出該編隊仍在建制內的營級代號（裁示 41：營代號必須公佈給該方）。"""
    return "、".join(f"{k}({v.get('type','?')})"
                     for k, v in u.get("orbat", {}).items()
                     if v.get("status") == "in_division") or "（無）"


def own_state_tag(s, uid):
    """己方編隊的狀態欄：自己的部隊自己當然知道得比敵人清楚。

    含指揮權與投降條件——因為那是指揮官必須知道才能做決定的事：
    某個編隊已經符合 combat_v1 的投降條件時，他有權知道，並自行決定示降或戰至全滅。
    """
    u = s["units"][uid]
    bits = []
    st = status_of(u)
    if st == STATUS_SURRENDERED:
        bits.append(("自行投降（**已失去指揮權**）" if surrender_kind(u) == SURR_AUTO
                     else "已宣告示降（仍在你的指揮下）")
                    + f"，gh{u.get('surrender_gh')}")
    elif st == STATUS_ROUTED:
        bits.append(f"**潰散中**（gh{u.get('rout_gh')} 起，{ROUT_RECOVER_H}hr 後補給恢復可收攏）")
    elif st == STATUS_DISBANDED:
        bits.append("已解散")
    if signal_lost(s, uid):
        bits.append("**信號中斷**（新命令送不進去，只執行最後一道既有命令）")
    if u.get("surrender_eligible") and st not in (STATUS_SURRENDERED, STATUS_DISBANDED):
        bits.append("已符合 combat_v1 投降條件：" + "、".join(u.get("surrender_why", [])))
    if u.get("combat_hours", 0) >= SUPPRESS_AFTER_H:
        bits.append(f"連續戰鬥 {u['combat_hours']}hr（壓制生效，每 hour 額外 -{SUPPRESS_PER_H} 組織）")
    if u.get("pow_held"):
        bits.append(f"看管俘虜 {u['pow_held']} 人（口糧 -{u.get('pow_rat_per_hour',0)}%/hr，"
                    f"已抽出 {u.get('guard_detached',0)} 人看管）")
    return ("｜" + "｜".join(bits)) if bits else ""


def enemy_lines(s, side):
    spotted = s.get("fog_of_war", {}).get(f"{side}_spotted", [])
    out = []
    for uid in spotted:
        u = s["units"][uid]
        approx = int(round(u.get("strength", 100) / 10.0) * 10)
        f0 = u.get("fortification", 0.0)
        fort = "未構築" if f0 <= 0 else ("已完成" if f0 >= 0.5 else "構築中")
        out.append(f"- **{uid}** {u['name']}｜位置 {tuple(u['pos'])}｜概估戰力 ~{approx}%"
                   f"｜狀態 {u['visibility_state']}｜工事 {fort}"
                   + combat_state_tag(s, uid, side))
    cps = s.get("fog_of_war", {}).get(f"{side}_spotted_cps", [])
    if cps:
        out.append(f"- 已偵獲敵指揮所徵候：{', '.join(cps)}")
    return "\n".join(out) or "- （目前無任何敵方單位在偵察範圍內／全部失去接觸）"


def clock(s):
    gh = s["global_hour"]
    return (f"Tick {s['tick']}/{s['max_ticks']}  hour {s['hour_in_tick']}/6  "
            f"global_hour {gh}  {hs.game_time_str(gh)}  {hs.daynight(gh)}")


def cp_garrison(s, side):
    """回報各指揮所格內是否有我方守軍（裁示 11：無守軍 → 敵單位進入即斬首）。"""
    out = []
    for kind, pos in command.cp_hexes(s, side).items():
        occ = [uid for uid, u in own(s, side).items() if list(u["pos"]) == list(pos)]
        star = "★軍長所在" if s["command"][side].get("commander_at") == kind else ""
        out.append(f"{'主' if kind=='main' else '前進'}指揮所 {tuple(pos)}{star}："
                   + (f"格內守軍 {', '.join(occ)}" if occ else "**格內無我方守軍單位**"))
    return "；".join(out) or "（尚無已生效的指揮所）"


def cp_line(s, side):
    c = s["command"][side]
    at = c.get("commander_at")
    pend = c.get("pending_cp", [])
    parts = [f"主指揮所 {tuple(c['main_cp']) if c.get('main_cp') else '未建'}",
             f"前進指揮所 {tuple(c['fwd_cp']) if c.get('fwd_cp') else '未建'}",
             f"軍長所在 {at or '隨隊（無指揮所）'}"]
    # 「+見說明」不是資訊。指揮官必須看得到前進指揮所的驗算結果與實際階梯，
    # 否則他可能付了斬首風險卻不知道自己已經拿不到 0 級延遲（裁示 42：
    # 前進指揮所須位於本方整編編隊 x 中位數之前，而自己的部隊推進會讓它失格）。
    if c.get("fwd_cp"):
        fwd_ok = command.fwd_cp_is_forward(s, side)
        xs = sorted(u["pos"][0] for u in s.get("units", {}).values()
                    if u.get("side") == side and not u.get("is_detachment"))
        med = xs[len(xs) // 2] if xs else "—"
        parts.append(
            f"前進指揮所「真的在前」驗算 {'✅ 通過' if fwd_ok else '❌ **未通過**'}"
            f"（本方整編編隊 x 中位數 = {med}；"
            f"{'藍軍須 x ≥ 中位數' if side == 'allies' else '紅軍須 x ≤ 中位數'}）")
        base = f"其 {command.FWD_RANGE} 格內編隊 0 級、其餘 +1 級" if (fwd_ok and at == "fwd") \
            else ("全軍 +1 級（軍長不在前進指揮所）" if fwd_ok
                  else "全軍 +1 級（驗算未通過，前進指揮所不生延遲效益）")
        parts.append(f"命令延遲加成 {base}")
    else:
        parts.append(f"命令延遲加成 +{command.delay_tier_adjust(s, side, (0, 0))} 級")
    if pend:
        parts.append("架設中: " + ", ".join(f"{p['kind']}@{tuple(p['pos'])}(gh{p['effective_gh']}生效)" for p in pend))
    return "｜".join(parts)


def crater_lines(s, side):
    """裁示 25：把我方各編隊遭砲擊時的落彈分析結果列出。只有方位與口徑。"""
    out = []
    for uid, u in sorted(own(s, side).items()):
        log = u.get("crater_log", [])
        if not log:
            continue
        agg = {}
        for e in log:
            k = (e["bearing"], e["caliber"])
            agg.setdefault(k, []).append(e["gh"])
        for (b, c), ghs in sorted(agg.items()):
            rng = f"gh{min(ghs)}" if len(ghs) == 1 else f"gh{min(ghs)}–gh{max(ghs)}"
            # 裁示 34：距離依晝夜給不同精度
            es = [x for x in log if (x["bearing"], x["caliber"]) == (b, c)]
            hexes = sorted({x["range_hex"] for x in es if "range_hex" in x})
            bands = sorted({x["range_band"] for x in es if "range_band" in x})
            dtxt = ""
            if hexes:
                lo, hi = max(1, min(hexes) - 1), max(hexes) + 1
                dtxt += (f"｜距離 **約 {min(hexes)} 格**（±1，即 {lo}–{hi} 格；"
                         f"夜間 flash-to-bang 測得）")
            if bands:
                dtxt += f"｜距離帶 **{'／'.join(bands)}**（白天，由彈著散佈判定）"
            out.append(f"- **{uid}**（{tuple(u['pos'])}）遭砲擊 {len(ghs)} 次｜"
                       f"來襲方位 **{b}**｜口徑 **{c}**{dtxt}｜時段 {rng}")
    return "\n".join(out) or "- （我方未遭砲擊，無落彈可供分析）"


def brief_md(s, side):
    zh = "藍軍" if side == "allies" else "紅軍"
    pend = hs.pending_for(s, side)
    sc = score(s)
    return f"""# {zh}戰報 — {clock(s)}

## 一、戰場態勢圖（你的視角；未偵獲的敵軍不會出現）
```
{ascii_map(s, side)}
```
圖例：`林`=森林（戰車不可入）｜`B*`=藍軍｜`R*`=紅軍｜`主/前`=你的指揮所（★=軍長所在）｜`敵主/敵前`=已偵獲的敵指揮所
座標 (x,y)，x 向東遞增。藍軍補給源＝西緣 x=0，紅軍補給源＝東緣 x=29。

## 二、我方部隊
{unit_lines(s, side)}

## 三、指揮系統
{cp_line(s, side)}
**指揮所守備狀態**（裁示 11：該格無守軍時，敵戰鬥單位進入即判定斬首、你立即落敗）：
{cp_garrison(s, side)}

## 四、敵情（僅列已偵獲）
{enemy_lines(s, side)}

## 四之二、落彈分析（裁示 25／34：彈坑犁溝測方位、彈坑尺寸判口徑；夜間可 flash-to-bang 測距 ±1 格，白天只得距離帶）
{crater_lines(s, side)}

## 五、我方延遲中的命令
{chr(10).join(f"- [{o['id']}] {o['level']} 「{o['text']}」 還要 {o['hours_until_effective']}hr 生效" for o in pend) or "- （無）"}

## 六、殲敵計分（雙方公開）
- 你已造成敵軍損失：{sc[side]['inflicted']} → **{sc[side]['points']} 分**
- 敵軍已造成你損失：{sc[ENEMY[side]]['inflicted']} → **{sc[ENEMY[side]]['points']} 分**

## 七、上一 tick 你方的紀錄（只含你自己的動作與你**當時真正偵獲**到的敵情）
{chr(10).join('- ' + t for t in s.get('hour_log_side', {}).get(side, [])[-14:]) or '- （無）'}
"""


def god_md(s):
    sc = score(s)
    return f"""# 上帝視角 — {clock(s)}

```
{ascii_map(s, 'god')}
```

## 藍軍 (allies)
{unit_lines(s, 'allies')}
指揮：{cp_line(s, 'allies')}
偵獲敵軍：{s.get('fog_of_war',{}).get('allies_spotted',[])}

## 紅軍 (axis)
{unit_lines(s, 'axis')}
指揮：{cp_line(s, 'axis')}
偵獲敵軍：{s.get('fog_of_war',{}).get('axis_spotted',[])}

## 殲敵計分
- 藍軍 {sc['allies']['points']} 分 {sc['allies']['inflicted']}
- 紅軍 {sc['axis']['points']} 分 {sc['axis']['inflicted']}
"""


def push_log(s, events, gh_label=""):
    """把事件依「誰看得到」分流進各方的可觀察日誌（防止上帝視角外洩）。

    events: [(target, text)]，target 必須是下列之一：
      - 單位 uid  → 該單位所屬方一定收；敵方**只有該單位當時被偵獲**才收
      - "allies" / "axis" → 只有該方收（指揮所架設、命令生效等該方內部事實）
      - "both"    → 真正中性、雙方都該知道的事（時間、天氣、公開計分）
    ★ 不接受 None：2026-07 第三次洩漏事故的根因就是「預設雙方都收」。
    """
    lg = s.setdefault("hour_log_side", {"allies": [], "axis": []})
    for side in ("allies", "axis"):
        spotted = set(s.get("fog_of_war", {}).get(f"{side}_spotted", []))
        for target, text in events:
            if target == "both":
                lg[side].append(f"{gh_label}{text}")
            elif target in ("allies", "axis"):
                if target == side:
                    lg[side].append(f"{gh_label}{text}")
            elif target in s["units"]:
                if s["units"][target].get("side") == side:
                    lg[side].append(f"{gh_label}{text}")
                elif target in spotted:
                    lg[side].append(f"{gh_label}【偵獲】{text}")
            else:
                raise ValueError(f"push_log: 事件目標 {target!r} 不合法（禁用 None，須指明 uid/陣營/both）")
    return lg


def clear_flags(s):
    for u in s["units"].values():
        if not u["flags"].get("moved"):
            u["static_hours"] = u.get("static_hours", 0) + 1
        u["flags"] = {}
    return s


def orbat_md(s, side):
    """該方的營級編制表（含各營攜行裝備）。**只印指定一方**，不含敵方任何資料。

    裁示 41 的常設補救：營級代號必須公佈給該方，否則指揮官無法指名抽離。
    此處另外列出各營依 bn_equip 實際攜行的戰車與野戰砲——那決定抽離後的戰力與計分價值。
    """
    zh = "藍軍" if side == "allies" else "紅軍"
    out = [f"# {zh}編制表 — {clock(s)}", "",
           "> 只列你自己的編制。敵方編制須靠偵察與推斷（鏡像劇本，可合理推論其鏡像）。", ""]
    sup = supply_status(s)
    for uid, u in sorted(own(s, side).items()):
        if u.get("is_detachment"):
            continue
        head = (f"## {uid} {u['name']}　兵 {u.get('personnel',0)}"
                f"｜戰力 {u.get('strength')}%｜組織 {u.get('org')}｜疲勞 {u.get('fatigue',0)}"
                f"｜戰車 {u['equip']['tanks']}｜火砲 {u['equip']['guns']}")
        st = own_state_tag(s, uid)
        out += [head + (st if st else ""), "",
                f"位置 {tuple(u['pos'])}｜地形 {'森林' if terr(s,u['pos'])=='F' else '開闊'}"
                f"｜工事 {u.get('fortification',0):.2f}（{fort_tier(u.get('fortification',0))[3]}"
                f"，工時 {u.get('dig_hours',0):.1f}hr）"
                f"｜砲擊暴露 {exposure_factor(u, terr(s,u['pos']))}"
                f"｜補給 {sup.get(uid,'?')}", "",
                "| 營碼 | 名稱 | 兵種 | 人數 | 狀態 | 攜行裝備 | 備註 |",
                "|---|---|---|---|---|---|---|"]
        ob = u.get("orbat", {})
        for code, b in ob.items():
            eq = bn_equip(u, code)
            eqs = "、".join(f"{k} {v}" for k, v in eq.items() if v) or "—"
            stt = {"in_division": "在師", "detached": "**已拉出**"}.get(
                b.get("status", "in_division"), b.get("status"))
            note = b.get("note", "")
            nd = ("　**不可拉出**" if b.get("type") in ("hq",)
                  and "不可拉出" not in note else "")
            out.append(f"| `{code}` | {b.get('name','')} | {b.get('type','')} | "
                       f"{b.get('personnel','?')} | {stt} | {eqs} | {note}{nd} |")
        out.append("")
    det = {k: v for k, v in own(s, side).items() if v.get("is_detachment")}
    if det:
        out += ["## 已抽離的獨立編隊", "",
                "| 編隊 | 位置 | 兵力 | 組織 | 疲勞 | 工事 | 暴露 | 攜行裝備 | 母編隊 |",
                "|---|---|---|---|---|---|---|---|---|"]
        for uid, u in sorted(det.items()):
            eqs = "、".join(f"{k} {v}" for k, v in u["equip"].items() if v) or "—"
            out.append(f"| **{uid}** | {tuple(u['pos'])} | {u.get('personnel',0)} | "
                       f"{u.get('org')} | {u.get('fatigue',0)} | "
                       f"{u.get('fortification',0):.2f} | "
                       f"{exposure_factor(u, terr(s,u['pos']))} | {eqs} | {u.get('parent','?')} |")
    return "\n".join(out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "god"
    s = load()
    if cmd == "god":
        print(god_md(s))
    elif cmd == "brief":
        print(brief_md(s, sys.argv[2]))
    elif cmd == "orbat":
        print(orbat_md(s, sys.argv[2]))
    elif cmd == "map":
        print(ascii_map(s, sys.argv[2] if len(sys.argv) > 2 else "god"))
    elif cmd == "spot":
        refresh_visibility(s); print(spot(s)); save(s)
    elif cmd == "score":
        print(json.dumps(score(s), ensure_ascii=False, indent=2))
    elif cmd == "supply":
        print(json.dumps(supply_status(s), ensure_ascii=False, indent=2))
