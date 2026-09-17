"""一級動詞登錄表：裁判能呼叫的全部動作，每個都是 arbiter.py 既有函式的薄封裝。

封裝裡只放以前每支 tick 腳本都重寫的那幾行（自 runs/_tickkit.py 與 run7 t5.py 逐行對應），
不新增規則。管線鉤子（補給、消耗、能見、組織度恢復、狀態機、日誌、清旗）一律不在此表。

每個動詞回傳 [(target, text)] 事件清單（push_log 的契約：target 為 uid／陣營／"both"），
另外把引擎回傳值放進 result 供決定紀錄的 execution 區段記錄。

二級動作只能用 PRIMITIVES 白名單裡的原語；白名單裡沒有任何能**增加**人員、裝備、彈藥的原語。
"""
from dataclasses import dataclass, field
from typing import Any, Callable

import arbiter as ar
import command
import hourstate as hs

MISSIONS = tuple(ar.FIRE_MISSION)          # 火力任務型態，自引擎取
MAX_MARCH_STEPS = 4                        # _tickkit.route_advance 的 max_hex


@dataclass
class Outcome:
    events: list = field(default_factory=list)   # [(target, text)]
    result: Any = None                            # 引擎回傳值（可序列化的摘要）
    applied: bool = True                          # 引擎是否真的做了事


@dataclass
class Verb:
    name: str
    zh: str
    params: dict                       # 參數名 → 型別說明（給動詞目錄與綱要用）
    fn: Callable[..., Outcome]
    doc: str
    register_only: bool = False        # 只准在登記卷宗（tick 首小時之前）使用
    primary: bool = True               # 是否算「主動作」（每受指揮編隊每小時恰一個）


# ── 共用小工具（與 _tickkit 相同語意）───────────────────────────
def can_fire(s, uid):
    u = s["units"].get(uid)
    return bool(u and not u["flags"].get("moved")
                and u["equip"]["guns"] > 0
                and any((u.get("ammo") or {}).values()))


def in_range(s, shooter, target_pos):
    u = s["units"][shooter]
    mix = u.get("gun_mix") or ar.GUN_MIX.get(u["type"], {})
    d = ar.dist(u["pos"], target_pos)
    return any(d <= ar.GUN_SPEC[g][2] for g in mix)


def _loss_text(cas, tk, gk):
    return (f"傷亡 {cas} 人" + (f"、戰車 -{tk}" if tk else "") + (f"、火砲 -{gk}" if gk else ""))


# ── 一級動詞 ───────────────────────────────────────────────────
def v_march(s, uid, dest):
    """朝 dest 行軍一小時；速度 >1 格/時的兵種連呼至走完（_tickkit.route_advance 的迴圈）。
    裁示 47 護欄（不得走進敵佔格）在 advance 內。"""
    u = s["units"][uid]
    dest = [int(dest[0]), int(dest[1])]
    msgs = []
    for _ in range(MAX_MARCH_STEPS):
        if list(u["pos"]) == dest:
            break
        moved, m = ar.advance(s, uid, dest)
        msgs.append(m)
        if not moved or u.get("move_progress", 0.0) < 1.0:
            break
    if not msgs:
        return Outcome([(uid, f"{uid} 已在目標格 {tuple(dest)}")], {"moved": False}, applied=False)
    return Outcome([(uid, m) for m in msgs], {"moved": True, "pos": list(u["pos"])})


def v_hold(s, uid):
    """零效果宣告：讓「每個受指揮編隊每小時恰一個主動作」成為可檢查的完整性條件。"""
    return Outcome([], {"held": True}, applied=False)


def v_dig(s, uid):
    r = ar.dig(s, uid)
    if r is None:
        return Outcome([(uid, f"{uid} 本小時無法構工（行軍中、不受指揮或遭干擾）")], None, applied=False)
    tier, fort, exp = r
    return Outcome([(uid, f"{uid} 構工：{tier}（工事 {fort:.2f}，暴露 {exp:.2f}）")],
                   {"tier": tier, "fortification": fort, "exposure": exp})


