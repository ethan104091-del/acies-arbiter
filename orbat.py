#!/usr/bin/env python3
"""營級編制（ORBAT）系統 — 師完整攤開 + 最高自由度拆分。

取代舊 detachments.py。設計見 design_division_orbat.md。
理念（user 定）：師編制完整明確、任一營都能單獨拉出、裁判只管真實+可行不管戰術。

第一階段（本檔）：營級編制資料 + 拆單營(detach) + 歸建(rejoin) + 編制樹(orbat_tree)。
（編組自組戰鬥群之後再加。）

雙軌數值：
  personnel — 人數，拆/歸建按它加減、守恆。
  strength  — 0-100 戰力%，戰鬥公式用。拉營時母師按貢獻度微調。

uid：拉出的營 = "<師>-<營碼>"，如 "1ID-5arty"、"3AD-32a"。
欄位 is_detachment/parent/bn_code 標記，渲染與迷霧自動套用。
"""
import json
from pathlib import Path

GAME_DIR = Path.home() / "war-game"
STATE_PATH = GAME_DIR / "state.json"

# ── 各師營級編制（依 forces_v1.md）────────────────────────────────
# 每營: (碼, 顯示名, 兵種, 人數, 武器/備註)
# 兵種對應 mapcore.TYPE_GLYPH: infantry/armor/artillery/recon/engineer/antitank
#   + 新增 mech_inf(裝甲步兵), aa(防空)

def _us_inf_div(regts):
    """美軍步兵師通用編制（3 團×3 營 + 砲4 + 工/偵 + attached）。
    regts = [團號×3]；tank_bn = attached 戰車營 (碼,名,人數,M4數)。"""
    bns = []
    for r in regts:
        for b in (1, 2, 3):
            bns.append((f"{b}-{r}", f"{b}營/{r}團", "infantry", 870, "步兵營"))
    return bns


US_INF_ARTY = [
    ("a1", "105榴砲營", "artillery", 500, "M2A1 105mm×12"),
    ("a2", "105榴砲營", "artillery", 500, "M2A1 105mm×12"),
    ("a3", "105榴砲營", "artillery", 500, "M2A1 105mm×12"),
    ("a4", "155榴砲營", "artillery", 500, "M1 155mm×12"),
]
US_INF_SUP = [
    ("eng", "工兵戰鬥營", "engineer", 700, "架橋/拆雷/工事"),
    ("rcn", "騎兵偵察隊", "recon", 300, "M8×13+Jeep"),
    ("hq", "師部及勤務", "hq", 2050, "醫療/信號/補給/司令部 — 不可拉出"),
]

# 不可單獨拉出的兵種（師部勤務黏在師裡）
NON_DETACHABLE = {"hq"}

