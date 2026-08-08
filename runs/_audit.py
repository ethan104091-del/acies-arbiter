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
                "camo_hours": u.get("camo_hours", 0.0),
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


# ══════════════════════════════════════════════════════════════════
# 以下六項需要**命令清單**（`runs/_manifest.py`）。沒有傳 manifest 時，
# 它們一律回傳一條「注意」——因為「稽核跑了但少查了六項」必須看得見，
# 不能靜默通過。這正是 Run 7 那批瑕疵的共同特徵：漏掉的東西沒有聲音。
# ══════════════════════════════════════════════════════════════════
def _need_manifest(name):
    return [("注意", f"{name}：未提供命令清單（manifest），本項未檢查。"
                     f"新的 tick 腳本應建立 runs/_manifest.TickOrders 並傳入")]


def check_dig_authorized(s, b, mf):
    """A3：構工與偽裝必須明確下令（裁示 33／17）。判例 §二十一。"""
    if mf is None:
        return _need_manifest("A3 構工授權")
    out = []
    for e in s.get("works_ledger") or []:
        if e.get("uid") and e["uid"] not in mf.dig:
            out.append(("錯誤", f"A3 {e['uid']} 於 gh{e.get('gh')} 在 {e.get('hex')} "
                                f"構工 {e.get('man_hours')} man-hr，但本 tick 的命令清單"
                                f"未登記它有構工令（判例 §二十一：不得批次推導）"))
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES or uid not in b["units"]:
            continue
        if u.get("camo_hours", 0.0) > b["units"][uid]["camo_hours"] + 1e-9 and uid not in mf.camo:
            out.append(("錯誤", f"A3 {uid} 的偽裝工時增加，但命令清單未登記偽裝令"))
    return out


def check_movement_authorized(s, b, mf):
    """A4：位置變化須可歸因於本 tick 登記的目的地，或強制位移帳。判例 §二十四。"""
    if mf is None:
        return _need_manifest("A4 移動授權")
    out = []
    pushed = {e["uid"] for e in (s.get("push_ledger") or [])}
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES or uid not in b["units"]:
            continue
        was, now = b["units"][uid]["pos"], list(u["pos"])
        if was == now:
            continue
        if uid in pushed:                      # 逼退／潰散後撤：已有帳
            continue
        if uid not in mf.move:
            out.append(("錯誤", f"A4 {uid} 由 {tuple(was)} 移動到 {tuple(now)}，"
                                f"但本 tick 的命令清單未登記其目的地"
                                f"（判例 §二十四：不得沿用上一 tick 的資料結構）"))
            continue
        dest = mf.move[uid]
        if ar.dist(now, dest) > ar.dist(was, dest):
            out.append(("錯誤", f"A4 {uid} 移動後**離登記目的地更遠**："
                                f"{tuple(was)}→{tuple(now)}，目的地 {dest}"
                                f"（距離 {ar.dist(was, dest)}→{ar.dist(now, dest)}）"))
    return out


def check_push_executed(s, b, mf):
    """A5：battle 判定的逼退必須真的執行。判例 §二十五 ＋ R8-G1（攻方方向）。"""
    out = []
    for e in s.get("push_ledger") or []:
        if e.get("kind") == "潰散後撤":
            continue
        if e.get("moved", 0) < e.get("ordered", 0) and not e.get("note"):
            out.append(("錯誤", f"A5 {e['uid']} 於 gh{e.get('gh')} 應逼退 "
                                f"{e['ordered']} 格但只位移 {e.get('moved')} 格，"
                                f"且未載明受阻原因（判例 §二十五：逼退不受移動速率限制）"))
        elif e.get("moved", 0) < e.get("ordered", 0):
            out.append(("注意", f"A5 {e['uid']} 應逼退 {e['ordered']} 格、實際 "
                                f"{e.get('moved')} 格：{e.get('note')}"))
    # 反向檢查：本 tick 有近戰但完全沒有逼退帳 → 可能又漏了執行
    if mf is not None and any("兵力比" in l for l in s.get("hour_log", [])[-24:]) \
            and not (s.get("push_ledger") or []):
        out.append(("注意", "A5 本 tick 有近戰解算但逼退帳為空——"
                           "確認每一場的兵力比都落在 push=0 的兩列（1.0–2.0）"))
    return out


def check_fire_authorized(s, b, mf):
    """A6：開火者須在命令清單、或為應變觸發、或為近戰參與者。"""
    if mf is None:
        return _need_manifest("A6 射擊授權")
    out = []
    allowed = mf.shooters() | mf.triggered
    melee = set()
    for line in s.get("hour_log", [])[-24:]:
        if "兵力比" in line:
            for uid in s["units"]:
                if uid in line:
                    melee.add(uid)
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES:
            continue
        if u["flags"].get("fired") and uid not in allowed and uid not in melee:
            out.append(("錯誤", f"A6 {uid} 開火但命令清單未登記其火力任務，"
                                f"也未登記為應變觸發（mf.contingency_fired）"))
    return out


def check_manifest_valid(s, b, mf):
    """A7：清單本身合法——每個動作都有出處，且出處指向本 tick。"""
    if mf is None:
        return _need_manifest("A7 命令出處")
    try:
        mf.validate()
    except AssertionError as e:
        return [("錯誤", f"A7 {e}")]
    return [("注意", f"A7 命令出處齊備（{mf!r}）")] if False else []


def check_no_mixed_hex(s, b, mf=None):
    """A8：同一格不得同時有雙方的戰鬥編隊（裁示 47 的事後驗證）。

    移入敵佔格是近戰突擊，攻方只在守軍被殲滅／投降／潰散／逼退後才進駐。
    引擎自 2026-08-08 起在 `advance()` 內擋下，本項是它的獨立驗證——
    判例 §二十四 的教訓是護欄寫成單方清單會靜默失效，故護欄與稽核都要有。
    """
    out = []
    byhex = {}
    for uid, u in s["units"].items():
        if u.get("side") not in SIDES or ar.status_of(u) not in ar.COMBAT_STATUSES:
            continue
        byhex.setdefault((int(u["pos"][0]), int(u["pos"][1])), []).append((uid, u["side"]))
    for pos, lst in sorted(byhex.items()):
        sides = {sd for _, sd in lst}
        if len(sides) > 1:
            out.append(("錯誤", f"A8 格 {pos} 同時有雙方戰鬥編隊："
                                f"{'、'.join(u for u, _ in lst)}（違反裁示 47）"))
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

# 需要命令清單的檢查（`_manifest.TickOrders`）
CHECKS_MF = [
    ("A3 構工授權", check_dig_authorized),
    ("A4 移動授權", check_movement_authorized),
    ("A5 逼退執行", check_push_executed),
    ("A6 射擊授權", check_fire_authorized),
    ("A7 命令出處", check_manifest_valid),
    ("A8 敵我同格", check_no_mixed_hex),
]


def run(s, before, manifest=None):
    """跑完整清單。回傳 {類別: [(嚴重度, 說明)]}。"""
    out = {name: fn(s, before) for name, fn in CHECKS}
    for name, fn in CHECKS_MF:
        out[name] = fn(s, before, manifest)
    return out


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


def require_clean(s, before, manifest=None, allow_warnings=True):
    """稽核。有「錯誤」級發現即 raise——計分因此印不出來。

    「注意」與「警告」級不阻斷，但會印出來要求裁判逐條說明。

    `manifest`：本 tick 的 `runs/_manifest.TickOrders`。**不傳會少查六項**
    （A3–A8），且每一項都會印出「未檢查」的注意——漏查必須看得見。
    """
    findings = run(s, before, manifest)
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