def v_camouflage(s, uid):
    r = ar.camouflage(s, uid)
    if r is None:
        return Outcome([(uid, f"{uid} 本小時無法偽裝（行軍中、不受指揮或遭干擾）")], None, applied=False)
    hours, done = r
    return Outcome([(uid, f"{uid} 偽裝作業 {hours:.1f}/{ar.CAMO_HOURS} 工時" + ("，完成" if done else ""))],
                   {"camo_hours": hours, "done": bool(done)})


def v_fire(s, shooters, target, mission="壓制"):
    """對已偵獲編隊砲擊並套用損失（_tickkit.shoot）。同一小時同一目標只准一筆（裁示 63）。"""
    live = [u for u in shooters if can_fire(s, u)]
    if not live or target not in s["units"]:
        return Outcome([(shooters[0], f"砲群 → {target}：無可射擊之編隊")], None, applied=False)
    cas, tk, gk, msg = ar.bombard(s, live, target, mission=mission)
    if not (cas or tk or gk):
        return Outcome([(live[0], f"砲群 → {target}：{msg}")], {"cas": 0, "tanks": 0, "guns": 0, "org": 0})
    t = s["units"][target]
    org = ar.org_impact(s, target, 100.0 * cas / max(t.get("personnel", 1), 1))
    ar.hurt(s, target, personnel=cas, tanks=tk, guns=gk, org=org,
            fatigue=ar.fatigue_from_combat("light"), note="遭敵砲擊")
    return Outcome([(live[0], f"砲群 → {target}：{msg}（組織度 -{org}）"),
                    (target, f"{target} 遭敵砲擊：{_loss_text(cas, tk, gk)}、組織度 -{org}")],
                   {"cas": cas, "tanks": tk, "guns": gk, "org": org, "shooters": live})


def v_barrage(s, shooters, hex, mission="壓制"):
    """攔阻射擊（對格面、不需偵獲；_tickkit.shoot_hex）。"""
    live = [u for u in shooters if can_fire(s, u)]
    pos = (int(hex[0]), int(hex[1]))
    if not live:
        return Outcome([(shooters[0], f"砲群 對 {pos} 攔阻射擊：無可射擊之編隊")], None, applied=False)
    cas, tk, gk, msg, hit = ar.bombard_hex(s, live, list(pos), mission=mission)
    if hit is None:
        return Outcome([(live[0], f"砲群 對 {pos} 攔阻射擊：該格無敵編隊，彈藥與暴露照付，效果為零")],
                       {"hit": None, "shooters": live})
    t = s["units"][hit]
    org = ar.org_impact(s, hit, 100.0 * cas / max(t.get("personnel", 1), 1))
    ar.hurt(s, hit, personnel=cas, tanks=tk, guns=gk, org=org,
            fatigue=ar.fatigue_from_combat("light"), note="遭敵攔阻射擊")
    return Outcome([(live[0], f"砲群 對 {pos} 攔阻射擊 → {msg}（組織度 -{org}）"),
                    (hit, f"{hit} 遭敵攔阻射擊：{_loss_text(cas, tk, gk)}、組織度 -{org}")],
                   {"hit": hit, "cas": cas, "tanks": tk, "guns": gk, "org": org, "shooters": live})


def defenders_at(s, side, hexpos):
    """該格內敵方仍具戰鬥資格的編隊（裁示 56：守方全格自動參戰）。side 為攻方。"""
    enemy = ar.ENEMY[side]
    return [uid for uid, u in s["units"].items()
            if u.get("side") == enemy and list(u["pos"]) == list(hexpos)
            and ar.status_of(u) in ar.COMBAT_STATUSES]


