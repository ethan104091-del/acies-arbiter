# Operation Black Tide — 黑潮行動

**戰役劇本入口檔**——本檔含**戰役特定資訊**+**全套規則引用**。系統規則本身在各 v1 檔案中。

---

## § 0 戰役元資料

- **日期**：1944-08-25 06:00 起（D+80 after Normandy）
- **地點**：法國中部、La Sève 河沿線
- **時長**：8 ticks × 6 hour = 48 hour 遊戲時間
- **地圖**：25 × 18 grid（每 hex ≈ 2 km）
- **角色**：你 = 美軍 **III Corps** 臨時指揮官（代號 Phoenix）；對方 = 德軍 Panzergruppe Hartmann（代號 Adler）

---

## § 1 戰略背景

諾曼第突破後、盟軍向東席捲。德軍在 La Sève 河構築臨時防線、試圖延緩美軍直撲德國邊境。情報顯示德軍正調動 2. Panzer 師增援前線；若該師完整投入反擊、盟軍南翼補給線將被切斷。

你接任 III Corps 臨時指揮、必須在 48 小時內：
- 強渡 La Sève 河
- 攻佔交通樞紐 **Saint-Vivien**
- 肅清沿線德軍

Eisenhower 不會等。

---

## § 2 雙方部隊（**引用 `forces_v1.md` 看 TOE 細節**）

### 美軍 III Corps（你方）

| 代號 | 番號 | 員額 | veteran |
|------|------|------|---------|
| 1ID | 1st Infantry "Big Red One" | 14,253 | ⭐⭐⭐⭐ |
| 4ID | 4th Infantry "Ivy" | 14,253 | ⭐⭐⭐ |
| 3AD | 3rd Armored "Spearhead" | 14,488 | ⭐⭐⭐⭐ |
| 90ID | 90th Infantry "Tough Ombres" | 14,253 | ⭐⭐ |

**軍級附屬：** 第 2 Ranger 營、第 4 騎兵集團、第 87 化學迫擊砲營、第 1110 工兵集團、第 56 信號營、空中聯絡組

**所有人員、武器、車輛、彈藥詳明於 `forces_v1.md` + `equipment_v1.md`。**

### 德軍 Panzergruppe Hartmann（敵方）

| 代號 | 番號 | 員額 | veteran |
|------|------|------|---------|
| 17SS | 17. SS-Panzergrenadier "Götz" | 17,983 nominal、13,200 actual | ⭐⭐⭐⭐ |
| 2Pz | 2. Panzer-Division | 13,725 nominal、11,800 actual | ⭐⭐⭐⭐⭐ |
| 352 | 352. Infanterie-Division | 12,734 nominal、7,200 actual | ⭐⭐ |

**集團群附屬：** 第 311 觀察砲營、第 7 通信集團、戰役物資池 50,000 噸

### Adler 人格

Oberst Klaus Hartmann（代號 Adler、鷹）：前東線旅長、庫斯克老兵、Manstein 學派、「Schlagen aus der Nachhand」（後手反擊）信徒。**機動防禦派、不蠻幹、保留預備隊、誘敵深入**。意識形態強硬但實事求是。

---

## § 3 初始部署（**戰役起始狀態**）

### 美軍位置

| 單位 | 起始位置 | 初始 visibility state | 初始補給 |
|------|---------|---------------------|---------|
| 1ID | (3, 8) | STANDARD | POL 90、SA 95、HE 90、AT 95、RAT 95、MED 95、PARTS 90 |
| 4ID | (4, 11) | STANDARD | POL 85、SA 90、HE 85、AT 85、RAT 90、MED 90、PARTS 80 |
| 3AD | (5, 5) F | STANDARD（森林中）| POL 80、SA 90、HE 80、AT 90、RAT 90、MED 85、PARTS 75 |
| 90ID | (3, 15) | STANDARD | POL 85、SA 90、HE 80、AT 80、RAT 90、MED 85、PARTS 80 |

戰役物資池：**120,000 噸**

### 德軍位置

| 單位 | 起始位置 | 初始 visibility state | 初始補給 |
|------|---------|---------------------|---------|
| 17SS | (18, 9) Saint-Vivien | STANDARD（城內）| POL 70、SA 80、HE 65、AT 70、RAT 75、MED 60、PARTS 55 |
| 2Pz | (22, 5) | STANDARD | POL 65、SA 80、HE 60、AT-Pz4 70、AT-Pz5 55、RAT 70、MED 55、PARTS 50 |
| 352 | (18, 14) Beaumont | STANDARD（城內）| POL 60、SA 75、HE 55、AT 50、RAT 65、MED 50、PARTS 40 |

### 客觀目標控制

| 目標 | 控制方 | 戰略價值 |
|------|--------|---------|
| Saint-Vivien (18, 9) | 軸心 | **主要勝利條件** |
| La Hêtraie (16, 2) | 軸心 | 次要 |
| Beaumont-sur-Sève (19, 14) | 軸心 | 次要 |
| Pont du Nord 北橋 (13, 3) | 軸心 | 橋 |
| Pont du Centre 中橋 (14, 9) | 軸心 | 橋 |
| Pont du Sud 南橋 (12, 14) | 軸心 | 橋 |

