"""單一迷霧投影：某一方能看到的狀態。

取代 mapcore.filter_state_for（頂層鍵允許為預設，實測會外洩敵指揮所座標、敵工事、
敵方逐小時日誌）。本投影**頂層鍵一律白名單**，每個鍵各自定義該方能看到的部分。
後端絕不回傳未投影的狀態；"god" 視角只給裁判席與終局。
"""
import copy

import arbiter as ar

SIDES = ("allies", "axis")

# 敵方已偵獲編隊的公開欄位（與 mapcore._ENEMY_PUBLIC 相同）＋概略兵力＋工事粗分級
ENEMY_PUBLIC = ("side", "short", "name", "type", "pos", "visibility_state", "hidden")

# 與陣營無關、雙方本來就都知道的頂層鍵
NEUTRAL_KEYS = ("scenario_name", "scenario_id", "mode", "tick", "max_ticks", "map",
                "hour_in_tick", "global_hour", "game_time", "phase", "weather_state",
                "objectives", "supply_note", "victory_state")


def fort_bucket(u):
    """敵情欄的工事粗分級（arbiter.enemy_lines 的三檔）。"""
    f0 = float(u.get("fortification", 0.0) or 0.0)
    return "未構築" if f0 <= 0 else ("構築中" if f0 < 0.5 else "已完成")


def strength_approx(u):
    st = u.get("strength")
    return int(round(st / 10.0) * 10) if isinstance(st, (int, float)) else None


def project(state, side):
    """回傳 side 視角的新狀態（深拷貝，不動原狀態）。side ∈ allies / axis / god。"""
    if side == "god":
        return copy.deepcopy(state)
    if side not in SIDES:
        raise ValueError(f"未知陣營 {side!r}")
    s = state
    fog = s.get("fog_of_war", {})
    spotted = set(fog.get(f"{side}_spotted", []))
    out = {k: copy.deepcopy(s[k]) for k in NEUTRAL_KEYS if k in s}

    units = {}
    for uid, u in s["units"].items():
        if u.get("side") == side:
            units[uid] = copy.deepcopy(u)
        elif uid in spotted:
            pub = {k: copy.deepcopy(u[k]) for k in ENEMY_PUBLIC if k in u}
            pub["strength_approx"] = strength_approx(u)
            pub["fortification_bucket"] = fort_bucket(u)
            units[uid] = pub
    out["units"] = units

    out["fog_of_war"] = {f"{side}_spotted": sorted(spotted),
                         f"{side}_spotted_cps": sorted(fog.get(f"{side}_spotted_cps", [])),
                         "_note": fog.get("_note", "")}
    # 指揮所：只給自己的。敵指揮所要靠偵察，偵獲紀錄在 fog_of_war 的 *_spotted_cps。
    out["command"] = {side: copy.deepcopy(s.get("command", {}).get(side, {}))}
    # 工事：只給本方挖的格。敵方工事程度透過敵情欄的粗分級給。
    out["works"] = {k: copy.deepcopy(v) for k, v in s.get("works", {}).items()
                    if v.get("by") == side}
    out["pending_orders"] = [copy.deepcopy(o) for o in s.get("pending_orders", [])
                             if o.get("side") == side]
    out["standing_orders"] = {side: s.get("standing_orders", {}).get(side, "")}
    # 逐小時日誌：只有 push_log 已分流過的本方那份；全知的 hour_log 與 record 一律不給。
    out["hour_log_side"] = {side: list(s.get("hour_log_side", {}).get(side, []))}
    out["score"] = {k: {"points": v["points"]} for k, v in ar.score(s).items()}   # 計分雙方公開
    return out


def assert_no_leak(projected, state, side):
    """投影結果的機械檢查：不得含未偵獲敵編隊、敵指揮所、敵方工事、敵方日誌。回傳問題清單。"""
    enemy = ar.ENEMY[side]
    spotted = set(state.get("fog_of_war", {}).get(f"{side}_spotted", []))
    bad = []
    for uid, u in state["units"].items():
        if u.get("side") == enemy and uid not in spotted and uid in projected["units"]:
            bad.append(f"未偵獲敵編隊 {uid} 出現在投影")
    for uid, u in projected["units"].items():
        if u.get("side") == enemy and set(u) - set(ENEMY_PUBLIC) - {"strength_approx", "fortification_bucket"}:
            bad.append(f"敵編隊 {uid} 洩露非公開欄位 {sorted(set(u) - set(ENEMY_PUBLIC))}")
    if enemy in projected.get("command", {}):
        bad.append("敵方指揮所整包外洩")
    if any(v.get("by") == enemy for v in projected.get("works", {}).values()):
        bad.append("敵方工事外洩")
    if enemy in projected.get("hour_log_side", {}):
        bad.append("敵方逐小時日誌外洩")
    for k in ("hour_log", "record", "push_ledger", "works_ledger", "pending_precedents"):
        if k in projected:
            bad.append(f"全知鍵 {k} 出現在投影")
    if any(o.get("side") == enemy for o in projected.get("pending_orders", [])):
        bad.append("敵方延遲命令外洩")
    return bad
