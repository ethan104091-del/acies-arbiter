"""樞衡 Arbiter — **Run 4 凍結副本**（2026-07-30 凍結，勿修改）。

本檔存在的唯一目的是讓 Run 4 永久可重播為 8813:1790。專案根目錄的 arbiter.py
會繼續演進（Run 5 補齊 org 六項與缺陷 8），因此不能再用它重播本局。
要看引擎改進對本局的影響，把 of.py 改成 import arbiter——那是對照實驗，非回歸測試。


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
   4. 彈藥用百分比 → 永遠打不完。forces_v1 已給實數（步兵師 105mm 5,800 發、155mm 1,400 發；
      裝甲師 105mm SP 6,500 發），應改為按發數扣。見 prompts/referee_pvp.md。
   5. FIRE_MINUTES 固定 10 分鐘，抹掉了指揮官選擇火力急襲／持續壓制／干擾射擊的權利。
   6. 經驗只進地面戰 CP，沒有進命中 → 特戰旅的 ⭐⭐⭐⭐⭐ 幾乎全局無作用。見 precedents.md §八。
   7. org 損失只實作了 combat_v1 的 Casualty_% × 1.5，漏了 Suppression／Cover（工事內衝擊減半）／
      Resupply 三項。
   8. unit_cp 以 strength 為戰力係數，而 strength 與實際傷亡幾乎脫鉤：Run 4 的 RED-1 損失
      21.6% 人員與六成火砲，strength 只從 100 掉到 95，地面戰鬥力僅打九五折。砲兵輸出是對的
      （GUN_MIX 依 equip.guns 等比縮放），但**人員傷亡對地面戰鬥力幾乎無影響**。仍待修。
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

★ 每 hour 迴圈的呼叫順序（新增部分）：
   spot → …移動/砲擊/地面戰… → refresh_return_fire → evaluate_status → pow_upkeep
   （refresh_return_fire 必須在戰鬥後、evaluate_status 前，因為它讀 flags["fired"]）

★★★ 標示 [判例] 的常數不是規則書的，是裁判當場裁定的，須依 precedents.md 的制度處理：
   FIRE_MINUTES、SATURATION、density_factor 的四段值、森林 ×0.7、BASE_POWER 的 ranger 45、
   組織度損失的 ×150（此項其實源自 combat_v1，非裁判自訂）。
"""
import json, sys, math
from pathlib import Path

# 凍結副本住在 runs/run4_openfield/，但地圖、mapcore 等仍在專案根，故往上兩層。
GAME = Path(__file__).resolve().parents[2]
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
        u.setdefault("equip", dict(EQUIP.get(u["type"], {"tanks": 0, "guns": 0})))
        u.setdefault("losses", {"personnel": 0, "tanks": 0, "guns": 0})
        u.setdefault("static_hours", 0)
        u.setdefault("move_progress", 0.0)
        u.setdefault("flags", {})
    return s


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
        if u["type"] == "ranger":      # 特戰滲透隱蔽：好一級
            v = {"EXPOSED": "STANDARD", "STANDARD": "CAMOUFLAGED",
                 "CAMOUFLAGED": "CONCEALED", "CONCEALED": "CONCEALED"}[v]
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
    return r


def step_toward(a, b):
    dx = (b[0] > a[0]) - (b[0] < a[0])
    dy = (b[1] > a[1]) - (b[1] < a[1])
    return [a[0] + dx, a[1] + dy]


def _passable(u, t):
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
    if not under_command(s, uid):            # 自行投降／解散 → 不接受命令
        return s["units"][uid]["pos"]
    """把單位朝 target 推進 1 hour。回傳 (是否移動, 訊息)。避開不可通行地形。"""
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
    u["flags"]["moved"] = True
    u["static_hours"] = 0
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
def hurt(s, uid, personnel=0, tanks=0, guns=0, org=0, str_pct=0.0, fatigue=0, note=""):
    u = s["units"][uid]
    personnel = min(personnel, u.get("personnel", 0))
    tanks = min(tanks, u["equip"]["tanks"])
    guns = min(guns, u["equip"]["guns"])
    u["personnel"] = u.get("personnel", 0) - personnel
    u["equip"]["tanks"] -= tanks
    u["equip"]["guns"] -= guns
    for k, v in (("personnel", personnel), ("tanks", tanks), ("guns", guns)):
        u["losses"][k] += v
    if personnel:                                     # 潰散條件 2 需要 24 hour 傷亡窗
        u.setdefault("cas_log", []).append([s["global_hour"], personnel])
    if str_pct:
        u["strength"] = round(max(0.0, u.get("strength", 100) - str_pct), 2)
    if org:
        u["org"] = round(max(0.0, u.get("org", 100) - org), 2)
    if fatigue:
        u["fatigue"] = min(100, u.get("fatigue", 0) + fatigue)
    u["flags"]["fired"] = True
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
FIRE_MINUTES = 10        # [判例] 「集中砲擊」每 hour 每門砲的實際射擊分鐘數（其餘為修正/裝填/補彈）
SATURATION = 0.08        # [判例] 單一目標編隊每 hour 傷亡上限＝其兵力 8%（散布飽和、彈坑重疊）