def v_assault(s, attackers, hex):
    """近戰突擊（裁示 47／56）。守軍由狀態推得，裁判不得指定；逼退由 battle 自做；
    守軍清出則攻方進駐並棄工事（t5.py do_assault，去掉已由引擎接手的 forced_push）。"""
    hexpos = [int(hex[0]), int(hex[1])]
    side = s["units"][attackers[0]]["side"]
    defs = defenders_at(s, side, hexpos)
    atks = [a for a in attackers if a in s["units"]
            and ar.dist(s["units"][a]["pos"], hexpos) == 1 and ar.under_command(s, a)]
    if not defs:
        return Outcome([(attackers[0], f"突擊 {tuple(hexpos)}：該格無敵戰鬥編隊，改以行軍進入")], None, applied=False)
    if not atks:
        return Outcome([(attackers[0], f"突擊 {tuple(hexpos)}：受命編隊皆未抵相鄰格或不受指揮")], None, applied=False)
    detail, res = ar.battle(s, atks, defs, hexpos)
    ev = [(atks[0], f"★近戰突擊 {tuple(hexpos)}：{detail}")]
    ev += [(d, f"★遭 {'／'.join(atks)} 近戰突擊於 {tuple(hexpos)}：{detail}") for d in defs]
    still = [d for d in defs if list(s["units"][d]["pos"]) == hexpos
             and ar.status_of(s["units"][d]) in ar.COMBAT_STATUSES]
    captured = False
    if not still:
        captured = True
        for a in atks:
            s["units"][a]["pos"] = list(hexpos)
            ar.abandon_works(s["units"][a])
            ev.append((a, f"{a} 奪下 {tuple(hexpos)} 並進駐"))
    return Outcome(ev, {"attackers": atks, "defenders": defs, "push": res.push,
                        "side_pushed": res.side_pushed, "displaced": dict(res.displaced),
                        "captured": captured})


def v_detach(s, div, code, pos):
    uid, _u = ar.detach_bn(s, div, code, list(pos))
    return Outcome([(uid, f"{div} 抽離 {code} 營為 {uid} 於 {tuple(pos)}")], {"uid": uid})


def v_rejoin(s, uid):
    parent = ar.rejoin_bn(s, uid)
    return Outcome([(parent, f"{uid} 歸建 {parent}")], {"parent": parent})


def v_establish_cp(s, side, kind, pos):
    eff = command.establish_cp(s, side, kind, list(pos))
    zh = {"main": "主指揮所", "fwd": "前進指揮所"}[kind]
    return Outcome([(side, f"下令於 {tuple(pos)} 建立{zh}，gh{eff} 生效")], {"effective_gh": eff})


def v_register_clause(s, side, level, text, unit_uids):
    """把一條命令條款送進延遲佇列；延遲由引擎依指揮所階梯計算，裁判不填。"""
    pos = s["units"][unit_uids[0]]["pos"] if unit_uids and unit_uids[0] in s["units"] else [0, 0]
    extra = command.delay_tier_adjust(s, side, pos)
    o = hs.enqueue_order(s, side, level, text, extra_delay=extra)
    return Outcome([(side, f"命令登記：{level}＋指揮所階梯 {extra} → gh{o['effective_global_hour']} 生效")],
                   {"order_id": o["id"], "effective_gh": o["effective_global_hour"], "extra_delay": extra})


def v_legal_order(s, kind, uid, by_uid=None):
    """示降／受降：由執行器直接呼叫，不走 run_tick 內的 apply_due_legal_orders
    （該路徑因 hour_brief 先把到期令標成生效而永不觸發；v1 問題另立項目）。"""
    if kind == "declare":
        ok, msg = ar.declare_surrender(s, uid)
        return Outcome([(uid, msg)], {"ok": ok}, applied=ok)
    if kind == "accept":
        r = ar.accept_surrender(s, uid, by_uid=by_uid)
        if r is None:
            return Outcome([(uid, f"受降 {uid}：條件不成立")], None, applied=False)
        return Outcome([(uid, f"{uid} 受降：俘 {r['pow']} 人，由 {r['captor']} 看押")], r)
    raise ValueError(f"legal_order.kind 須為 declare/accept，不是 {kind!r}")