ORBAT = {
    # ── 美軍步兵師 ──
    "1ID": _us_inf_div(["16", "18", "26"]) + US_INF_ARTY + US_INF_SUP + [
        ("tank", "第745戰車營", "armor", 750, "M4×54+Stuart×17 (attached)"),
        ("aa", "第634防空營", "aa", 400, "40mm Bofors×32 (attached)"),
    ],
    "4ID": _us_inf_div(["8", "12", "22"]) + US_INF_ARTY + US_INF_SUP + [
        ("tank", "第70戰車營", "armor", 720, "M4×52 (attached)"),
    ],
    "90ID": _us_inf_div(["357", "358", "359"]) + US_INF_ARTY + US_INF_SUP + [
        ("tank", "第712戰車營", "armor", 700, "M4×48 (attached)"),
        ("brg", "第537架橋連", "engineer", 200, "重型浮橋200m (軍級加強)"),
    ],
    # ── 3AD 裝甲師（戰鬥指揮部制，營為積木供自組 CCA/CCB/CCR）──
    "3AD": [
        ("32a", "32團1戰車營", "armor", 700, "M4 Sherman"),
        ("32b", "32團2戰車營", "armor", 700, "M4 Sherman"),
        ("33a", "33團1戰車營", "armor", 700, "M4 Sherman"),
        ("33b", "33團2戰車營", "armor", 700, "M4 Sherman"),
        ("36a", "36團1裝步營", "mech_inf", 1000, "M3 halftrack×80"),
        ("36b", "36團2裝步營", "mech_inf", 1000, "M3 halftrack×80"),
        ("36c", "36團3裝步營", "mech_inf", 1000, "M3 halftrack×80"),
        ("sp1", "第54自走砲營", "artillery", 550, "M7 Priest×18"),
        ("sp2", "第67自走砲營", "artillery", 550, "M7 Priest×18"),
        ("sp3", "第391自走砲營", "artillery", 550, "M7 Priest×18"),
        ("eng", "第23裝甲工兵營", "engineer", 700, "橋梁/TNT12000lbs"),
        ("rcn", "裝甲偵察", "recon", 300, "M8×9"),
        ("hq", "師部及勤務", "hq", 5538, "司令部/補給/醫療 — 不可拉出"),
    ],
    # ── 17SS 擲彈兵師 ──
    "17SS": [
        ("37-1", "1營/37團", "panzergrenadier", 700, "擲彈兵(部分摩化)"),
        ("37-2", "2營/37團", "panzergrenadier", 700, "擲彈兵"),
        ("37-3", "3營/37團", "panzergrenadier", 700, "擲彈兵"),
        ("38-1", "1營/38團", "panzergrenadier", 700, "擲彈兵(部分摩化)"),
        ("38-2", "2營/38團", "panzergrenadier", 700, "擲彈兵"),
        ("38-3", "3營/38團", "panzergrenadier", 700, "擲彈兵"),
        ("pz", "第17裝甲營", "armor", 900, "StuG III/IV×41 (無Panther/Tiger)"),
        ("art1", "砲兵1營(自走)", "artillery", 550, "Wespe×12+Hummel×6"),
        ("art2", "砲兵2營", "artillery", 500, "leFH18 105mm×12"),
        ("art3", "砲兵3營", "artillery", 500, "sFH18 150mm×12"),
        ("pak", "反戰車營", "antitank", 600, "PaK40×23+Marder×9+Hetzer×6"),
        ("flak", "88防空營", "aa", 400, "88mm Flak×12 (★彈藥短缺)"),
        ("eng", "裝甲工兵營", "engineer", 600, "預埋/拆橋/Teller雷"),
        ("rcn", "裝甲偵察營", "recon", 400, "SdKfz234/250+摩托"),
        ("hq", "師部及勤務", "hq", 4550, "司令部/補給/醫療 — 不可拉出"),
    ],
    # ── 2Pz 裝甲師（最精銳）──
    "2Pz": [
        ("pz1", "第I裝甲營", "armor", 600, "Panther×34 (75mm L/70)"),
        ("pz2", "第II裝甲營", "armor", 700, "Pz IV×50 (75mm L/48)"),
        ("pg2-1", "1營/2機步團", "mech_inf", 900, "SdKfz251機械化"),
        ("pg2-2", "2營/2機步團", "mech_inf", 900, "機步"),
        ("pg304-1", "1營/304團", "mech_inf", 850, "機步"),
        ("pg304-2", "2營/304團", "mech_inf", 850, "機步"),
        ("art", "第74砲兵團", "artillery", 1200, "Wespe×12+Hummel×6+leFH18×24"),
        ("pak", "反戰車營", "antitank", 600, "PaK40×12+Marder×9+JagdpzIV×12"),
        ("eng", "第38裝甲工兵營", "engineer", 580, "工兵"),
        ("rcn", "第2裝甲偵察營", "recon", 500, "Puma(50mm)×16 ★重型偵察"),
        ("hq", "師部及勤務", "hq", 4120, "司令部/補給/醫療 — 不可拉出"),
    ],
    # ── 352 步兵師（殘破 7,200）──
    "352": [
        ("914", "第914擲彈團", "infantry", 1600, "已削減(約1.6k)"),
        ("915", "第915擲彈團", "infantry", 1600, "已削減"),
        ("916", "第916擲彈團", "infantry", 1600, "已削減"),
        ("art", "第352砲兵團", "artillery", 700, "leFH18×18(半損)"),
        ("pak", "反戰車", "antitank", 300, "PaK40×14+Marder×3"),
        ("flak", "防空", "aa", 200, "20mm Flak×12"),
        ("eng", "第352工兵營", "engineer", 440, "半損"),
        ("hq", "師部及勤務", "hq", 760, "司令部/補給/醫療(半損) — 不可拉出"),
    ],
}