def density_factor(u):
    p = u.get("personnel", 0)
    if p >= 10000:
        return 0.20      # 師級散佈於 2km 格
    if p >= 2000:
        return 0.15      # 旅級
    if p >= 600:
        return 0.30      # 營級（面積小、相對密集）
    return 0.12          # 偵察營等小單位、極散


def exposure_factor(u, terrain="."):
    """砲擊暴露係數。工事線性內插；森林另 ×0.7（樹木遮蔽與樹爆效應相抵後略優於開闊地）。
    ★開火不影響此係數——工事是實體掩體，EXPOSED 只影響「是否被偵獲」（裁示 36）。"""
    fort = u.get("fortification", 0.0)            # 0 ~ 0.5
    e = 0.7 - (fort / 0.5) * 0.6                  # 開闊散開 0.7 → 工事完整 0.10
    if terrain == "F":
        e *= 0.7
    return round(e, 3)


def bombard(s, firing_uids, target_uid, minutes=FIRE_MINUTES):
    """回傳 (人員傷亡, 戰車損失, 火砲損失, 明細字串)。多編隊集中射擊時效果相加、受飽和上限。"""
    firing_uids = [u for u in firing_uids if under_command(s, u)]
    if not firing_uids:
        return 0, 0, 0, "（無可受命之砲兵）"
    tgt = s["units"][target_uid]
    record_engagement(s, firing_uids, target_uid, kind="砲擊")   # 只記事實，不判罪
    detail, rounds_by = [], {}
    for fu in firing_uids:
        f = s["units"].get(fu)
        if not f:
            continue
        d = dist(f["pos"], tgt["pos"])
        mix = GUN_MIX.get(f["type"], {})
        total_nominal = sum(mix.values()) or 1
        scale = f["equip"]["guns"] / total_nominal          # 戰損後的實際門數比例
        for gtype, n in mix.items():
            rate, leth, rng, tk = GUN_SPEC[gtype]
            if d > rng:
                continue
            guns = n * scale
            r = guns * minutes * rate
            lf = leth * (0.5 if d > 0.8 * rng else 1.0)      # 逼近最大射程 → 散布增大 ×0.5
            rounds_by[gtype] = rounds_by.get(gtype, 0) + r
            detail.append(f"{fu} {gtype}×{guns:.0f} 距{d} 發數{r:.0f} 殺傷力{lf}")
            tgt.setdefault("_inc", [0.0, 0.0])
            tgt["_inc"][0] += r * lf
            tgt["_inc"][1] += r * tk
    if "_inc" not in tgt:
        return 0, 0, 0, "（無砲兵在射程內）"
    ef, df = exposure_factor(tgt, terr(s, tgt["pos"])), density_factor(tgt)
    cas = tgt["_inc"][0] * ef * df
    cap = tgt.get("personnel", 0) * SATURATION
    capped = cas > cap
    cas = int(min(cas, cap))
    # Tank_Exposure（determinism_v1 §III 的分級化，雙方同一套）：
    #   移動/行軍中 1.0；靜止且未構工事（開闊地散開停放）0.3；已構工事/hull-down 0.05
    if tgt["flags"].get("moved"):
        texp = 1.0
    elif tgt.get("fortification", 0) > 0:
        texp = 0.05
    else:
        texp = 0.3
    ecap_t = max(1, int(tgt["equip"]["tanks"] * SATURATION))
    ecap_g = max(1, int(tgt["equip"]["guns"] * SATURATION))
    tank_kill = min(int(tgt["_inc"][1] * texp), tgt["equip"]["tanks"], ecap_t)
    gun_kill = min(int(tgt["_inc"][1] * texp * 0.5), tgt["equip"]["guns"], ecap_g)
    del tgt["_inc"]
    msg = (f"暴露{ef} 密度{df} 戰車暴露{texp} → 傷亡 {cas} 人" + ("（觸飽和上限 8%）" if capped else "")
           + (f"、戰車 -{tank_kill}" if tank_kill else "") + (f"、火砲 -{gun_kill}" if gun_kill else "")
           + "｜" + "；".join(detail))
    return cas, min(tank_kill, tgt["equip"]["tanks"]), min(gun_kill, tgt["equip"]["guns"]), msg


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


