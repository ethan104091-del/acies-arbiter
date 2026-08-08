# Run 8 開局前的工程計劃（2026-08-08）

> 依據：`docs/TODO.md` 的 R8-A ～ R8-H（Run 7 檢討 ＋ 2026-08-07 規則重讀稽核）。
> 本檔只講**怎麼修**。為什麼要修、依據在哪，一律回去看 TODO 與 `law/precedents.md`。
>
> **設計原則:不修那 26 個項目,修產生它們的四個結構。**
> 逐項修完只保證這一批不再犯；結構不動,下一局會長出新的一批。

---

## 〇、四個結構問題與對應的四個結構解

| # | 結構問題 | 結構解 | 消掉哪些項目 |
|---|---|---|---|
| **S1** | 規則有三個住址(引擎／規格書／手冊),而且**引擎的行為有一部分不可列舉**(`.get(n, 1.7)` 這種預設值) | **規則註冊表 `rulespec.py`**:每條玩家可見的規則登記為「定義域 ＋ 求值函式 ＋ 規範住址」。手冊、規格書檢查、稽核全部從它產生 | F1、B1、B2、G8、H3、H4、H7 |
| **S2** | 「雙方皆適用」的規則被實作成裁判寫的清單或腳本步驟——**裁判的手是執行路徑,而手沒有閘門** | **命令清單(manifest)＋引擎內建護欄**:tick 腳本必須交出機器可讀的動作清單,`_audit` 逐項對帳；能搬進引擎的護欄一律搬進去 | A1–A5、G1、G2、D5 |
| **S3** | 一致性檢查在用字串比對(已第四次) | **結構化比對**:解析文件的表格再與註冊表逐值對照；`_audit` 同理 | F1 的測試面、D6、L 段其餘 10 項 |
| **S4** | 規則書承諾了引擎不做的事,而指揮官照規則書規劃 | **實作狀態標記 ＋ 手冊列出「本局未實作」**,並用測試強制兩者一致 | G3–G7、H5、H6、H8、H9 |

---

## 一、Phase 1 — S2:把規則搬進引擎(最高優先)

### 1-A `battle()` 自己執行逼退,含**兩個方向**

現況:`battle()` 只回傳 `push`,執行交給腳本。`push > 0` 是守方後退,
**`push == -1` 是攻方被逼退(兵力比 <0.5)——四局以來所有腳本都寫 `if push > 0`,
攻方逼退從未執行過。**

```python
# arbiter.py
def battle(...) -> tuple[str, dict]:
    ...
    moved = _execute_push(s, atk_uids, def_uids, push)   # 正負都處理
    return detail, {"push": push, "displaced": moved}    # moved: uid -> 實際格數
```

- `forced_push()` 自 `runs/_tickkit.py` **搬進 `arbiter.py`**(語意是引擎的,不是工具的)。
- 逼退不受移動速率／疲勞／POL 限制,只受地形可通行性與地圖邊界限制(§二十五 已裁定)。
- 方向:守方朝其補給源；**攻方被逼退時朝攻方的補給源**(即退回發起方向)。
- 回傳 `displaced` 讓 `_audit` 能對帳(見 1-D 的 A5)。
- `runs/_tickkit.forced_push` 保留為薄殼並發 `DeprecationWarning`,避免歷史腳本壞掉。

### 1-B `advance()` 拒絕進入敵佔格,`approach()` 也搬進引擎

裁示 47 目前是「規定裁判不得對敵佔格呼叫 `advance`」——靠注意力。

```python
def advance(s, uid, dest, ...):
    if _enemy_combat_units_at(s, dest, side):
        return {"ok": False, "reason": "ENEMY_HELD", "hint": "移入敵佔格＝近戰突擊，須呼叫 battle()"}
```

- **只擋最後一步進入,不擋整段接近**(§二十四 錯誤二的教訓)。
- `approach()`(目標格被佔 → 改走最近的可通行相鄰格；已在相鄰格 → 回 None)一併搬進引擎。
- 呼叫方沒檢查回傳值也不會靜默錯:`ok=False` 時不改變任何狀態,而 1-D 的 A4 會抓到「登記了目的地卻沒動」。

### 1-C 命令清單(manifest):本階段的承重牆

四個 Run 7 錯誤(§二十一 構工批次化、§二十四 三連錯、§二十五 逼退、G1)共同的可稽核化前提,
是**讓「這個 tick 允許發生什麼」變成資料**。

