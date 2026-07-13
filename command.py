#!/usr/bin/env python3
"""指揮所、通訊延遲、斬首 — PvP『純戰場』機制（scenario_open_field.md §5-B）。

純邏輯、裁判結算時呼叫。三段延遲階梯：
  未建指揮所      → +2 級（軍長隨隊臨時指揮，最慢）
  主指揮所        → +1 級
  前進指揮所(罩內) → 基準（0）

指揮所皆由玩家下令建立、架設 CP_SETUP_HOURS 小時才生效。
斬首：敵佔軍長所在指揮所格 → 該方即敗。

state["command"][side] = {
    "main_cp": [x,y]|None, "fwd_cp": [x,y]|None,
    "commander_at": "main"|"fwd"|None,
    "pending_cp": [ {"kind","pos","effective_gh"} ... ],
}
"""
from hourstate import LEVEL_DELAY

CP_SETUP_HOURS = 2     # 指揮所架設時間
FWD_RANGE = 6          # 前進指揮所罩住的格數


def _dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))   # 切比雪夫距離（八向）


def delay_tier_adjust(state, side, unit_pos):
    """該單位命令的延遲級數調整：0(前進指揮所罩內) / +1(有主指揮所) / +2(無指揮所)。"""
    cmd = state.get("command", {}).get(side, {})
    fwd, main, at = cmd.get("fwd_cp"), cmd.get("main_cp"), cmd.get("commander_at")
    if fwd and at == "fwd" and _dist(unit_pos, fwd) <= FWD_RANGE:
        return 0
    if main:
        return 1
    return 2


def command_delay(state, side, level, unit_pos):
    """實際延遲小時 = 基準(L1/L2/L3) + CP 調整。"""
    return LEVEL_DELAY[level] + delay_tier_adjust(state, side, unit_pos)


def establish_cp(state, side, kind, pos):
    """玩家下令建立指揮所（kind='main'/'fwd'）。CP_SETUP_HOURS 小時後生效。回傳生效 global_hour。"""
    if kind not in ("main", "fwd"):
        raise ValueError(f"kind 須為 main/fwd，不是 {kind!r}")
    cmd = state.setdefault("command", {}).setdefault(side, {})
    gh = state.get("global_hour", 0)
    eff = gh + CP_SETUP_HOURS
    cmd.setdefault("pending_cp", []).append({"kind": kind, "pos": list(pos), "effective_gh": eff})
    return eff


def activate_due_cps(state):
    """把架設完成的指揮所啟用（裁判每 hour 呼叫）。回傳剛啟用 [(side,kind,pos)]。"""
    gh = state.get("global_hour", 0)
    fired = []
    for side, cmd in state.get("command", {}).items():
        still = []
        for p in cmd.get("pending_cp", []):
            if p["effective_gh"] <= gh:
                cmd[f"{p['kind']}_cp"] = p["pos"]
                cmd["commander_at"] = p["kind"]          # 軍長進駐剛建好的指揮所
                fired.append((side, p["kind"], p["pos"]))
            else:
                still.append(p)
        cmd["pending_cp"] = still
    return fired


def cp_hexes(state, side):
    """回傳該方已啟用的指揮所位置 {'main':pos,'fwd':pos}（未建者不列）。"""
    cmd = state.get("command", {}).get(side, {})
    return {k: cmd[f"{k}_cp"] for k in ("main", "fwd") if cmd.get(f"{k}_cp")}


def decapitation(state):
    """斬首偵測：若某方軍長所在指揮所格被敵單位佔據 → 回傳該方(敗者)。無則 None。
    （裁判仲裁突襲成功後即可據此判即敗；此函式做幾何偵測。）"""
    units = state.get("units", {})
    for side, cmd in state.get("command", {}).items():
        at = cmd.get("commander_at")
        cp = cmd.get(f"{at}_cp") if at else None
        if not cp:
            continue
        for u in units.values():
            if u.get("side") and u["side"] != side and list(u["pos"]) == list(cp):
                return side          # 軍長 CP 被敵佔 → 該方斬首落敗
    return None


if __name__ == "__main__":
    # ── self-test ──
    s = {"global_hour": 0, "command": {
        "allies": {"main_cp": None, "fwd_cp": None, "commander_at": None},
        "axis": {"main_cp": None, "fwd_cp": None, "commander_at": None}}}
    assert delay_tier_adjust(s, "allies", (5, 5)) == 2           # 未建 → +2
    establish_cp(s, "allies", "main", (0, 9))
    assert delay_tier_adjust(s, "allies", (5, 5)) == 2           # 架設中、還沒生效
    s["global_hour"] = 2
    assert activate_due_cps(s) == [("allies", "main", [0, 9])]   # 2hr 後生效
    assert delay_tier_adjust(s, "allies", (5, 5)) == 1           # 主指揮所 → +1
    establish_cp(s, "allies", "fwd", (12, 9)); s["global_hour"] = 4; activate_due_cps(s)
    assert delay_tier_adjust(s, "allies", (14, 9)) == 0          # 前進 CP 罩內 → 基準
    assert delay_tier_adjust(s, "allies", (25, 9)) == 1          # 罩外、但有主 CP → +1
    assert command_delay(s, "allies", "L2", (14, 9)) == 2        # 基準 L2=2
    assert command_delay(s, "allies", "L2", (25, 9)) == 3        # +1 → 3
    # 斬首：敵佔軍長 fwd CP (12,9)
    s["units"] = {"RED-SF": {"side": "axis", "pos": [12, 9]}}
    assert decapitation(s) == "allies"
    print("command.py self-test OK — 三段延遲 + 架設計時 + 斬首偵測")