def battle(s, atk_uids, def_uids, hexpos, atk_from_march=False, def_passive=True):
    """一個 hour 的地面戰。回傳 (明細字串, 守方應後退格數)。就地套用損失。"""
    atk_uids = [u for u in atk_uids if under_command(s, u)]
    if not atk_uids:
        return "（無可受命之攻擊部隊）", 0
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
    lines = [f"攻方 CP {a_cp}（{a_arms} 兵種、協同 {COMBINED.get(a_arms,1.7)}）"
             f" vs 守方 CP {d_cp}（{d_arms} 兵種"
             + (f"、工事 +{s['units'][def_uids[0]].get('fortification',0):.3f}" if def_uids else "") + "）"
             f" → **兵力比 {fr:.2f}** → 對照表：攻方 -{astr}% 戰力/-{aorg} 組織、守方 -{dstr}% 戰力/-{dorg} 組織"]
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
    if u.get("cp_signal_lost"):
        why.append("師長陣亡且信號中斷")
    return bool(why), why


def force_retreat(s, uid, note="潰散後撤"):
    """強制撤退 ROUT_RETREAT 格，朝本方補給源方向（x=0 / x=width-1）。"""
    u = s["units"][uid]
    src_x = 0 if u["side"] == "allies" else s["map"]["width"] - 1
    for _ in range(ROUT_RETREAT):
        nxt = step_toward(u["pos"], [src_x, u["pos"][1]])
        if nxt == u["pos"] or not _passable(u, terr(s, nxt)):
            break
        u["pos"] = nxt
    u["fortification"] = 0.0             # 撤退即棄工事
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
            c3 = u.get("supply_status") == "cut" or encircled(s, uid) or u.get("cp_signal_lost")
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


def score(s):
    out = {}
    for side in ("allies", "axis"):
        infl = {"personnel": 0, "tanks": 0, "guns": 0}
        for u in own(s, ENEMY[side]).values():           # 敵方的損失 = 我方殲敵
            for k in infl:
                infl[k] += u["losses"][k]
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


def unit_lines(s, side, full=True):
    sup = supply_status(s)
    out = []
    for uid, u in sorted(own(s, side).items()):
        out.append(
            f"- **{uid}** {u['name']}｜位置 {tuple(u['pos'])}｜兵 {u.get('personnel',0)}"
            f"｜戰力 {u.get('strength')}%｜組織 {u.get('org')}｜疲勞 {u.get('fatigue')}"
            f"｜戰車 {u['equip']['tanks']}｜火砲 {u['equip']['guns']}"
            f"｜補給線 {sup.get(uid,'?')}｜能見 {u['visibility_state']}"
            f"｜工事 {u.get('fortification',0):.3f}/0.5\n"
            f"  　資源: {_res_str(u.get('resources',{}))}｜上一動作: {u.get('last_action','')}")
    return "\n".join(out)


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
             f"軍長所在 {at or '隨隊（無指揮所）'}",
             f"命令延遲加成 +{command.delay_tier_adjust(s, side, (0,0)) if not c.get('fwd_cp') else '見說明'}"]
    if pend:
        parts.append("架設中: " + ", ".join(f"{p['kind']}@{tuple(p['pos'])}(gh{p['effective_gh']}生效)" for p in pend))
    return "｜".join(parts)


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

## 五、我方延遲中的命令
{chr(10).join(f"- [{o['id']}] {o['level']} 「{o['text']}」 還要 {o['hours_until_effective']}hr 生效" for o in pend) or "- （無）"}

## 六、殲敵計分（雙方公開）
- 藍軍已造成紅軍損失：{sc['allies']['inflicted']} → **{sc['allies']['points']} 分**
- 紅軍已造成藍軍損失：{sc['axis']['inflicted']} → **{sc['axis']['points']} 分**

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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "god"
    s = load()
    if cmd == "god":
        print(god_md(s))
    elif cmd == "brief":
        print(brief_md(s, sys.argv[2]))
    elif cmd == "map":
        print(ascii_map(s, sys.argv[2] if len(sys.argv) > 2 else "god"))
    elif cmd == "spot":
        refresh_visibility(s); print(spot(s)); save(s)
    elif cmd == "score":
        print(json.dumps(score(s), ensure_ascii=False, indent=2))
    elif cmd == "supply":
        print(json.dumps(supply_status(s), ensure_ascii=False, indent=2))
