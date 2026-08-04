#!/usr/bin/env python3
"""解算後自我稽核清單 — `docs/TODO.md` P6-14 的制度性修正。

## 為什麼存在

Run 6 終局，裁判在**看到雙方僅差 7 分之後**才繼續深挖，發現「從行軍中接戰 ×0.7」
被誤用為整場交戰的持久標籤。修正後計分由「紅軍勝 7 分」變為「藍軍勝 769 分」。

修正本身是對的（執行錯誤，非規則變更），但**裁判的稽核努力是不對稱的**——
若首次結果即為一方大勝，該錯誤極可能不會被發現。
這使「修正的方向」與「當時誰落後」之間存在無法排除的相關性。
完整記錄見 `law/precedents.md` §十二。

## 用法：稽核通過才准印計分

    import sys; sys.path.insert(0, str(Path(__file__).parent))
    import _audit

    before = _audit.snapshot(s)          # ← run_tick 之前
    lines = ar.run_tick(s, resolve, hours=6, log=log)
    ar.save(s)

    _audit.require_clean(s, before)      # ← 有問題就在這裡 raise，計分印不出來
    print(f"計分：藍 {sc['allies']['points']} : 紅 {sc['axis']['points']}")

**裁判不得在看到計分之後才開始找錯。** 這支腳本的唯一目的是把那個順序倒過來，
讓它成為機械性的、與結果無關的。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arbiter as ar          # noqa: E402

SIDES = ("allies", "axis")


def snapshot(s):
    """解算前的守恆基準。只記稽核需要的量。"""
    return {
        "gh": s.get("global_hour"),
        "units": {
            uid: {
                "personnel": u.get("personnel", 0),
                "losses": dict(u["losses"]),
                "tanks": u["equip"]["tanks"],
                "guns": u["equip"]["guns"],
                "ammo": dict(u.get("ammo", {})),
                "pos": list(u["pos"]),
            }
            for uid, u in s["units"].items() if u.get("side") in SIDES
        },
        "works": {k: v.get("man_hours", 0.0) for k, v in s.get("works", {}).items()},
    }


# ── 個別檢查。每個回傳 [(嚴重度, 說明)]，空列表＝通過 ────────────────
def check_conservation(s, b):
    """裝備與人員守恆：減少量必須等於登記的損失。"""
    out = []
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES or uid not in b["units"]:
            continue
        o = b["units"][uid]
        for k, eq in (("personnel", None), ("tanks", "tanks"), ("guns", "guns")):
            now = u.get(k, 0) if eq is None else u["equip"][eq]
            was = o[k]
            dl = u["losses"][k] - o["losses"][k]
            # 抽離／歸建會改變 personnel 與 equip 而不計入 losses，故只查「減少多於損失」
            if was - now > dl + 0.5 and not u.get("is_detachment"):
                out.append(("警告", f"{uid} 的 {k} 減少 {was - now} 但只登記損失 {dl}"
                                    f"（抽離／歸建會造成此差異，須人工確認）"))
    return out


def check_ammo(s, b):
    """彈藥不得為負；不得無故增加（只有 resupply 能增加）。"""
    out = []
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES:
            continue
        for g, v in (u.get("ammo") or {}).items():
            if v < -1e-6:
                out.append(("錯誤", f"{uid} 的 {g} 彈藥為負：{v}"))
            cap = (u.get("ammo_max") or {}).get(g)
            if cap is not None and v > cap + 1e-6:
                out.append(("錯誤", f"{uid} 的 {g} 彈藥 {v} 超過基數上限 {cap}"))
    return out


def check_friendly_fire(s, b):
    """友軍誤擊的自傷帳不得超過總損失，且必須有對應的事實紀錄（TODO P6-16）。"""
    out = []
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES:
            continue
        slf = u.get("losses_self") or {}
        for k, v in slf.items():
            if v > u["losses"].get(k, 0) + 1e-6:
                out.append(("錯誤", f"{uid} 的自傷 {k}={v} 超過總損失 "
                                    f"{u['losses'].get(k, 0)}"))
        if any(slf.values()):
            has = any(f.get("kind") == "友軍誤擊" and f.get("victim") == uid
                      for f in s.get("record", []))
            if not has:
                out.append(("錯誤", f"{uid} 有自傷帳但事實紀錄中無對應的友軍誤擊條目"))
    return out


def check_fire_legality(s, b):
    """裁示 18：該小時行軍過的編隊不得砲擊。以最終旗標抽驗。"""
    out = []
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES:
            continue
        if u["flags"].get("moved") and u["flags"].get("fired"):
            out.append(("錯誤", f"{uid} 同一小時內既行軍又開火（違反裁示 18）"
                                f"——除非那是近戰（battle），近戰不受此限"))
    return out


def check_works(s, b):
    """工事：man_hours 不得為負；移動過的編隊不得仍有防護。"""
    out = []
    for k, w in (s.get("works") or {}).items():
        if w.get("man_hours", 0) < -1e-6:
            out.append(("錯誤", f"格 {k} 的 man_hours 為負：{w['man_hours']}"))
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES:
            continue
        if u["flags"].get("moved") and u.get("fortification", 0) > 0:
            out.append(("錯誤", f"{uid} 該小時移動過卻仍有工事防護 "
                                f"{u['fortification']}（人不在洞裡）"))
    return out


def check_tactical_state(s, b):
    """戰術狀態的裁判覆寫必須留痕（battle 會把覆寫寫進明細）。"""
    out = []
    for line in s.get("hour_log", [])[-64:]:
        if "裁判覆寫戰術狀態" in line:
            out.append(("注意", f"本 tick 有裁判覆寫戰術狀態，須在裁示中說明：{line[:70]}"))
    return out


def check_status_machine(s, b):
    """狀態與門檻的一致性：org 在合法範圍、潰散/投降門檻未被跳過。"""
    out = []
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES:
            continue
        org = u.get("org", 100)
        if not (-1e-6 <= org <= 100 + 1e-6):
            out.append(("錯誤", f"{uid} 的 org 超出 0–100：{org}"))
        st = ar.status_of(u)
        if st == "ACTIVE" and org < ar.SURR_ORG:
            elig, why = ar.surrender_conditions(s, uid)
            if elig:
                out.append(("注意", f"{uid} org {org:.1f} < {ar.SURR_ORG} 且滿足"
                                    f"{'、'.join(why)}——應已符合自行投降資格，"
                                    f"確認 evaluate_status 是否被呼叫"))
    return out


def check_position_sanity(s, b):
    """位置必須在地圖內，且該兵種可通行。"""
    out = []
    W, H = s["map"]["width"], s["map"]["height"]
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES:
            continue
        x, y = u["pos"]
        if not (0 <= x < W and 0 <= y < H):
            out.append(("錯誤", f"{uid} 位置 {tuple(u['pos'])} 超出地圖 {W}×{H}"))
        elif not ar._passable(u, ar.terr(s, u["pos"])):
            out.append(("錯誤", f"{uid}（{u['type']}）停在不可通行的地形 "
                                f"{ar.terr(s, u['pos'])} 於 {tuple(u['pos'])}"))
    return out


CHECKS = [
    ("守恆", check_conservation),
    ("彈藥", check_ammo),
    ("射擊合法性", check_fire_legality),
    ("友軍誤擊", check_friendly_fire),
    ("工事", check_works),
    ("戰術狀態", check_tactical_state),
    ("狀態機", check_status_machine),
    ("位置", check_position_sanity),
]


def run(s, before):
    """跑完整清單。回傳 {類別: [(嚴重度, 說明)]}。"""
    return {name: fn(s, before) for name, fn in CHECKS}


def report(findings):
    lines, n_err, n_warn = [], 0, 0
    for name, items in findings.items():
        if not items:
            lines.append(f"  ✅ {name}")
            continue
        for sev, msg in items:
            lines.append(f"  {'❌' if sev == '錯誤' else '⚠️ '} [{name}] {msg}")
            n_err += sev == "錯誤"
            n_warn += sev != "錯誤"
    return "\n".join(lines), n_err, n_warn


def require_clean(s, before, allow_warnings=True):
    """稽核。有「錯誤」級發現即 raise——計分因此印不出來。

    「注意」與「警告」級不阻斷，但會印出來要求裁判逐條說明。
    """
    findings = run(s, before)
    text, n_err, n_warn = report(findings)
    print("── 解算後自我稽核（TODO P6-14：稽核通過才准印計分）──")
    print(text)
    if n_err:
        raise AssertionError(
            f"稽核發現 {n_err} 項錯誤，計分不予輸出。修正後重跑，"
            f"不得在看到計分之後才處理。")
    if n_warn:
        print(f"  ── {n_warn} 項需裁判逐條說明（不阻斷）")
    print("── 稽核通過 ──\n")
    return findings


if __name__ == "__main__":
    s = ar.load()
    b = snapshot(s)
    require_clean(s, b)
