#!/usr/bin/env python3
"""規則註冊表 — `docs/plan_run8.md` 的 Phase 2，S1＋S3 的結構解。

## 為什麼存在

規則有三個住址：**引擎**、`rules/` 規格書、發給指揮官的**手冊**。
指揮官只看得到第三份，而三份會漂移。Run 7 的 22 條裁示裡 11 條源於這個落差。

`gen_handbook.py` 早就「自引擎取值」了，仍然出了 F1（協同倍率）。原因是
**引擎的行為有一部分不可列舉**：

| 藏在哪 | 例子 | 產生器看得到嗎 |
|---|---|---|
| 常數 dict | `COMBINED[1..3]` | ✅ |
| **`.get(k, 預設)` 的預設值** | 4 兵種以上 ＝ 1.7 | ❌ **F1 就是這個** |
| **函式裡的字面值** | `unit_cp` 的 `cp *= 0.7 if t == "F"` | ❌ 更糟 |

所以註冊表**不存常數，存「定義域 ＋ 求值函式」**。
第四級因此會被枚舉出來；而 CP 乘數鏈那幾個字面值，其求值函式是
**直接量測引擎**（同一狀態下切換單一條件，取比值），連原始碼都不必解析。

## 一致性怎麼保證：文件裡的表由本檔產生，不是被本檔解析

上一版的做法是「解析規格書的表格再比對」。判例 §二十六 記著本專案在
「用字串比對近似語意」這個坑上已經踩了四次，而解析他人手寫的 Markdown
仍然是同一類脆弱做法。

**改成反過來：規格書裡放產生區塊，內容由本檔產出。**

    <!-- rulespec:combined_arms -->
    …（表格，由 rulespec.render 產生）…
    <!-- /rulespec:combined_arms -->

散文（「為什麼」）仍然手寫，就寫在區塊外面。測試斷言區塊內容與
`render(id)` **逐位元組相同**——不是近似、不是子字串。

    python3 rulespec.py --verify     # 檢查所有文件的區塊（測試會跑這個）
    python3 rulespec.py --sync       # 引擎改了之後，把區塊重寫成新值
    python3 rulespec.py --list       # 列出所有規則與其涵蓋的常數

## 覆蓋率

`coverage()` 檢查 `arbiter.py` 的每個模組級常數是否被某條規則涵蓋，
或列在 `INTERNAL` 白名單裡。白名單**每一項都要寫理由**——
讓「忘記登記」變成加白名單時會被看見的動作，而不是靜默的遺漏。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import arbiter as ar          # noqa: E402

BEGIN = "<!-- rulespec:{} -->"
END = "<!-- /rulespec:{} -->"


# ── 規則 ──────────────────────────────────────────────────────────
class Rule:
    """一條玩家可見的規則。

    `domain` ＋ `fn` 是本檔的核心：**存求值函式，不存常數**。
    `covers` 是它涵蓋的 `arbiter` 常數名（供覆蓋率檢查）；
    量測型規則（CP 乘數鏈）的 `covers` 為空，因為那些值不是常數。
    """

    def __init__(self, id, label, domain, fn, header, row,
                 covers=(), note="", addr=None):
        self.id = id
        self.label = label
        self.domain = list(domain)
        self.fn = fn
        self.header = list(header)
        self.row = row
        self.covers = set(covers)
        self.note = note
        self.addr = addr            # 規範住址（哪份文件的哪一節）

    def render(self):
        """產生 Markdown 表格（＋可選的註腳）。逐位元組穩定。"""
        align = "|" + "|".join("---" if i == 0 else "---:"
                               for i in range(len(self.header))) + "|"
        lines = ["|" + "|".join(f" {h} " for h in self.header) + "|", align]
        for k in self.domain:
            cells = self.row(k, self.fn(k))
            lines.append("|" + "|".join(f" {c} " for c in cells) + "|")
        if self.note:
            lines += ["", self.note]
        return "\n".join(lines)

    def block(self):
        return f"{BEGIN.format(self.id)}\n{self.render()}\n{END.format(self.id)}"


# ── 量測型求值：CP 乘數鏈（引擎裡的字面值，不是常數）──────────────────
_FIX = {"cache": None}


def _fixture():
    """一個固定的量測夾具：同一個編隊、一個平原格、一個森林格。

    ★ 為何要量測而不是抄字面值：`unit_cp` 的地形／伏擊／被動／行軍中接戰四個乘數
      寫在函式體裡（`cp *= 0.7 if t == "F" else 1.0`），既不在常數表也不在
      `.get` 預設值裡。抄一次就是再一次 F1。量測法對「引擎改了而文件沒改」免疫。
    """
    if _FIX["cache"] is None:
        s = ar.load(ROOT / "maps" / "open_field_state.json")
        for u in s["units"].values():
            u["flags"] = {}
        uid = next(k for k, v in s["units"].items()
                   if v.get("side") == "allies" and v["type"] == "infantry")
        u = s["units"][uid]
        u["strength"], u["org"], u["xp"], u["fatigue"] = 100, 100, 3, 0
        u["fortification"] = 0.0
        W, H = s["map"]["width"], s["map"]["height"]
        plain = next((x, y) for y in range(H) for x in range(W) if ar.terr(s, (x, y)) == ".")
        forest = next(((x, y) for y in range(H) for x in range(W) if ar.terr(s, (x, y)) == "F"),
                      None)
        _FIX["cache"] = (s, uid, plain, forest)
    return _FIX["cache"]


def _cp(**kw):
    s, uid, plain, _ = _fixture()
    base = dict(pos=plain, is_attacker=True, spotted_by_enemy=True,
                sees_enemy=True, from_march=False, passive=False, arms_count=1)
    base.update(kw)
    pos = base.pop("pos")
    return ar.unit_cp(s, uid, pos, **base)


def _cp_ratio(**kw):
    """同一編隊、只切換一個條件，取比值——即該條件的乘數。"""
    return round(_cp(**kw) / _cp(), 4)


def _cp_def(**kw):
    s, uid, plain, _ = _fixture()
    s["units"][uid]["pos"] = list(plain)
    base = dict(is_attacker=False, spotted_by_enemy=True, passive=False, arms_count=1)
    base.update(kw)
    return ar.unit_cp(s, uid, plain, **base)


CP_CHAIN = {
    "攻方突襲（守方未偵獲攻方）": lambda: _cp_ratio(spotted_by_enemy=False),
    "守方被突襲（看不見攻方）": lambda: round(_cp_def(sees_enemy=False) / _cp_def(), 4),
    "攻方在森林（目標格）": lambda: (
        round(_cp(pos=_fixture()[3]) / _cp(), 4) if _fixture()[3] else None),
    "守方在森林": lambda: round(
        (lambda s, uid: (
            (s["units"][uid].__setitem__("pos", list(_fixture()[3])),
             ar.unit_cp(s, uid, _fixture()[3], is_attacker=False, arms_count=1))[1]
            / _cp_def()))(*_fixture()[:2]), 4) if _fixture()[3] else None,
    "守方伏擊（攻方未偵獲守方）": lambda: round(
        _cp_def(spotted_by_enemy=False) / _cp_def(), 4),
    "守方被動應戰": lambda: round(_cp_def(passive=True) / _cp_def(), 4),
    "從行軍中接戰": lambda: _cp_ratio(from_march=True),
}


def _fatigue_row(f):
    cap, eff, mv = ar.fatigue_effects({"fatigue": f})
    return cap, eff, mv


# 編隊種類的人話標籤。★ 手冊與規格書用同一份產生，故標籤必須讓**指揮官**看得懂——
# 只印引擎代號（`infantry`）是產生器方便、讀者不方便。兩者都給。
TYPE_ZH = {
    "infantry": "步兵師", "armor": "裝甲師／自走砲", "mech_inf": "裝甲步兵營",
    "ranger": "特戰旅", "recon": "偵察營（抽離）", "engineer": "工兵營（抽離）",
    "artillery": "砲兵營（抽離）", "aa": "防空營（抽離）", "hq": "司令部／勤務",
    "div": "師級主力",
}


def _zh(k):
    """人話標籤 ＋ 引擎代號。兩者都要：讀者看標籤，下令與查證看代號。"""
    return f"{TYPE_ZH.get(k, k)} `{k}`"


# ── 註冊表 ────────────────────────────────────────────────────────
def _m(x):
    """乘數的統一呈現：一律兩位小數（1.00 不寫成 1，避免「×1」讀成整數）。"""
    return "—" if x is None else f"{float(x):.2f}"


def _f(x):
    """數字的統一呈現：整數不帶小數點，其餘去尾零。"""
    if isinstance(x, bool):
        return "是" if x else "—"
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


RULES = [
    Rule("combined_arms", "兵種協同倍率",
         domain=[1, 2, 3, 4], fn=lambda n: ar.COMBINED.get(n, 1.7),
         header=["兵種數", "倍率"],
         row=lambda n, v: [f"{n}" + (" 以上" if n == 4 else ""),
                           f"**{_m(v)}**" if n >= 4 else _m(v)],
         covers=["COMBINED"],
         note="★ 第 4 級不在 `COMBINED` dict 裡，是 `unit_cp` 的 `.get(n, 1.7)` 預設值。\n"
              "判例 §二十六：手冊曾因此寫成「3 種以上 1.5」。"
              "`ARM_OF_TYPE` 使裝甲師 ∪ 步兵師 ＝ 4 種，故 1.7 是常見情況。",
         addr=("rules/40_近戰.md", "§6")),

    Rule("fort_tiers", "工事分級",
         domain=range(len(ar.FORT_TIERS)), fn=lambda i: ar.FORT_TIERS[i],
         header=["級", "累計工時（每人）", "`fortification`", "砲擊暴露", "說明"],
         row=lambda i, t: [f"**{t[3]}**", _f(t[0]) if i else "—", _f(t[1]),
                           f"**{_f(t[2])}**", t[4]],
         covers=["FORT_TIERS"],
         addr=("rules/50_工事.md", "§1")),

    Rule("dig_rate", "挖掘／偽裝工時速率",
         domain=sorted(ar.DIG_RATE), fn=lambda k: ar.DIG_RATE[k],
         header=["兵種", "倍率"],
         row=lambda k, v: [_zh(k), f"{v:.2f}"],
         covers=["DIG_RATE"],
         addr=("rules/50_工事.md", "§1")),

    Rule("move_rate", "移動速率（格/hour，白天無壓制）",
         domain=sorted(ar.RATE), fn=lambda k: ar.RATE[k],
         header=["兵種", "開闊地", "森林"],
         row=lambda k, v: [_zh(k), f"{v['.']:.2f}",
                           "**不可入**" if v["F"] == 0 else f"{v['F']:.2f}"],
         covers=["RATE"],
         note="夜間一律 ×0.5；疲勞 40+／60+／80+ 分別 ×0.9／×0.8／×0.7；"
              "POL <20% ×0.5、<10% 停止；前一小時遭砲擊 ×"
              f"{_f(ar.SUPPRESS_MOVE_MULT)}。",
         addr=("rules/10_地形與移動.md", "§2")),

    Rule("sight", "偵察視距（格）",
         domain=sorted(ar.SIGHT), fn=lambda k: ar.SIGHT[k],
         header=["觀測者", "白天", "夜間"],
         row=lambda k, v: [_zh(k), _f(v[0]), _f(v[1])],
         covers=["SIGHT"],
         addr=("rules/20_偵察.md", "§1")),

    Rule("vis_req", "能見狀態 → 被偵獲所需距離",
         domain=["EXPOSED", "STANDARD", "CAMOUFLAGED", "CONCEALED", "HIDDEN"],
         fn=lambda k: ar.VIS_REQ[k],
         header=["能見狀態", "被偵獲所需距離（格）"],
         row=lambda k, v: [k, "視距內皆可" if v is None else f"≤ {_f(v)}"],
         covers=["VIS_REQ"],
         note="★ `HIDDEN` 引擎**永不指派**（`refresh_visibility` 只產出前四種）——"
              "`docs/TODO.md` R8-H6。",
         addr=("rules/20_偵察.md", "§2")),

    Rule("gun_spec", "火砲諸元",
         domain=list(ar.GUN_SPEC), fn=lambda k: (ar.GUN_SPEC[k], ar.AMMO_LOAD.get(k)),
         header=["砲種", "射速/min", "每發殺傷力", "射程（格）", "每發殺戰車", "彈藥基數（發）"],
         row=lambda k, v: [f"`{k}`", f"{v[0][0]:.1f}", _f(v[0][1]),
                           f"**{_f(v[0][2])}**", _f(v[0][3]),
                           f"{v[1]:,}" if v[1] else "—"],
         covers=["GUN_SPEC", "AMMO_LOAD"],
         addr=("rules/30_火力.md", "§1")),

    Rule("fire_mission", "火力任務類型",
         domain=list(ar.FIRE_MISSION), fn=lambda k: ar.FIRE_MISSION[k],
         header=["任務", "佔用（min）", "彈量×", "每發殺傷×", "org 衝擊×", "凍結土工"],
         row=lambda k, v: [f"**{k}**", _f(v[0]), _m(v[1]), _m(v[2]), _m(v[3]),
                           "**是**" if v[4] else "—"],
         covers=["FIRE_MISSION", "FIRE_MINUTES"],
         note=f"彈量倍率是「相對標準任務（`FIRE_MINUTES = {ar.FIRE_MINUTES}` 分）"
              "的總彈量」，**不與佔用時長相乘**。",
         addr=("rules/30_火力.md", "§2")),

    Rule("fr_table", "兵力比 → 損失對照表",
         domain=range(len(ar.FR_TABLE)), fn=lambda i: ar.FR_TABLE[i],
         header=["兵力比 <", "攻方 str%", "攻方 org", "守方 str%", "守方 org", "逼退格數"],
         row=lambda i, t: ["**≥5.0**" if t[0] > 1e8 else _f(t[0]),
                           _f(t[1]), _f(t[2]), _f(t[3]), _f(t[4]),
                           "**攻方退 1**" if t[5] < 0 else
                           ("—" if t[5] == 0 else f"守方退 {t[5]}")],
         covers=["FR_TABLE"],
         note="★ 逼退**由 `battle()` 自行執行**，兩個方向都做（判例 §二十五、`docs/TODO.md` R8-G1）。\n"
              "★ 最後兩列的 2／3 格為 [判例]：`combat_v1` §III 的地形變化欄只寫"
              "「潰散風險」「必潰散」，未給格數。",
         addr=("rules/40_近戰.md", "§3")),

    Rule("vet", "經驗倍率",
         domain=sorted(ar.VET), fn=lambda k: ar.VET[k],
         header=["經驗", "倍率"],
         row=lambda k, v: ["⭐" * k, _m(v)],
         covers=["VET"],
         note="經驗有**兩個互不重疊的入口**（判例 §八）：地面戰 CP，以及"
              "所有計算發數的射擊（`bombard` 的每發殺傷力另乘此值）。",
         addr=("rules/30_火力.md", "§10")),

    Rule("base_power", "基礎戰力",
         domain=sorted(ar.BASE_POWER), fn=lambda k: ar.BASE_POWER[k],
         header=["編隊種類", "基礎值"],
         row=lambda k, v: [_zh(k), _f(v)],
         covers=["BASE_POWER"],
         note="抽離的營級單位按人數等比：`人數 / 1000 × 7.1`。",
         addr=("rules/40_近戰.md", "§1")),

    Rule("cp_chain", "CP 乘數鏈（★ 由量測引擎產生）",
         domain=list(CP_CHAIN), fn=lambda k: CP_CHAIN[k](),
         header=["條件", "乘數"],
         row=lambda k, v: [k, "—" if v is None else f"**{_m(v)}**"],
         covers=[],
         note="★ 這些乘數**寫在 `unit_cp` 的函式體裡**，既不在常數表也不在 `.get` 預設值裡。\n"
              "本表的值是**量測**出來的：同一編隊、同一狀態，只切換單一條件後取 CP 比值。\n"
              "抄字面值就是再一次 F1（判例 §二十六）。\n"
              "★ 三個能見／突襲乘數自 2026-08-10 起由 `battle()` 自戰霧推導後傳入"
              "（R8-G3）。在此之前沒有任何呼叫方傳過那兩個旗標，故伏擊 ×2.0 是死碼、"
              "突襲 ×1.5 是一行 `pass`——而手冊公告過前者。見判例 §二十七。",
         addr=("rules/40_近戰.md", "§2")),

    Rule("fatigue", "疲勞效應",
         domain=[0, 20, 40, 60, 80], fn=_fatigue_row,
         header=["疲勞（起）", "組織度上限", "戰鬥效力×", "移動×"],
         row=lambda f, v: [f"{f}–{f + 19}" if f < 80 else "80–100",
                           _f(v[0]), f"{v[1]:.2f}", f"{v[2]:.2f}"],
         covers=["FATIGUE_MARCH", "FATIGUE_MARCH_NIGHT", "FATIGUE_REST_FULL",
                 "FATIGUE_COMBAT"],
         note=f"累積：行軍每小時 +{ar.FATIGUE_MARCH}（夜間再 +{ar.FATIGUE_MARCH_NIGHT}）；"
              f"戰鬥 輕 +{ar.FATIGUE_COMBAT['light']}／中 +{ar.FATIGUE_COMBAT['medium']}／"
              f"重 +{ar.FATIGUE_COMBAT['heavy']}。\n"
              f"恢復：完全休整 −{ar.FATIGUE_REST_FULL}/hr（該小時未移動、未開火、未遭擊）。\n"
              "組織度上限另受口糧危機扣減（見 70_後勤 §4）：`org_cap = 疲勞上限 − 口糧扣減`。\n"
              "★ 未實作：`movement_v1` §IV 的「接戰待命 −3／輕度活動 −1」——"
              "開火但未移動的編隊恢復量為 **0**（`docs/TODO.md` R8-G7）。",
         addr=("rules/10_地形與移動.md", "§4")),

    Rule("gun_exposure", "火砲暴露（對照戰車）",
         domain=["moved", "none", "shallow", "dug"],
         fn=lambda k: (ar.GUN_EXPOSURE[k],
                       {"moved": 1.0, "none": 0.30, "shallow": 0.15, "dug": 0.05}[k]),
         header=["狀態", "火砲", "戰車"],
         row=lambda k, v: [f"`{k}`", f"**{_f(v[0])}**", _f(v[1])],
         covers=["GUN_EXPOSURE", "GUN_VS_TANK_VULN"],
         note=f"火砲相對戰車的易損倍率 `GUN_VS_TANK_VULN = {_f(ar.GUN_VS_TANK_VULN)}`"
              "（牽引火砲無裝甲；由有效殺傷半徑 15m vs 5m 推導）。",
         addr=("rules/50_工事.md", "§5")),

    Rule("impact_coverage", "彈著覆蓋率的兩個輸入",
         domain=["靜止", "行軍", "戰車靜止", "戰車行軍"],
         fn=lambda k: {"靜止": ar.IMPACT_KM2_STATIC, "行軍": ar.IMPACT_KM2_COLUMN,
                       "戰車靜止": ar.IMPACT_KM2_STATIC_TANK,
                       "戰車行軍": ar.IMPACT_KM2_COLUMN_TANK}[k],
         header=["彈著區", "面積（km²）"],
         row=lambda k, v: [k, _f(v)],
         covers=["IMPACT_KM2_STATIC", "IMPACT_KM2_COLUMN",
                 "IMPACT_KM2_STATIC_TANK", "IMPACT_KM2_COLUMN_TANK",
                 "UNIT_AREA_KM2", "HEX_KM"],
         note="`覆蓋率 = 彈著區面積 ÷ 編隊佔地面積`。編隊佔地："
              + "、".join(f"≥{p:,} 人 {a:g} km²" for p, a in ar.UNIT_AREA_KM2) + "。\n"
              f"一格 = {ar.HEX_KM:.3f} km 見方 = {ar.HEX_KM ** 2:.2f} km²"
              "（★ `precedents.md` §二 的幾何論證寫「2 km／4 km²」，"
              "與此差 13%——`docs/TODO.md` R8-H4）。",
         addr=("rules/30_火力.md", "§6")),

    Rule("org_impact", "組織度衝擊的六項",
         domain=["連續戰鬥", "被突襲", "指揮所被毀", "團長陣亡", "友軍誤擊",
                 "工事減半", "自然恢復"],
         fn=lambda k: {"連續戰鬥": f"每小時 −{ar.SUPPRESS_PER_H}"
                                   f"（連戰 {ar.SUPPRESS_AFTER_H}+ 小時起）",
                       "被突襲": f"−{ar.SURPRISE_PEN}",
                       "指揮所被毀": f"−{ar.CP_DESTROYED_PEN}",
                       "團長陣亡": f"−{ar.REGT_CO_KIA_PEN}",
                       "友軍誤擊": f"−{ar.FRIENDLY_FIRE_PEN}",
                       "工事減半": f"×{_f(ar.COVER_FACTOR)}"
                                   f"（散兵壕級起，門檻 {_f(ar.FORT_COVER_TIER)}）",
                       "自然恢復": f"+{ar.RESUPPLY_RECOVER}/hr（補給線完整）"}[k],
         header=["項目", "值"],
         row=lambda k, v: [k, v],
         covers=["SUPPRESS_AFTER_H", "SUPPRESS_PER_H", "SURPRISE_PEN",
                 "CP_DESTROYED_PEN", "REGT_CO_KIA_PEN", "FRIENDLY_FIRE_PEN",
                 "RESUPPLY_RECOVER", "COVER_FACTOR", "FORT_COVER_TIER",
                 "FORT_TANK_TIER"],
         note="`impact = (傷亡% × 1.5 + 壓制 + 突襲 + 指揮 + 誤擊) × (工事 ? "
              f"{_f(ar.COVER_FACTOR)} : 1)`，自然恢復另加，**不被工事減半**。\n"
              f"戰車掩壕門檻 `FORT_TANK_TIER = {_f(ar.FORT_TANK_TIER)}`（淺掘對戰車無用）。",
         addr=("rules/80_狀態.md", "§1")),

    Rule("status_thresholds", "潰散與投降門檻",
         domain=["潰散 org", "潰散 24hr 傷亡", "潰散後撤", "追擊倍率",
                 "潰散恢復", "潰散解散", "投降 org", "投降 食物", "投降 無補給"],
         fn=lambda k: {"潰散 org": f"< {ar.ROUT_ORG}",
                       "潰散 24hr 傷亡": f"> {ar.ROUT_CAS_24H:.0%}",
                       "潰散後撤": f"{ar.ROUT_RETREAT} 格",
                       "追擊倍率": f"×{_f(ar.PURSUIT_MULT)}",
                       "潰散恢復": f"{ar.ROUT_RECOVER_H} 小時後 org → 30",
                       "潰散解散": f"{ar.ROUT_DISBAND_H} 小時未恢復",
                       "投降 org": f"< {ar.SURR_ORG}",
                       "投降 食物": f"RAT < {_f(ar.SURR_RAT)}% 且戰役 > 7 天",
                       "投降 無補給": f"連續 {ar.SURR_NOSUP_H} 小時"}[k],
         header=["門檻", "值"],
         row=lambda k, v: [k, v],
         covers=["ROUT_ORG", "ROUT_CAS_24H", "ROUT_RETREAT", "PURSUIT_MULT",
                 "ROUT_RECOVER_H", "ROUT_DISBAND_H", "SURR_ORG", "SURR_RAT",
                 "SURR_NOSUP_H", "POW_GUARD_RATIO"],
         note="潰散需**三條同時成立**：org 門檻 ＋ 24 小時傷亡 ＋（補給切斷 或 被包圍 或 信號中斷）。\n"
              "★ 第三條使「補給完整時 org 歸零仍不潰散」——"
              "Run 5–7 三局零潰散、零投降（`docs/TODO.md` R8-C3、`law_of_war.md` §9）。\n"
              f"受降的看管兵力 ＝ 俘虜數 × {ar.POW_GUARD_RATIO:.0%}。",
         addr=("rules/80_狀態.md", "§2")),

    Rule("scalars", "其餘係數",
         domain=["飽和上限", "攔阻射擊", "砲擊壓制移動", "友軍誤擊分攤",
                 "工事摧毀", "近戰摧毀工事", "偽裝門檻", "彈藥補給",
                 "森林（無頂蓋）", "森林（有頂蓋）"],
         fn=lambda k: {"飽和上限": f"{ar.SATURATION:.0%}／目標／小時",
                       "攔阻射擊": f"每發殺傷 ×{_f(ar.BLIND_FIRE_PENALTY)}",
                       "砲擊壓制移動": f"×{_f(ar.SUPPRESS_MOVE_MULT)}",
                       "友軍誤擊分攤": f"×{_f(ar.FRIENDLY_FIRE_SHARE)}",
                       "工事摧毀": f"{_f(ar.WORKS_DEMOLITION)} man-hr／殺傷單位",
                       "近戰摧毀工事": f"man_hours × 攻方戰力損失% × {_f(ar.MELEE_WORKS_MULT)}",
                       "偽裝門檻": f"{_f(ar.CAMO_HOURS)} 編隊工時（不乘人數）",
                       "彈藥補給": f"基數的 {ar.AMMO_RESUPPLY:.0%}／tick",
                       "森林（無頂蓋）": f"砲擊 ×{_f(ar.FOREST_NO_COVER)}",
                       "森林（有頂蓋）": f"砲擊 ×{_f(ar.FOREST_WITH_COVER)}"}[k],
         header=["項目", "值"],
         row=lambda k, v: [k, v],
         covers=["SATURATION", "BLIND_FIRE_PENALTY", "SUPPRESS_MOVE_MULT",
                 "FRIENDLY_FIRE_SHARE", "WORKS_DEMOLITION", "MELEE_WORKS_MULT",
                 "CAMO_HOURS", "AMMO_RESUPPLY", "FOREST_NO_COVER",
                 "FOREST_WITH_COVER"],
         addr=("rules/00_核心.md", "§5")),

    Rule("orbat", "編成與計分",
         domain=sorted(ar.EQUIP),
         fn=lambda k: (ar.EQUIP[k], ar.GUN_MIX.get(k, {})),
         header=["編隊種類", "戰車", "火砲", "火砲編成"],
         row=lambda k, v: [_zh(k), _f(v[0]["tanks"]), _f(v[0]["guns"]),
                           "、".join(f"{g}×{n}" for g, n in v[1].items()) or "—"],
         covers=["EQUIP", "GUN_MIX", "SCORE_W", "ARM_OF_TYPE", "TIE_BAND"],
         note="計分：" + " ＋ ".join(f"{k} ×{v}" for k, v in ar.SCORE_W.items())
              + "。友軍誤擊的自傷不計入對手戰功。\n"
              f"終局判定順序：斬首即勝 → 殲敵較多 → **殲敵相當（差 ≤ {ar.TIE_BAND:.0%}）"
              f"時自損較少者勝** → 完全平手（`verdict()`，R8-H5）。\n"
              "兵種協同依**編制內營種**（`ARM_OF_TYPE`）："
              + "；".join(f"`{k}` = " + "＋".join(sorted(v))
                          for k, v in ar.ARM_OF_TYPE.items() if k in ar.EQUIP) + "。",
         addr=("rules/40_近戰.md", "§6")),

    Rule("consumption", "資源消耗（步兵師基準，%/hour）",
         domain=["L0", "L1", "L2", "L3", "L4"], fn=lambda k: ar.CONS[k],
         header=["等級", "POL", "SA", "AT", "RAT", "MED", "PARTS"],
         row=lambda k, v: [f"**{k}**"] + [_f(v[r]) for r in
                                          ("POL", "SA", "AT", "RAT", "MED", "PARTS")],
         covers=["CONS", "MULT", "RAT_CRISIS"],
         note="兵種乘數：" + "；".join(
             f"`{t}` " + "、".join(f"{r}×{_f(m)}" for r, m in d.items())
             for t, d in ar.MULT.items()) + "。\n"
              "★ `HE` 欄已於 2026-08-10 移除（R8-G5）：砲彈自 Run 7 起以**實數發數**計（30_火力 §1），"
              "百分比的 HE 與實彈是同一批砲彈的兩套帳。\n"
              "`SA`（輕兵器彈）與 `AT`（反戰車彈）**保留**——它們沒有實彈帳，"
              "這兩欄是其唯一表示。\n"
              f"組織度上限另受口糧影響：RAT <30% −10、<10% −20（`RAT_CRISIS`，R8-G6）。",
         addr=("rules/70_後勤.md", "§4")),
]

BY_ID = {r.id: r for r in RULES}


def render_unimplemented():
    """「本局未實作的規則」表。手冊與規格書都用這一份。"""
    tag = {"none": "**未實作**", "partial": "部分實作", "superseded": "已被取代"}
    rows = ["| 規則 | 狀態 | 規範住址 | 對指揮官的意義 |", "|---|---|---|---|"]
    for u in UNIMPLEMENTED:
        rows.append(f"| {u.label} | {tag[u.status]} | `{u.addr}` | "
                    f"{(u.effect or u.why).replace(chr(10), ' ')} |")
    return "\n".join(rows)


# ── 本局未實作的規則（S4：規則書不得承諾引擎不做的事）──────────────────
#
# 指揮官是照規則書規劃的。Run 7 的手冊裡，以下每一項都**沒有**標示未實作，
# 而它們全部寫在規則書裡、讀起來像是有效的規則。
#
# 這張表是**唯一的來源**：手冊的「本局未實作」一節由它產生，
# 測試斷言每一項的住址存在。加規則而忘了標，就會在覆蓋率或住址檢查裡現形。
class Unimpl:
    def __init__(self, id, label, addr, status, why, effect=""):
        self.id, self.label, self.addr = id, label, addr
        self.status = status              # none / partial / superseded
        self.why, self.effect = why, effect


UNIMPLEMENTED = [
    Unimpl("armor_penetration", "戰車對戰車穿甲表 ＋ 命中係數表",
           "v1_archive/combat_v1.md §IV、v1_archive/determinism_v1.md §I", "none",
           "`battle()` 的第 9 步（`combat_v1` §III 結算流程「若有戰車對戰車 → 加跑穿甲表」）"
           "從未實作。戰車損失＝`equip.tanks × 戰力損失%`，與人員同比例。",
           "**規則書最精細的兩個系統連續四局零使用。** Sherman／Panther 的穿甲差異不存在；"
           "戰車只是另一個損失欄位。`docs/TODO.md` G4／Phase 4。"),
    Unimpl("pursuit_cp", "突破後追擊 攻方 ×1.4／守方 ×0.6",
           "v1_archive/combat_v1.md §II 戰術狀態表", "none",
           "CP 側未實作。追擊只從**傷亡側**實作（`PURSUIT_MULT = 3.0` 乘在潰散守方的人員損失上）。",
           "刻意不補 CP 側，否則同一件事會被計兩次。"),
    Unimpl("fatigue_alert_rest", "疲勞「接戰待命 −3／輕度活動 −1」",
           "v1_archive/movement_v1.md §IV", "partial",
           "引擎只有「完全休整 −10」或「零」。",
           "**開火但未移動的編隊，疲勞恢復量為 0。** 與 `flags[\"hit\"]` 的二元性"
           "（判例 §二十三）同一家族的離散化失真。`docs/TODO.md` G7。"),
    Unimpl("logistics_crisis", "`logistics_v1` §4 的其餘五項危機閾值",
           "v1_archive/logistics_v1.md §4", "partial",
           "已實作：POL（<20% 移動 ×0.5、<10% 停止）、RAT（<30% org 上限 −10、<10% −20）。"
           "未實作：SA／AT／MED／PARTS 的個別效果。",
           "以 `combat_v1` 的 `supply_factor`（min <30% → ×0.7、<10% → ×0.4）概括承受。"),
    Unimpl("vis_hidden_decoy", "`HIDDEN` 與 `DECOY` 兩個能見狀態",
           "v1_archive/recon_v1.md §I", "none",
           "`refresh_visibility` 只產出 EXPOSED／STANDARD／CAMOUFLAGED／CONCEALED。"
           "`VIS_REQ[\"HIDDEN\"]` 是死碼；DECOY 沒有任何引擎支援。",
           "假陣地／假目標無法部署，與 `precedents.md` §七 的空白並列。"),
    Unimpl("casualty_split", "傷亡分類 KIA／WIA-輕／WIA-重／MIA／POW",
           "v1_archive/combat_v1.md〈傷亡分類〉", "none",
           "引擎只有人員總損失，沒有分流。",
           "**`law_of_war.md` W2b（屠殺俘虜）因此是空條文**——"
           "該條的要件是「POW 於後續 tick 自人員帳中消失」，沒有 POW 帳就沒有消失可查。"),
    Unimpl("camo_material", "反偵察的物資成本（帆布 yd²、木材 bf、人時）",
           "v1_archive/recon_v1.md §VI", "superseded",
           "偽裝改為工時制（`CAMO_HOURS`，見 `50_工事.md` §3），不扣物資。",
           "指揮官不必計算帆布庫存；偽裝的成本是**時間**。"),
    Unimpl("cas_aa", "近距空中支援（CAS）與防空",
           "v1_archive/combat_v1.md §VII／§VIII、v1_archive/determinism_v1.md §IV／§VII", "none",
           "純戰場劇本雙方**皆無航空兵**，編制表裡沒有飛機。",
           "五兵種協同的上限因此是四種（步＋戰＋砲＋工）。"),
    Unimpl("counter_battery_kill", "反砲兵摧毀率「每 N 發毀一門」",
           "v1_archive/combat_v1.md §VI-4、30_火力.md §8", "none",
           "火砲損失走 `GUN_SPEC` 第四個係數與飽和上限，與「每 N 發毀一門」無關。"
           "規則書原載的 30 發已判定錯誤（幾何估算為 71 發）。",
           "彈藥改實數後現在有可能實作，列為 Run 8 待決。"),
]


# ── 覆蓋率白名單：每一項都要寫理由 ─────────────────────────────────
INTERNAL = {
    "GAME": "路徑常數，非規則",
    "STATE": "路徑常數，非規則",
    "ENEMY": "陣營對照，非規則",
    "STATUS_ACTIVE": "狀態機的字面代號",
    "STATUS_ROUTED": "狀態機的字面代號",
    "STATUS_SURRENDERED": "狀態機的字面代號",
    "STATUS_DISBANDED": "狀態機的字面代號",
    "COMBAT_STATUSES": "由上列狀態組成，非獨立規則",
    "SURR_AUTO": "投降路徑的字面代號：自行投降（law_of_war §1.W2.0）",
    "SURR_DECLARED": "投降路徑的字面代號：手動示降（可用於詐降，故與自行投降分開記）",
    "SURRENDER_FORMS": "命令文字的解析詞表（示降），非數值規則",
    "ACCEPT_FORMS": "命令文字的解析詞表（受降），非數值規則",
    "SURRENDER_HINTS": "示降／受降的近似詞表，只用於提醒裁判該命令可能有法律後果",
    "TYPE_INI": "地圖渲染用的單字元代號",
    "BEARING8": "八向方位的字面對照（落彈分析用），無可調數值",
    "RANGE_BAND": "白天距離帶的分界，已於 20_偵察 §4 以散文載明；"
                  "★ 待併入 scalars（R8-B 未完項）",
    "SOUND_MPS": "聲速物理常數，用於 flash-to-bang 的說明文字",
    "COVER_TERRAIN": "本劇本為空（純戰場無城鎮地形）",
    "HEX_KM": "已由 impact_coverage 涵蓋",
    "UNIT_AREA_KM2": "已由 impact_coverage 涵蓋",
    "FIRE_MINUTES": "已由 fire_mission 涵蓋",
    "FATIGUE_COMBAT": "已由 fatigue 涵蓋",
}


def coverage():
    """回傳 (已涵蓋, 未涵蓋)。未涵蓋即為「規則長在註冊表外」。"""
    import inspect
    covered = set().union(*(r.covers for r in RULES)) | set(INTERNAL)
    allnames = {n for n in dir(ar) if n.isupper() and not n.startswith("_")
                and not inspect.ismodule(getattr(ar, n))}
    return covered & allnames, sorted(allnames - covered)


# ── 文件區塊的產生與驗證 ───────────────────────────────────────────
def doc_paths():
    """所有可能含 rulespec 區塊的文件。"""
    out = []
    for p in sorted((ROOT / "rules").rglob("*.md")) + sorted((ROOT / "law").glob("*.md")):
        if "v1_archive" in p.parts:       # 封存件不再同步
            continue
        if BEGIN.split("{")[0] in p.read_text():
            out.append(p)
    return out


def _blocks(text):
    """回傳 {id: (完整區塊字串, 內容字串)}。"""
    pat = re.compile(re.escape(BEGIN.format("")).replace(r"\ ", " ").replace("", "")
                     if False else r"<!-- rulespec:([a-z_]+) -->\n(.*?)\n<!-- /rulespec:\1 -->",
                     re.S)
    return {m.group(1): (m.group(0), m.group(2)) for m in pat.finditer(text)}


def _render_id(rid):
    """區塊內容的產生器。`unimplemented` 是特例（不是 Rule，是另一張表）。"""
    if rid == "unimplemented":
        return render_unimplemented()
    return BY_ID[rid].render() if rid in BY_ID else None


def verify(paths=None):
    """檢查每個區塊的內容與產生結果逐位元組相同。回傳不符清單。"""
    bad = []
    seen = set()
    for p in (paths if paths is not None else doc_paths()):
        text = Path(p).read_text()
        for rid, (_, body) in _blocks(text).items():
            seen.add(rid)
            want = _render_id(rid)
            if want is None:
                bad.append(f"{Path(p).name}：區塊 `{rid}` 無對應規則")
                continue
            if body != want:
                import difflib
                d = [l for l in difflib.unified_diff(body.split("\n"), want.split("\n"),
                                                     lineterm="", n=0)
                     if l[:1] in "+-" and l[:3] not in ("+++", "---")]
                bad.append(f"{Path(p).name} §{rid}：與引擎不符（{len(d)} 行）"
                           + ("　" + " / ".join(x[:60] for x in d[:3]) if d else ""))
    for r in RULES:
        if r.addr and r.id not in seen:
            bad.append(f"規則 `{r.id}` 宣告住址 {r.addr[0]} {r.addr[1]}，"
                       f"但該文件沒有它的產生區塊（跑 `--sync` 或補上區塊標記）")
    return bad


def sync(paths=None):
    """把文件裡的區塊重寫為當前引擎的值。回傳被改動的檔案清單。"""
    changed = []
    for p in (paths if paths is not None else doc_paths()):
        p = Path(p)
        text = new = p.read_text()
        for rid, (whole, _) in _blocks(text).items():
            body = _render_id(rid)
            if body is not None:
                new = new.replace(
                    whole, f"{BEGIN.format(rid)}\n{body}\n{END.format(rid)}")
        if new != text:
            p.write_text(new)
            changed.append(p.name)
    return changed


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--verify"
    if arg == "--list":
        for r in RULES:
            print(f"{r.id:20} {r.label}")
            print(f"{'':20} 涵蓋 {sorted(r.covers) or '（量測型，無常數）'}")
        cov, miss = coverage()
        print(f"\n涵蓋 {len(cov)} 個常數；未涵蓋 {len(miss)}：{miss}")
    elif arg == "--sync":
        ch = sync()
        print("已同步：" + ("、".join(ch) if ch else "（無變更）"))
    elif arg == "--render":
        print(BY_ID[sys.argv[2]].render())
    else:
        bad = verify()
        cov, miss = coverage()
        if miss:
            bad.append(f"未涵蓋的常數（須登記或加入 INTERNAL 白名單並寫理由）：{miss}")
        if bad:
            print("❌ " + "\n❌ ".join(bad))
            sys.exit(1)
        print(f"✅ 註冊表與文件一致（{len(RULES)} 條規則、涵蓋 {len(cov)} 個常數）")