# 軍級資產（parent="corps"）
CORPS_ORBAT = {
    "allies": [
        ("ranger", "第2 Ranger營", "ranger", 473, "6連A-F,特戰滲透/夜拆/狙擊"),
        ("cav", "第4騎兵集團", "recon", 2000, "M8×54+Stuart×17"),
        ("chem", "第87化學迫砲營", "artillery", 600, "4.2吋107mm×48"),
    ],
    "axis": [
        ("obs", "第311觀察砲營", "artillery", 500, "聲測/觀測修砲"),
    ],
}


# ── PvP「純戰場 Open Field」鏡像編制（藍軍=紅軍，沿用 1944 諸兵種 TOE）──
def _mirror_inf_div(regts):
    return (_us_inf_div(regts) + US_INF_ARTY + [
        ("eng", "工兵戰鬥營", "engineer", 700, "架橋/拆雷/工事"),
        ("rcn", "偵察隊", "recon", 300, "裝甲車+Jeep"),
        ("hq", "師部及勤務", "hq", 2050, "司令部/補給/醫療 — 不可拉出"),
        ("tank", "配屬戰車營", "armor", 750, "中戰車×54 (attached)"),
        ("aa", "防空營", "aa", 400, "40mm×32 (attached)"),
    ])

def _mirror_armor_div():
    return [
        ("t1", "1戰車營", "armor", 700, "中戰車"), ("t2", "2戰車營", "armor", 700, "中戰車"),
        ("t3", "3戰車營", "armor", 700, "中戰車"), ("t4", "4戰車營", "armor", 700, "中戰車"),
        ("m1", "1裝步營", "mech_inf", 1000, "半履帶"), ("m2", "2裝步營", "mech_inf", 1000, "半履帶"),
        ("m3", "3裝步營", "mech_inf", 1000, "半履帶"),
        ("sp1", "1自走砲營", "artillery", 550, "自走榴砲×18"),
        ("sp2", "2自走砲營", "artillery", 550, "自走榴砲×18"),
        ("sp3", "3自走砲營", "artillery", 550, "自走榴砲×18"),
        ("eng", "裝甲工兵營", "engineer", 700, "工兵"), ("rcn", "裝甲偵察", "recon", 300, "裝甲車"),
        ("hq", "師部及勤務", "hq", 5538, "司令部/補給/醫療 — 不可拉出"),
    ]

def _sf_brigade():
    return [
        ("a1", "1突擊營", "ranger", 600, "精銳輕步兵/游騎兵"),
        ("a2", "2突擊營", "ranger", 600, "精銳輕步兵"),
        ("a3", "3突擊營", "ranger", 600, "精銳輕步兵"),
        ("rcn", "偵察營", "recon", 300, "縱深偵察/前導"),
        ("spt", "輕支援分隊", "engineer", 400, "迫擊/輕反戰車/爆破"),
        ("hq", "旅部及勤務", "hq", 1000, "通信/補給 — 不可拉出"),
    ]