```python
# runs/_manifest.py
@dataclass
class TickOrders:
    tick: int
    move:    dict[str, tuple[int, int]]        # uid -> 目的地
    dig:     set[str]                          # 明確下令構築工事者
    camo:    set[str]                          # 明確下令偽裝作業者
    fire:    list[FireOrder]                   # (shooters, target|hex, mission)
    barrage: list[BarrageOrder]                # 攔阻射擊(格)
    src:     dict[str, str]                    # 每個動作 -> 命令出處「紅軍 T5 第 3 條」
    contingency: list[str]                     # 本 tick 登記的應變條件原文

    def validate(self):
        """每個登記的動作都必須有非空的 src。無出處即報錯。"""
```

- **`dig` / `camo` / `barrage` 三者手冊明定須明文下令**,故 manifest 建構時
  禁止 `set(DEST)`、`all_units`、或任何由其他集合推導的形式——
  以型別強制:這三個欄位只接受 `frozenset[str]` 的字面列舉,且 `src` 必須逐 uid 齊備。
- **每個 tick 的 manifest 必須重新建立**(D5 從紀律變成必要輸入:`TickOrders(tick=n)`
  不接受從上一個 tick 的物件複製)。

### 1-D `_audit` 從八項擴到十四項

`_audit.reconcile(before_snapshot, after_state, manifest)`:

| # | 檢查 | 抓到哪次瑕疵 |
|---|---|---|
| **A3** | `works[hex].man_hours` 或 `camo_hours` 增加,而該編隊不在 `manifest.dig/camo` → 報錯 | §二十一(白給 13,988 man-hr) |
| **A4** | 位置變化,而其方向與 `manifest.move[uid]` 不一致,且不能歸因於 `displaced` 紀錄 → 報錯 | §二十四(沿用舊目的地) |
| **A5** | `battle` 回傳 `push ≠ 0`,而對應編隊的位移 < |push| 且未達邊界／不可通行 → 報錯 | §二十五(逼退當行軍)、**G1(攻方逼退)** |
| **A6** | 有 `flags["fired"]`,而該編隊不在 `manifest.fire` 也不在應變觸發紀錄 → 報錯 | 未發生過,但同一類 |
| **A7** | `manifest.validate()` 失敗(有動作無出處) → 報錯 | §二十一 的根因 |
| **A8** | 敵佔格內出現以 `advance` 抵達的編隊 → 報錯 | §二十四(裁示 47 單方清單) |

**稽核必須在印出計分之前跑完**(§十二 已定,保留)。

### 1-E 回歸網:不重跑 Run 7,而是對快照做黃金測試

1-A／1-B 改變引擎行為,**整局重跑必然與紀錄不同**(腳本自己也在做逼退)。
且 `runs/run4-6`(以及 Run 7 作為稽核紀錄)不得編輯。

故改為:讀 `snap_T*start.json`,對 Run 7 實際發生過的每一場近戰,
斷言新引擎的 `battle()` 產出的傷亡與日誌記載**逐值相同**。
覆蓋 T5／T7／T8 共 12 場、含那 12 次 4 兵種解算。這比整局重跑更精準,且不動歷史檔。

---

## 二、Phase 2 — S1＋S3:規則註冊表與結構化比對

### 2-A `rulespec.py`

```python
Rule(
    id="combined_arms",
    addr=("rules/arbiter_v2.md", "§XI"),      # 規範住址
    domain=range(1, 7),                       # 定義域
    fn=lambda n: ar.COMBINED.get(n, 1.7),     # ★ 存函式,不存 dict
    label="兵種協同倍率",
    unit="×",
)
```

**為什麼存函式而不存常數:F1 的整個根因。** `COMBINED` 只有三個鍵,
自動產生器取得到的就只有三級；把「求值函式 ＋ 定義域」登記起來,
第四級才會被枚舉出來。凡是以預設值、`or`、`max()`、`min()` 表達的規則都同理。

首批登記(即現行手冊涵蓋的全部):
`FORT_TIERS`／`DIG_RATE`／`CAMO_HOURS`／`RATE`／`SIGHT`／`VIS_REQ`／`GUN_SPEC`／
`AMMO_LOAD`／`AMMO_RESUPPLY`／`FIRE_MISSION`／`SATURATION`／`BLIND_FIRE_PENALTY`／
`FR_TABLE`(含**後兩列的逼退格數**,G2)／`COMBINED`／`VET`／`BASE_POWER`／
`FATIGUE` 階梯／`CONS`＋`MULT`／`GUN_EXPOSURE`／`IMPACT_KM2_*`／`UNIT_AREA_KM2`／
`SUPPRESS_MOVE_MULT`／`FRIENDLY_FIRE_SHARE`／`WORKS_DEMOLITION`／`MELEE_WORKS_MULT`／
CP 乘數鏈(地形／伏擊／被動／行軍中接戰)。

### 2-B 三個消費端全部改從註冊表產生