### 初始 fog of war

- **美軍可見**：352 在 (18,14) 大致位置（地面偵察+空偵預戰已知）
- **德軍可見**：1ID 在 (3,8)、3AD 在 (5,5)（預戰情報）
- 其他單位的具體 visibility state 玩家自行掌握與決定

---

## § 4 勝利條件

### Major Allied Victory（決定性勝利）
- Tick 8 結束前佔領 **Saint-Vivien 城本體**（market square (18,9) 街區）**且**至少一座橋

### Minor Allied Victory（戰術勝利）
- 佔領任意 **2 座橋**（即使未拿 Saint-Vivien）

### Minor Axis Victory（德軍守住）
- Tick 8 結束時 Saint-Vivien 城本體仍在德軍手中

### Major Axis Victory（德軍勝利）
- 任一盟軍師組織度 < 10%（被打殘） **或** 德軍奪回任一已失目標

---

## § 5 ★★ TOE 嚴格主義（**核心規則**）★★

> **任何指令中提到的單位、武器、人員、車輛、彈藥、物資——必須存在於 `forces_v1.md` + `equipment_v1.md` 列表中，且當前庫存允許。否則該指令部分視為無效，不被執行。**

### 範例：合理但不存在 = 無效

```
你下令：「派 2 個 Tank Destroyer 連的 Hellcat M18 反擊」
我檢查 forces_v1：1ID/4ID/90ID 是步兵師、無 attached TD bn
                3AD attached 第 703 TD 營是 M10 Wolverine、不是 M18 Hellcat
→ ❌ 拒絕。提醒：「你方 TD 是 M10 × 36（in 3AD）、不是 M18。改 M10？」

你下令：「使用熱顯像儀偵察敵戰車」
我檢查 equipment_v1：1944 美軍無熱顯像儀
→ ❌ 拒絕。理由：技術未發明（直到 1950s）

你下令：「派 OSS 接觸法國地下抵抗組織」
我檢查 forces_v1：OSS 確實存在於戰役期間、合理
但 equipment_v1 無 OSS 詳細編制
→ ⚠️ 接受但限定範圍：「OSS 接觸僅能提供粗略戰略級情報、不能提供戰術級具體座標」

Adler 下令：「派 Tiger I 連反擊」
我檢查 forces_v1：17SS 主裝甲是 Stug III × 41、**無 Tiger**
                2Pz 是 Panther + Pz IV、**無 Tiger**
→ ❌ 拒絕。理由：本戰役無 Tiger（Tiger Bn 在東線）

Adler 下令：「動員 4 個營反戰車組」
我檢查 forces_v1：17SS Panzerjäger 共 ~600 人、不夠 4 個營級規模
→ ⚠️ 接受但縮至實際規模：「可動員師屬 PaK 40 × 23 + Marder × 9 + Hetzer × 6 = 約 38 個砲位」

你下令：「Ranger 連 + 第 2 個 Ranger 連 + 第 3 個 Ranger 連同時 3 路滲透」
我檢查 forces_v1：第 2 Ranger 營有 6 個連（A-F）、可 3 路
但 equipment_v1 規定「6 個 Ranger 連可同時執行 6 個獨立任務、不可超過」
→ ✅ 接受。扣 3 個連使用記
```

### 範例：合理且存在 = 通過

```
你下令：「3AD 用 8 輛 76mm Sherman + HVAP 鎢芯穿甲打 Panther」
我檢查：3AD 有 76mm Sherman × 32 輛、HVAP × 400 發庫存
8 輛打戰 4 hour ≈ 48 發 HVAP
→ ✅ HVAP 400→352。提醒「鎢芯戰役總額已用 12%」
```

### 物資池追蹤

`state.json` 起始時記載每師完整資源池（POL、SA、HE、AT、RAT、MED、PARTS + 特殊物資如帆布、沙包、TNT、車輛各型號數量）。每次戰鬥/移動結算時扣具體數量。**池空 = 該行動不可執行**。

### Adler 也受同樣約束

Adler 不能下「召喚備援師」「Tiger 突然到位」「無中生有 88 砲位」這類超 TOE 命令。他的軍級附屬只有那些。

---

## § 6 系統規則引用

所有非劇本特定的規則在各 v1 檔案中。**戰況解算以本表為準：**

