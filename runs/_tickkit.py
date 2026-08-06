#!/usr/bin/env python3
"""tick 解算腳本的共用工具 — `docs/TODO.md` P7-17。

## 為什麼存在

Run 6 的九個 tick 腳本共 1,923 行（Run 4 是 1,231），膨脹的全是重複：
`spotted` 在 7 個腳本裡各寫一次、`is_big` 5 個、`route_step` 與 `route_advance` 各 4 個。
每次重寫都是一次犯同樣錯的機會——而 Run 6 確實犯了五次，每次都要還原快照重跑。

**本檔把那五個坑直接修在裡面，使它們無法再犯。** 每個函式的 docstring 記載它修的是哪個坑。

## 不得改動既有腳本

`runs/run4_*/`、`run5_*/`、`run6_*/` 的 t*.py **不要改成用這支工具**。
那些是稽核紀錄——重放它們必須得到與當時一致的結果。本檔只供未來的 run 使用。

## 用法

    import sys; sys.path.insert(0, str(Path(__file__).parent.parent))
    import _tickkit as tk

    IDX = tk.init_route_index(s, ROUTE)      # 跨 tick 續行必須這樣起始
    ...
    for msg in tk.route_advance(s, uid, ROUTE[uid], IDX):
        ev.append((uid, msg))
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arbiter as ar          # noqa: E402

SIDES = ("allies", "axis")


# ── 偵獲與編隊分類 ───────────────────────────────────────────────
def spotted(s, side):
    """該方**現在**偵獲的敵編隊。失去接觸者不在其中（手冊 §6）。"""
    return s.get("fog_of_war", {}).get(f"{side}_spotted", [])


def is_formation(u):
    """整編隊（非抽離營）。用於「敵師級或旅級」這類門檻。"""
    return not u.get("is_detachment")


def is_division(u):
    """師級：整編隊且兵種為 infantry / armor。旅級（ranger）不算。"""
    return not u.get("is_detachment") and u.get("type") in ("infantry", "armor")


# ── 航路行進 ────────────────────────────────────────────────────
def init_route_index(s, routes):
    """依各編隊的**現在位置**初始化航路索引。

    ★ Run 6 坑 #1：跨 tick 續行時若讓索引從 0 起算，route_step 會從航路起點
    重新比對，把部隊往回送。Run 6 T1 的紅軍守備營因此在原地來回走兩小時。

    單點航路（只給終點、由 plan_path 尋路者）本來就不會命中，屬正常。
    """
    idx = {}
    for uid, route in routes.items():
        u = s["units"].get(uid)
        if not u:
            continue
        hit = [i for i, p in enumerate(route) if list(p) == list(u["pos"])]
        idx[uid] = hit[0] + 1 if hit else 0
        assert hit or len(route) == 1, f"{uid} 不在其航路上：{tuple(u['pos'])}"
    return idx


def route_step(s, uid, route, idx):
    """沿航路的下一個目的地；已到終點回 None。

    ★ Run 6 坑 #2：早期版本取「第一個尚未到達的點」，造成部隊在兩個航點間振盪。
    改為逐編隊記住進度（idx）。
    """
    u = s["units"][uid]
    i = idx.get(uid, 0)
    while i < len(route) and list(u["pos"]) == list(route[i]):
        i += 1
    idx[uid] = i
    return route[i] if i < len(route) else None


def route_advance(s, uid, route, idx, max_hex=4):
    """本小時沿航路盡量前進。回傳訊息列表。

    ★ Run 6 坑 #3：航點是逐格相鄰的，而 advance() 一次只走到給定目標為止。
    若不在此處續走，速度 >1.0 格/hr 的兵種（偵察營 1.5）被硬卡成 1 格/hr。
    反之，若引擎每次呼叫都重複累加疲勞與移動速率，連續呼叫又會超速——
    該問題已於引擎端修正（缺陷 20：兩者皆以 flags["moved"] 判定「本小時第一次移動」），
    故此處可安全連呼。
    """
    msgs = []
    for _ in range(max_hex):
        tgt = route_step(s, uid, route, idx)
        if tgt is None:
            break
        _, m = ar.advance(s, uid, list(tgt))
        msgs.append(m)
        u = s["units"][uid]
        if list(u["pos"]) != list(tgt) or u.get("move_progress", 0.0) < 1.0:
            break
    return msgs


def shadow_target(s, lead, route, back):
    """尾隨編隊的目標＝被跟隨者航路上「後方 back 格」的那一點。

    ★ Run 6 坑 #4：早期版本用 IDX（指向**下一個**航點）推算，慢一拍，
    使尾隨距離多出一格。必須用被跟隨者的**實際現位置**在航路上的索引。
    """
    cur = [i for i, p in enumerate(route) if list(p) == list(s["units"][lead]["pos"])]
    k = cur[0] if cur else 0
    return route[max(0, k - back)]


def cycle_move(s, uid, ring, idx, note="循環巡邏"):
    """沿環狀航點巡邏一小時。回傳訊息或 None。"""
    u = s["units"][uid]
    t = ring[idx.get(uid, 0) % len(ring)]
    if list(u["pos"]) == list(t):
        idx[uid] = idx.get(uid, 0) + 1
        t = ring[idx[uid] % len(ring)]
    _, m = ar.advance(s, uid, list(t))
    return f"{m}（{note}，下一航點 {tuple(t)}）"


# ── 應變：持續性位移 ────────────────────────────────────────────
class Retreat:
    """應變觸發的後撤——**持續動作，走到目的地為止**。

    ★ Run 6 坑 #5：早期版本只在觸發的那一小時呼叫一次移動，
    導致該編隊付出了動作的代價（移動即離開工事）卻沒走到位置，兩頭落空。
    裁示 19 由此確立：應變所觸發的位移類動作應執行至完成或條件消滅為止。
    """

    def __init__(self):
        self.dest = {}

    def start(self, s, uid, dest):
        """登記後撤目的地。**座標會被夾進地圖範圍內。**

        不夾的話，「向西後撤 2 格」對一個已在 x=1 的編隊會算出 x=-1，
        advance() 找不到路徑，該編隊就永遠停在原地——付了代價卻走不到。
        應變條款是自動執行的，不能假設指揮官算過邊界。
        """
        if uid in self.dest:
            return False
        W, H = s["map"]["width"], s["map"]["height"]
        self.dest[uid] = [max(0, min(W - 1, int(dest[0]))),
                          max(0, min(H - 1, int(dest[1])))]
        return True

    def step(self, s):
        """每小時呼叫。回傳 [(uid, 訊息)]。"""
        ev = []
        for uid, dest in list(self.dest.items()):
            u = s["units"].get(uid)
            if not u:
                self.dest.pop(uid)
                continue
            if list(u["pos"]) == list(dest):
                self.dest.pop(uid)
                ev.append((uid, f"{uid} 後撤完成，抵達 {tuple(dest)}"))
                continue
            _, m = ar.advance(s, uid, list(dest))
            ev.append((uid, f"{uid} 後撤中：{m}"))
        return ev

    def cancel(self, uid):
        return self.dest.pop(uid, None)

    def __contains__(self, uid):
        return uid in self.dest


# ── 火力 ────────────────────────────────────────────────────────
def in_range(s, shooter, target_pos):
    u = s["units"][shooter]
    mix = u.get("gun_mix") or ar.GUN_MIX.get(u["type"], {})
    d = ar.dist(u["pos"], target_pos)
    return any(d <= ar.GUN_SPEC[g][2] for g in mix)


def can_fire(s, uid):
    """該編隊本小時是否可實施砲擊：未行軍（裁示 18）、有砲、有彈。"""
    u = s["units"].get(uid)
    return bool(u and not u["flags"].get("moved")
                and u["equip"]["guns"] > 0
                and any((u.get("ammo") or {}).values()))


def nearest_target(s, shooters, side, kinds=None, exclude_pos=None):
    """射程內、距砲群最近的已偵獲敵編隊。

    ★ Run 6 坑 #6（終局那次，值 288 分）：友軍誤擊防護若「挑完最近的再否決」，
    當最近者恰為近戰格時該砲群會變成**完全不射擊**。
    必須在**挑選前**就把 exclude_pos 排除。
    """
    live = [u for u in shooters if u in s["units"]]
    if not live:
        return None
    anchor = s["units"][live[0]]["pos"]
    cands = []
    for e in spotted(s, side):
        u = s["units"].get(e)
        if not u:
            continue
        if kinds and u.get("type") not in kinds:
            continue
        if exclude_pos is not None and list(u["pos"]) == list(exclude_pos):
            continue
        if not any(in_range(s, x, u["pos"]) for x in live):
            continue
        cands.append((ar.dist(anchor, u["pos"]), e))
    return min(cands)[1] if cands else None


def shoot(s, shooters, target, label="砲群", mission="壓制"):
    """對已偵獲編隊直接砲擊並套用損失。回傳 [(uid, 訊息)]。"""
    live = [u for u in shooters if can_fire(s, u)]
    if not live or target not in s["units"]:
        return []
    cas, tk, gk, msg = ar.bombard(s, live, target, mission=mission)
    if not (cas or tk or gk):
        return [(live[0], f"{label} → {target}：{msg}")]
    t = s["units"][target]
    org = ar.org_impact(s, target, 100.0 * cas / max(t.get("personnel", 1), 1))
    ar.hurt(s, target, personnel=cas, tanks=tk, guns=gk, org=org,
            fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
    return [(live[0], f"{label} → {target}：{msg}（組織度 -{org}）"),
            (target, f"{target} 遭敵砲擊：傷亡 {cas} 人"
                     + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else "")
                     + f"、組織度 -{org}")]


def shoot_hex(s, shooters, pos, label="砲群", mission="壓制"):
    """攔阻射擊（對格面、不需偵獲）。回傳 [(uid, 訊息)]。"""
    live = [u for u in shooters if can_fire(s, u)]
    if not live:
        return []
    cas, tk, gk, msg, hit = ar.bombard_hex(s, live, list(pos), mission=mission)
    if hit is None:
        return [(live[0], f"{label} 對 {tuple(pos)} 攔阻射擊：該格無敵編隊，"
                          f"彈藥與暴露照付，效果為零")]
    t = s["units"][hit]
    org = ar.org_impact(s, hit, 100.0 * cas / max(t.get("personnel", 1), 1))
    ar.hurt(s, hit, personnel=cas, tanks=tk, guns=gk, org=org,
            fatigue=ar.fatigue_from_combat("light"), note="遭敵攔阻射擊")
    return [(live[0], f"{label} 對 {tuple(pos)} 攔阻射擊 → {msg}（組織度 -{org}）"),
            (hit, f"{hit} 遭敵攔阻射擊：傷亡 {cas} 人"
                  + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else "")
                  + f"、組織度 -{org}")]


# ── 工事 ────────────────────────────────────────────────────────
def try_dig(s, uid, note="構築工事"):
    """構築工事一小時。已達上限、行軍中、遭干擾射擊者自動略過。回傳訊息或 None。"""
    u = s["units"].get(uid)
    if not u or u.get("dig_hours", 0.0) >= ar.FORT_TIERS[-1][0]:
        return None
    r = ar.dig(s, uid)
    if not r:
        return None
    return f"{uid} {note} → {r[0]}（{u['dig_hours']:.2f}hr/人，暴露 {r[2]}）"


def try_camouflage(s, uid):
    """偽裝作業一小時（裁示 17）。回傳訊息或 None。"""
    u = s["units"].get(uid)
    if not u or u.get("camouflaged"):
        return None
    r = ar.camouflage(s, uid)
    if not r:
        return None
    return (f"{uid} 偽裝作業 → {r[0]:.2f}/{ar.CAMO_HOURS} 工時"
            + ("　★完成，靜止時能見狀態好一級" if r[1] else ""))


# ── 近戰的強制後退 ──────────────────────────────────────────────
def forced_push(s, uid, hexes, ev=None):
    """`FR_TABLE` 的「守方後退 N 格」——**強制位移，不是行軍**。

    ★ Run 7 T8 揭露的錯誤：初版以 `ar.advance()` 執行逼退，於是位移受**移動速率**
      限制。一個 org 歸零、疲勞爆表的編隊每小時只挪得動 0.05–0.8 格，
      於是「被逼退 3 格」實際等於**留在原格繼續挨打**——RED-SF 因此連續六小時
      被同一群部隊近戰，累計 2,122 人。

      `law/law_of_war.md` 早已把這件事列為 Run 4 的**缺陷 9**：
      「一個編隊 org 掉到 0 也只會站在原地繼續挨打，既不潰散、**不強制後退**。」
      狀態機後來補了 ROUTED／SURRENDERED，但強制後退這一半沒補。

    正確語意：部隊被逐出陣地，不是自己選擇行軍。故**不受移動速率、疲勞、POL 限制**，
    只受地形可通行性與地圖邊界限制。方向為該方補給源（allies 向西、axis 向東）。

    逼退後工事防護歸零（人離開了洞），`abandon_works` 一併處理。
    回傳實際後退格數。
    """
    u = s["units"].get(uid)
    if not u or hexes <= 0:
        return 0
    W, H = s["map"]["width"], s["map"]["height"]
    step = -1 if u["side"] == "allies" else 1
    x, y = int(u["pos"][0]), int(u["pos"][1])
    moved = 0
    for _ in range(int(hexes)):
        nx = x + step
        if not (0 <= nx < W):
            break
        if not ar._passable(u, ar.terr(s, (nx, y))):
            # 正面不可通行 → 試斜後方（仍朝本方補給源）
            alt = [(nx, y + dy) for dy in (-1, 1)
                   if 0 <= y + dy < H and ar._passable(u, ar.terr(s, (nx, y + dy)))]
            if not alt:
                break
            nx, y = alt[0]
        x = nx
        moved += 1
    if moved:
        u["pos"] = [x, y]
        u["flags"]["moved"] = True          # 被逐離陣地：該小時不得構工／射擊
        ar.abandon_works(u)
        u["last_action"] = f"遭近戰逼退 {moved} 格"
        if ev is not None:
            ev.append((uid, f"{uid} 遭強制後退 {moved} 格 → {tuple(u['pos'])}"
                            f"（逼退為強制位移，不受移動速率限制；工事防護歸零）"))
    return moved