| 消費端 | 現況 | 改為 |
|---|---|---|
| `gen_handbook.py` | 數字自引擎取,**算式與敘述手寫** | 表格全部 `rulespec.render(id)`；手寫散文只准出現在「為什麼」的段落,不准含數字 |
| `tests` L 段 | 11 項 `inspec("...", "1.3")` 逐字比對 | `test_spec_drift`:解析 `Rule.addr` 指到的那一節的表格,逐 `domain` 與 `fn` 比對 |
| `_audit` | 八項硬編碼 | 能由註冊表推導的門檻改為讀註冊表 |

### 2-C 覆蓋率測試(防止新規則又長在註冊表外)

```python
def test_no_unregistered_player_visible_constant():
    """arbiter.py 的模組級常數,必須或登記於 rulespec,或列於 INTERNAL 白名單。
    白名單須逐項寫理由——讓「忘記登記」變成加白名單時會被看見的動作。"""
```

### 2-D 手冊產出的回歸

重寫 `gen_handbook.py` 有改動手冊內容的風險。
故:先對 Run 7 的手冊做 byte-diff,**只允許出現預期中的差異**
(協同第 4 級、`FR_TABLE` 後兩列、未實作清單三處),其餘一律視為迴歸。

---

## 三、Phase 3 — S4:把「未實作」變成明文,並用測試鎖住

### 3-A 每一節加實作狀態標記

規格書每個 `##` 節首加一行:

```
<!-- impl: full | partial | none | superseded-by: <addr> -->
```

測試強制:
- `full` → 該節提到的每個常數都要在 `rulespec` 有登記
- `none` / `partial` → 必須出現在手冊的「本局未實作／部分實作」清單裡
- `superseded-by` → 目標住址必須存在

### 3-B 手冊新增一節「本局未實作的規則」

指揮官是照規則書規劃的。目前這些沒有一項標著未實作:

| 項目 | 處置 |
|---|---|
| 戰車對戰車穿甲表 ＋ 命中係數表(G4) | **標 none**。是否實作見 Phase 4 |
| 突襲 攻方 ×1.5(G3) | **實作**(一行,且守方伏擊 ×2.0 已有,不做就是偏向守方) |
| 突破後追擊 攻方 ×1.4／守方 ×0.6(G3) | 標 none(`PURSUIT_MULT` 已從傷亡側實作,避免重複計算) |
| 疲勞「接戰待命 −3」(G7) | **實作**(併入 Phase 4 的 C1,同一家族) |
| `logistics_v1` §4 七項危機閾值(G6) | POL 已實作；`RAT<30% → org 上限 −10` **實作**；其餘標 superseded-by `combat_v1` 的 `supply_factor` |
| 彈藥雙軌記帳(G5) | **移除** `CONS` 的 HE／SA／AT 三欄與其在 `supply_factor` 的角色。實彈已是唯一帳 |
| HIDDEN／DECOY 能見狀態(H6) | 標 none,與 `precedents.md` §七 的「假陣地」並列 |
| 傷亡分類 KIA/WIA/MIA/POW(H8) | 標 none,並在 `law_of_war.md` W2b 註明**本條為空條文**(無 POW 帳即無「消失」可查) |
| `recon_v1` §VI 帆布 yd² 成本表(H7) | 標 superseded-by `arbiter_v2` §III |
| `rules_v2` §2 Version B「未來實作」(H9) | 刪除該標記,改寫為現行 PvP 模型的入口(見 3-C) |
| 平手判準(H5) | **實作**:`score()` 加回傳 `self_loss`；「殲敵相當」定義為**差距 ≤ 總分 2%** |

### 3-C 新增 `rules/command_v2.md` — 應變欄的規範住址

**目前最嚴重的規範真空:決定了 Run 7 三個轉折的機制沒有住址。**
`rules_v2.md` §1 把應變定義為 Version A 的 Adler 專屬(8 條、觸發即生效、用過即無),
§2 的 PvP 完全沒有應變,且仍標「未來實作」。手冊給雙方 6 條,**從未把零延遲寫成規則**。

新檔涵蓋(取代 `rules_v2.md` §1／§2,並吸收 `scenario_open_field.md` §5-B):

1. 命令延遲階梯 L1／L2／L3 ＝ 1／2／3 小時
2. 指揮所三段(未建 +2 級／主 +1 級／前進 0 級,`FWD_RANGE` 6 格、須前於本方編隊中位數 x)
3. 架設 `CP_SETUP_HOURS = 2`,拆設同
4. **應變欄**:每 tick 最多 6 條；**觸發即生效,零延遲**；用過即無；不跨 tick 保留；
   位移類執行到完成為止(付移動的全部代價)；條件須可由 state 客觀判定
5. 主令每 tick 最多 8 條,各自標 L1／L2／L3
6. 提交窗口規則(§二十:tick 內公告新裁示 → 窗口對雙方重開)