| 類別 | 規則檔 | 內容 |
|------|--------|------|
| **時間與指令** | `rules_v2.md` | Tick/Hour 結算、L1/L2/L3 命令延遲、Adler 應變條件、Version A 不對稱、日夜 |
| **部隊編制** | `forces_v1.md` | 7 個師 TOE、軍級附屬、空軍 sortie 配額 |
| **單兵與物資** | `equipment_v1.md` | 兵種別單兵負荷、物資池（沙包/鐵絲/帆布/醫療/食物/POL）|
| **補給/後勤** | `logistics_v1.md` | 7 資源類型、L0-L4 消耗等級、車隊系統、interdiction、危機閾值 |
| **偵察與情報** | `recon_v1.md` | 5 級 visibility state、偵察手段對應表、徵候判讀、信心等級 |
| **戰鬥解算** | `combat_v1.md` | 8 因子 CP 公式、穿甲表、傷亡分流、潰散觸發、城戰、砲擊、CAS、AA |
| **天氣** | `weather_v1.md` | 戰役每 6 hr 確定天氣表、對作戰的影響 |
| **移動細節** | `movement_v1.md` | 道路網、擁塞、疲勞、機械故障、橋樑容量 |
| **城戰專章** | `urban_combat_v1.md` | 城鎮分區、逐棟結算、戰車城內、下水道、平民 |
| **兵種協同** | `combined_arms_v1.md` | 5 兵種倍率、FO/FDC/FAC/ALO 鏈條 |
| **確定公式** | `determinism_v1.md` | ★ 所有戰鬥/偵察/砲擊/CAS/AA/補給算式 canonical |

**衝突時以 v1 規則檔為準、本檔僅補劇本特定資訊。**

---

## § 7 戰役特殊規則

### 1. Saint-Vivien 政治紅線
- Saint-Vivien 為德軍中央集團軍南翼支點
- Adler 收到 OKW 命令「絕不放棄」——他若放棄面臨軍事法庭
- 戰役 narrative：Adler 內心 vs 上級壓力的張力

### 2. 法國平民疏散政策
- 美軍受國際輿論限制（**重砲集中 + 平民留城**有政治代價）
- 德軍可徵用平民（**戰爭罪風險**：占領區徵用有戰後法律代價）
- 法國地下抵抗組織存在於 Saint-Vivien 周邊村莊（OSS 可接觸）

### 3. Beaumont 焦土合法性
- 德軍若放棄 Beaumont 可實施焦土
- 美軍視之為「合法軍事行動」（戰爭法允許退守前破壞）
- 但平民/民用財產破壞會影響戰役結束後重建

### 4. 戰役物資池上限
- 美軍 120,000 噸（諾曼第後補給優勢）
- 德軍 50,000 噸（東補給線受空優干擾）
- 池子用盡 = 無新車隊可派、依現有庫存戰鬥

### 5. Adler 集團軍級緊急請求
- 每 24 hour Adler 可請求 1 次集團軍緊急支援（Stuka staffel / 砲兵）
- 命中差、僅作壓制作用
- 屬軍級附屬之外的偶發資源、不必預申請

### 6. 美軍空中支援優先序
- IX TAC 戰役全期配額：**~480 sortie**
- 戰役任何時刻最多 ~12 sortie 在空中
- 暴雨/強雲 CAS 受限（依 `weather_v1.md`）

### 7. 雙方無 Tiger / Panther 增援
- 此戰役期間（1944-08-25 至 27）**雙方無新增戰車師抵戰場**
- 損失即損失、不可空降補充

### 8. 戰役起始天氣
- Tick 0-3 晴朗多雲（CAS 黃金窗口）
- Tick 4 起小雨開始（CAS 效率打折）
- Tick 6-7 中雨（CAS 大部分取消、地面泥濘）
- 詳見 `weather_v1.md` 完整 8 tick 天氣表

---

## § 8 戰役開戰預備清單

**Game Master（我）開戰前需準備：**

- [x] state.json 起始狀態（依本檔 § 3）
- [x] 戰役物資池（美 120k / 德 50k 噸）
- [x] 天氣 8 tick 完整表載入
- [x] Adler agent 起始人格（Hartmann persona + 8 條應變條件起始空）
- [x] map.py refresh

**玩家（你）開戰前可做：**

- [ ] 閱讀 `rules_v2.md` § 1 Version A（你的指令系統）
- [ ] 瀏覽 `forces_v1.md` 確認你方 TOE 細節
- [ ] 瀏覽 `combat_v1.md` § II 戰鬥力公式（理解戰局怎麼算）
- [ ] 瀏覽 `recon_v1.md` § I-II（理解偵察的確定性）
- [ ] 開好 map.py 終端機（`python3 ~/war-game/map.py`）

**開戰指令：** `推進` 或 `開戰`

---

## § 9 戰役歷史備註

本劇本為原創、不對應真實 1944 歷史戰役、但材料合理：
- 1944-08-25 為 D+80（諾曼第登陸後 80 天）、盟軍突破 Cotentin、向東開展
- La Sève 河為虛構、合理位於諾曼第與 Reims 之間
- Saint-Vivien 為虛構小鎮（合理規模、合理位置）
- 雙方部隊皆為當時實際存在的師（17. SS-Panzergrenadier "Götz von Berlichingen"、2. Panzer-Division、352. Infanterie-Division、1st/4th/90th Infantry、3rd Armored）
- TOE 數字依 1944-08 實際資料、加少量戰役期間損耗調整

**Run 1 戰役紀錄** 已寫成歷史風格紀念於 `battle_record.md`。
