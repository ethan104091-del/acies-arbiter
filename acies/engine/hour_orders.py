"""決定紀錄 → runs/_manifest.TickOrders，讓 v1 的 _audit 六項授權檢查（A3–A8）直接可用。

出處字串格式「{陣營} T{tick} {條款} gh{gh}」，內含 T{tick} 以通過 TickOrders.validate()。
assault 的攻守雙方直接登記為 triggered，不依賴 _audit 對日誌字串的辨識。
"""
import _manifest
import arbiter as ar

ZH = {"allies": "藍軍", "axis": "紅軍"}


def _src(act, tick, gh):
    p = act.get("provenance", {})
    return f"{ZH.get(p.get('side'), p.get('side'))} T{tick} {p.get('clause_id', '?')} gh{gh}"


def to_manifest(s, decision, tick, gh, prior_decisions=()):
    """prior_decisions：本 tick 已落定的前幾小時決定紀錄。
    v1 的 A3／A4 對照的是**整個 tick** 的構工帳與位置變化，所以前幾小時登記過的構工、偽裝、
    目的地必須一併帶進本小時的命令清單，否則「前小時挖過、本小時改做別的」會被誤判為無令構工。"""
    mf = _manifest.TickOrders(tick)
    for prev in prior_decisions:
        _register(s, mf, prev, tick, prev.get("gh", gh))
    _register(s, mf, decision, tick, gh)
    return mf


def _register(s, mf, decision, tick, gh):
    for act in decision.get("actions", []):
        if act.get("tier", 1) != 1:
            continue
        v, a, src = act["verb"], act["args"], _src(act, tick, gh)
        if v == "march":
            mf.march(a["uid"], a["dest"], src)
        elif v == "hold":
            u = s["units"].get(a["uid"])
            if u:
                mf.march(a["uid"], u["pos"], src)      # 待機＝目的地為現位（A4 需每個未動編隊有目的地）
        elif v == "dig":
            mf.dig_order(a["uid"], src)
        elif v == "camouflage":
            mf.camo_order(a["uid"], src)
        elif v == "fire":
            mf.fire_mission(a["shooters"], src, target=a["target"], mission=a.get("mission", "壓制"))
        elif v == "barrage":
            mf.barrage_order(a["shooters"], a["hex"], src)
        elif v == "assault":
            side = s["units"][a["attackers"][0]]["side"]
            for u in a["attackers"]:
                mf.contingency_fired(u, src)
                mf.march(u, a["hex"], src)
            enemy = ar.ENEMY[side]
            for uid, u in s["units"].items():
                if u.get("side") == enemy and list(u["pos"]) == list(a["hex"]):
                    mf.contingency_fired(uid, src)
        p = act.get("provenance", {})
        if p.get("clause_id", "").find("應變") >= 0:
            for uid in _units_of(a):
                mf.contingency_fired(uid, src)


def _units_of(args):
    out = []
    for k in ("uid", "shooters", "attackers"):
        v = args.get(k)
        if isinstance(v, str): out.append(v)
        elif isinstance(v, list): out.extend(v)
    return out