for _s in ("BLU", "RED"):
    ORBAT[f"{_s}-1"] = _mirror_inf_div(["r1", "r2", "r3"])
    ORBAT[f"{_s}-2"] = _mirror_inf_div(["r4", "r5", "r6"])
    ORBAT[f"{_s}-3"] = _mirror_inf_div(["r7", "r8", "r9"])
    ORBAT[f"{_s}-AD"] = _mirror_armor_div()
    ORBAT[f"{_s}-SF"] = _sf_brigade()


def div_orbat(div_uid):
    """回傳某師的營級編制清單 [(碼,名,兵種,人數,備註)]。"""
    return ORBAT.get(div_uid, [])


def total_personnel(div_uid):
    return sum(b[3] for b in div_orbat(div_uid))


def ensure_orbat(state):
    """就地給每個師補上 personnel + orbat（status 樹）。冪等。"""
    for uid, u in state["units"].items():
        if u.get("is_detachment"):
            continue
        bns = div_orbat(uid)
        if not bns:
            continue
        if "orbat" not in u:
            u["orbat"] = {code: {"name": nm, "type": typ, "personnel": pers,
                                 "note": note, "status": "in_division"}
                          for (code, nm, typ, pers, note) in bns}
        u.setdefault("personnel", total_personnel(uid))
    return state


def _bn(div_uid, code):
    for b in div_orbat(div_uid):
        if b[0] == code:
            return b
    return None


def detach(state, div_uid, code, pos):
    """把一個營從師拉出成獨立棋子。回傳 (新uid, 棋子dict)。
    扣母師 personnel + strength(按人數佔比的一半，避免拉小單位重創師)。"""
    parent = state["units"].get(div_uid)
    if not parent:
        raise ValueError(f"無此師: {div_uid}")
    ensure_orbat(state)
    ob = parent.get("orbat", {})
    if code not in ob:
        raise ValueError(f"{div_uid} 無此營: {code}")
    if ob[code]["type"] in NON_DETACHABLE:
        raise ValueError(f"{div_uid}/{code} 是師部勤務，不可單獨拉出")
    if ob[code]["status"] != "in_division":
        raise ValueError(f"{div_uid}/{code} 已不在師內(status={ob[code]['status']})")
    info = ob[code]
    pers = info["personnel"]
    # 母師 strength 扣除：按人數佔比衰減一半（拉走一個營不該讓師戰力等比崩）
    frac = pers / max(parent.get("personnel", 1), 1)
    str_cut = min(round(parent.get("strength", 100) * frac * 0.5),
                  parent.get("strength", 100) - 1)
    parent["personnel"] = parent.get("personnel", 0) - pers
    parent["strength"] = parent.get("strength", 100) - str_cut
    ob[code]["status"] = "detached"
    det_uid = f"{div_uid}-{code}"
    # 營自身 strength：繼承母師戰力%（同樣訓練/補給水準），不是用扣除值反推
    bn_strength = parent.get("strength", 80) + str_cut  # 母師扣前的水準
    det = {
        "side": parent["side"], "short": f"{parent['short']}/{code}",
        "name": f"{parent['short']} {info['name']}", "type": info["type"],
        "pos": list(pos), "personnel": pers,
        "strength": min(100, bn_strength),   # 營承襲母師戰力水準
        "org": parent.get("org", 80), "xp": parent.get("xp", 2),
        "speed": _speed(info["type"]), "fatigue": 0,
        "visibility_state": "STANDARD",
        "is_detachment": True, "parent": div_uid, "bn_code": code,
        "_str_cut": str_cut,   # 記下母師扣了多少戰力，歸建時精確還原（守恆）
        "orders": "", "hidden": False, "last_action": f"由 {parent['short']} 拉出",
    }
    state["units"][det_uid] = det
    return det_uid, det