VERBS = {v.name: v for v in [
    Verb("march", "行軍", {"uid": "編隊", "dest": "[x,y]"}, v_march, v_march.__doc__),
    Verb("hold", "待機", {"uid": "編隊"}, v_hold, v_hold.__doc__),
    Verb("dig", "構工", {"uid": "編隊"}, v_dig, "構築工事一小時（arbiter.dig）。"),
    Verb("camouflage", "偽裝", {"uid": "編隊"}, v_camouflage, "偽裝作業一小時（arbiter.camouflage）。"),
    Verb("fire", "砲擊", {"shooters": "[編隊]", "target": "已偵獲敵編隊", "mission": f"{'/'.join(MISSIONS)}"},
         v_fire, v_fire.__doc__),
    Verb("barrage", "攔阻射擊", {"shooters": "[編隊]", "hex": "[x,y]", "mission": f"{'/'.join(MISSIONS)}"},
         v_barrage, v_barrage.__doc__),
    Verb("assault", "近戰突擊", {"attackers": "[編隊]", "hex": "[x,y]"}, v_assault, v_assault.__doc__),
    Verb("detach", "抽離", {"div": "師", "code": "營碼", "pos": "[x,y]"}, v_detach, "抽離一個營（arbiter.detach_bn）。", primary=False),
    Verb("rejoin", "歸建", {"uid": "抽離營"}, v_rejoin, "歸建（arbiter.rejoin_bn）。", primary=False),
    Verb("establish_cp", "建立指揮所", {"side": "陣營", "kind": "main/fwd", "pos": "[x,y]"},
         v_establish_cp, "建立指揮所，兩小時後生效（command.establish_cp）。", register_only=True, primary=False),
    Verb("register_clause", "登記條款", {"side": "陣營", "level": "L1/L2/L3", "text": "條款原文", "unit_uids": "[編隊]"},
         v_register_clause, v_register_clause.__doc__, register_only=True, primary=False),
    Verb("legal_order", "法律命令", {"kind": "declare/accept", "uid": "編隊", "by_uid": "受降方編隊（可省）"},
         v_legal_order, v_legal_order.__doc__, primary=False),
]}

# 二級原語：只能出現在裁示的 applied 內。沒有任何原語能增加人員、裝備、彈藥。
PRIMITIVES = {
    "hurt": lambda s, uid, **kw: ar.hurt(s, uid, **kw),
    "forced_push": lambda s, uid, hexes: ar.forced_push(s, uid, int(hexes)),
    "force_retreat": lambda s, uid, note="裁示後撤": ar.force_retreat(s, uid, note=note),
    "add_works": lambda s, pos, man_hours, side=None, by_uid=None: ar.add_works(s, list(pos), float(man_hours), side=side, by_uid=by_uid),
    "damage_works": lambda s, pos, man_hours, occupant=None: ar.damage_works(s, list(pos), float(man_hours), occupant=occupant),
    "abandon_works": lambda s, uid: ar.abandon_works(s["units"][uid]),
    "consume": lambda s, uid, level="L1": ar.consume(s, uid, level),
}
# hurt 只准減少：引數必須非負
_HURT_KEYS = ("personnel", "tanks", "guns", "org", "str_pct", "fatigue")


def check_primitive_args(name, args):
    """白名單與守恆方向的靜態檢查。回傳問題清單。"""
    if name not in PRIMITIVES:
        return [f"原語 {name!r} 不在白名單"]
    if name == "hurt":
        bad = [k for k in _HURT_KEYS if k in args and float(args[k]) < 0]
        return [f"hurt.{k} 為負（原語不得增加人員／裝備）" for k in bad]
    if name in ("add_works", "damage_works") and float(args.get("man_hours", 0)) < 0:
        return [f"{name}.man_hours 為負"]
    if name == "forced_push" and int(args.get("hexes", 0)) <= 0:
        return ["forced_push.hexes 須為正整數"]
    return []


def render_catalogue():
    """給卷宗前綴 A2 的動詞目錄（確定性文字）。"""
    lines = ["# 一級動詞目錄（裁判只能呼叫這些；每個都是引擎既有函式）", ""]
    for v in VERBS.values():
        flags = []
        if v.register_only: flags.append("只在登記卷宗")
        if not v.primary: flags.append("非主動作")
        lines.append(f"- **{v.name}**（{v.zh}）參數 {v.params}" + (f"　［{'；'.join(flags)}］" if flags else ""))
        lines.append(f"  {' '.join((v.doc or '').split())}")
    lines += ["", "# 二級原語白名單（只能出現在裁示的 applied 內，皆為減少或位移，無任何增加）", ""]
    lines += [f"- {k}" for k in PRIMITIVES]
    return "\n".join(lines)