---

## 四、Phase 4 — 需要重新校準的三項(不進最小集合)

| # | 項目 | 為何不進最小集合 | 做法 |
|---|---|---|---|
| **C1** | `flags["hit"]` 改為累積發數 | 連動傷亡、休整、工事、能見四個系統——**是重新縮放,不是修 bug** | 記錄該小時承受總發數；休整恢復量與構工進度按比例折減而非歸零;參考發數由史實錨定。併入 G7(接戰待命 −3) |
| **C2** | 同格疊放的密度懲罰 | 改 `impact_coverage` 會動到全部砲擊校準 | 加入同格編隊數的壓縮項；重跑「每 100–300 發 1 人傷亡」錨點驗證 |
| **G4** | 戰車對戰車穿甲表 | **規則書最精細的兩個系統連續四局零使用**,但接上去是新的平衡 | 在 `battle()` 內新增獨立的裝甲對抗步驟(只在雙方皆有 `tanks > 0` 時跑),與 FR 表的戰車損失**擇一**而非疊加；接上前先跑校準對照(同一場近戰,新舊兩法的戰車損失差多少) |

**C3(補給完整時 org 歸零仍不潰散)的處置與上面不同,見下。**

---

## 五、三個需要裁定的問題與建議

### 決定 1:劇本長度 — 建議 **54 小時(T0–T8,9 個 tick)**

`scenario_open_field.md` 寫 48,實際三局都跑 54。建議改文件而非改實作:
- 三局的快照是唯一的可比較基準,改成 48 會使 Run 5–7 不可比
- `law_of_war.md` §1.W2 對投降四條件的可達性盤點須連帶重算
  (「連續 48 小時無補給」在 54 小時劇本裡從 T0+6 起就可達,原註「極限」要改)
- `arbiter.py` 的 `SURR_RAT` 註解「48 hour 劇本永不成立」照樣成立(食物條件需 >7 天)

### 決定 2:戰爭法三局零觸發 — 建議 **不改 W1,改 ROUT,並在手冊揭露誘因**

W1 要件 C(補給走廊切斷)在 Run 5 被主張放寬、被駁回,理由「一個能撤走的單位不是屍體」。
**那個論證仍然成立,不建議推翻。** 真正的病灶有兩個,都不在法條:

1. **`ROUT` 需「補給切斷 或 被包圍 或 信號中斷」,故 org 歸零也不潰散。**
   建議:`org ≤ 5 持續 ≥ 3 小時` **視為指揮鏈中斷**——一支凝聚力歸零的編隊在事實上已失去指揮鏈。
   這是物理讀法、雙方對稱、且開啟 `law_of_war` 期待的自然路徑(org 崩潰 → 潰散 → 被殲滅或投降)。
2. **切走廊沒人試過。** 彈藥實數化(Run 7)已使「切斷 → 補給為零 → 砲兵一個 tick 內打光」成立,
   但三局無人嘗試。建議在手冊的開局提示明白寫出這條因果——**不是改規則,是把已存在的誘因說清楚。**

W1 是否仍零觸發,留到 Run 8 之後再判。

### 決定 3:F1 要不要發給雙方指揮官 — 建議 **要發**

手冊給了錯的協同倍率,雙方逐位元組相同、錯得一樣,而藍軍是實際受益者
(只有它做過裝甲＋步兵的聯合突擊)。依既有紀律,對稱裁示可以手寫但必須對雙方逐位元組相同。
形式:終局戰報的勘誤,內容為 `law/precedents.md` §二十六 的事實與可驗算的三行對照表。

---

## 六、排序與相依

```
決定 1／2／3          ← 需要裁定,不阻塞 Phase 1
      │
Phase 1  S2  1-A 逼退進引擎(含 push<0) → 1-B advance 護欄
              1-C manifest → 1-D _audit 六項新檢查 → 1-E 黃金測試
      │
Phase 2  S1  2-A rulespec → 2-B 三個消費端 → 2-C 覆蓋率 → 2-D 手冊 byte-diff
      │
Phase 3  S4  3-A 實作狀態標記 → 3-B 手冊未實作清單 → 3-C command_v2.md
      │
      ├─ 可開 Run 8 ─────────────────────────────
      │
Phase 4      C1 / C2 / G4(各需校準,任一項都可延後到 Run 9)
```

**開局前的最小集合＝Phase 1 ＋ Phase 2 ＋ Phase 3。**
Phase 1 不做完就開局,等於保證重犯 Run 7 的同一批錯(A 組原本的結論)。
Phase 2 不做完,手冊會再一次在對局中途被指揮官的提問揭發。
Phase 3 最便宜而收益最直接:**它讓指揮官不再照著不存在的規則規劃。**