def rejoin(state, det_uid):
    """營歸建：人數+戰力加回母師，status 還原，移除獨立棋子。回傳母師 uid。"""
    det = state["units"].get(det_uid)
    if not det or not det.get("is_detachment"):
        raise ValueError(f"{det_uid} 不是拉出的營")
    parent_uid = det["parent"]
    parent = state["units"].get(parent_uid)
    if parent:
        parent["personnel"] = parent.get("personnel", 0) + det.get("personnel", 0)
        # 精確還原 detach 時扣的戰力（守恆）
        parent["strength"] = min(100, parent.get("strength", 0) + det.get("_str_cut", 0))
        code = det.get("bn_code")
        if code in parent.get("orbat", {}):
            parent["orbat"][code]["status"] = "in_division"
    del state["units"][det_uid]
    return parent_uid


_SPEED = {"infantry": 1, "panzergrenadier": 2, "mech_inf": 2, "armor": 3,
          "artillery": 1, "recon": 2, "engineer": 1, "antitank": 2, "aa": 1,
          "ranger": 2}


def _speed(typ):
    return _SPEED.get(typ, 1)


def orbat_tree(state, div_uid):
    """回傳某師的編制樹（給面板顯示），含每營狀態。"""
    u = state["units"].get(div_uid, {})
    return u.get("orbat", {})


TYPE_ZH = {"infantry": "步兵", "armor": "裝甲", "mech_inf": "裝甲步兵",
           "panzergrenadier": "擲彈兵", "artillery": "砲兵", "recon": "偵察",
           "engineer": "工兵", "antitank": "反戰車", "aa": "防空",
           "ranger": "特戰", "hq": "師部勤務"}


def print_orbat(side=None):
    """CLI 查詢：印出師的完整營級編制樹。side=allies/axis/None(全部)。"""
    from rich.console import Console
    from rich.table import Table
    s = ensure_orbat(json.loads(STATE_PATH.read_text()))
    console = Console()
    order = ["1ID", "4ID", "3AD", "90ID", "17SS", "2Pz", "352"]
    for uid in order:
        u = s["units"].get(uid)
        if not u or (side and u["side"] != side):
            continue
        ob = u.get("orbat", {})
        n_det = sum(1 for b in ob.values() if b.get("status") == "detached")
        title = (f"[bold]{uid}[/] {u['name']} — 員額 {u.get('personnel','?')}人"
                 f" 戰力{u.get('strength','?')}%"
                 + (f"  [yellow]{n_det}營已拉出[/]" if n_det else ""))
        t = Table(title=title, show_edge=True, expand=False)
        t.add_column("營碼", style="cyan")
        t.add_column("名稱")
        t.add_column("兵種")
        t.add_column("人數", justify="right")
        t.add_column("狀態")
        t.add_column("備註", style="dim")
        for code, b in ob.items():
            st = b.get("status", "in_division")
            stxt = {"in_division": "[dim]在師[/]",
                    "detached": "[yellow]已拉出[/]"}.get(st, f"[green]{st}[/]")
            detachable = "" if b["type"] == "hq" else ""
            t.add_row(code, b["name"], TYPE_ZH.get(b["type"], b["type"]),
                      str(b.get("personnel", "")), stxt, b.get("note", ""))
        console.print(t)
        console.print()


if __name__ == "__main__":
    import sys
    if "--side" in sys.argv:
        i = sys.argv.index("--side")
        side = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        print_orbat(side)
    elif "--check" in sys.argv:
        import copy
        s = ensure_orbat(json.loads(STATE_PATH.read_text()))
        print("=== 各師員額(營級加總) vs forces_v1 ===")
        for uid in ["1ID", "4ID", "90ID", "3AD", "17SS", "2Pz", "352"]:
            print(f"  {uid:5} 營數={len(div_orbat(uid)):2} 人數加總={total_personnel(uid)}")
        s2 = copy.deepcopy(s)
        uid, det = detach(s2, "1ID", "a1", (8, 11))
        pu = rejoin(s2, uid)
        assert s2['units']['1ID']['personnel'] == s['units']['1ID']['personnel']
        print("orbat self-test OK")
    else:
        print_orbat()
