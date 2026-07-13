# 料鋒 Acies — 技術備忘（樞衡 Arbiter 引擎）

**命名（2026-06-10 定）**：
- **料鋒 / Acies（阿基耶斯）** = 遊戲名（面向玩家）。
  - 拉丁 Acies 一詞雙關「軍陣/鋒線」+「銳利目光/洞察」。
  - 中文「料鋒」對應雙義：**料**(料敵制勝·迷霧推理，《孫子》出處) + **鋒**(兵鋒鋒陣·列陣對抗)。
- **樞衡 / Arbiter（阿比特）** = 引擎/平台名(可重用)。
  - 拉丁 Arbiter = 羅馬法律術語,中立全知仲裁。
  - 中文「樞衡」(真實古詞,中樞權衡之職)對應雙義：**樞**(系統中樞·全知軸心) + **衡**(權衡裁決·零機率由規則定)。
- 完整：**料鋒 Acies — a wargame on the 樞衡 Arbiter engine**。

**最後更新**：2026-06-10
**專案路徑**：`~/war-game/`（資料夾名沿用，專案名為 料鋒 Acies）
**首場戰役紀念**：`battle_record.md`（Run 1 已落幕，紀錄體式戰史）

---

## 1. 專案是什麼

**料鋒 Acies** — 終端機 WWII 師級戰棋,跑在 **樞衡 Arbiter** 引擎(LLM 當裁判)上。玩家當美軍 III Corps 指揮（代號 Phoenix），對 Claude opus 扮演的德軍 Adler agent 打 48 小時 Saint-Vivien 戰役（首個劇本 Operation Black Tide 黑潮行動）。
引擎可換 scenario 打其他戰役(庫斯克/阿登)。

地圖 25×18 grid、Rich TUI 顯示、state.json 為單一 source of truth。

## 2. 已玩過的場次

- **Run 1**：8 tick 全程跑完，Major Allied Victory。靠 3AD 北線詐術 + 南橋夜拆 + Tick 8 CAS 斬首市政廳。Adler 演到精湛被 Weber 接掌、Luger 結束自己。完整戰史寫在 `battle_record.md` 290 行。
- **Run 2**：開到 Tick 2 玩家投降（敘事性結束「Phoenix 自制」）。新 Adler 沒拆北橋預埋、被 3AD 直衝過河。Run 2 沒寫 record。

## 3. 規則系統現狀（v1 確定性）

整套 5,671 行、12 個檔案。**零機率**（2026-05-28 全面去機率化）：

```
scenario.md              269 行   戰役入口 + ★ TOE 嚴格主義
rules_v2.md              230 行   時間+命令延遲（L1/L2/L3）
logistics_v1.md          301 行   7 類資源（POL/SA/HE/AT/RAT/MED/PARTS）
forces_v1.md             473 行   雙方 7 個師完整 TOE
equipment_v1.md          638 行   單兵負荷+物資池細目
recon_v1.md              410 行   5 級 visibility state + 確定觀察結果
combat_v1.md             742 行   8 因子 CP 公式 + 穿甲表
weather_v1.md            265 行   1944-08 戰役每 6hr 確定天氣
movement_v1.md           378 行   道路網+擁塞+疲勞+故障
urban_combat_v1.md       458 行   城戰逐棟+下水道+平民
combined_arms_v1.md      488 行   5 兵種協同倍率
determinism_v1.md        568 行   ★ 所有公式 canonical
```

## 4. 核心設計決策（紀錄、避免反悔）

### A. 不擲骰
所有結果由具體輸入確定產生。
**不確定性的來源**只有 3 個：
1. 資訊不對稱（你不知對方做了什麼）
2. 隱藏狀態（對方部隊真實狀態）
3. 徵候推理（看到的是徵候、不是結論）

### B. 不對稱命令系統（Version A）
- 你：每 hour 可下臨時令、依複雜度 L1/L2/L3 延遲（1/2/3 hour 生效）
- Adler：tick 開頭下計畫 + 最多 8 條應變條件、不能 hour 級反應
- 預留 Version B（多人對等版）但未實作

### C. TOE 嚴格主義
任何指令提到的單位/武器/車輛/彈藥必須在 `forces_v1.md` + `equipment_v1.md` 列出、且當前庫存允許。否則視為無效。雙方對等受約束（Adler 不能無中生有 Tiger）。

### D. 時間粒度
Tick = 6 hour 大決策週期；每 hour 結算+報告；有事件 hour 詳報、無事件壓 1 行。

### E. 天氣戰役寫死
1944-08-25 到 27 每 6 hour 天氣確定預定（晴→雨→泥濘）。CAS 黃金窗口在 Tick 0-3、Tick 4 起 CAS 效率降。

## 5. State.json 結構（需更新對應新規則）

舊版只有 `supply: 70`、需改成：
```json
"units": {
  "1ID": {
    "resources": {
      "POL": 90, "SA": 95, "HE": 90, "AT": 95,
      "RAT": 95, "MED": 95, "PARTS": 90
    },
    "visibility_state": "STANDARD",
    "fatigue": 0,
    "broken_down_vehicles": {...},
    ...
  }
}
```

~~`state.json` 目前還是 Run 2 結束時的舊格式~~ → **✅ 2026-05-29 已升級**：Run 3、Tick 0、每師 7 欄 `resources` + `fatigue` + `visibility_state` + `broken_down_vehicles`，並新增 `campaign_pool`（盟 120k/軸 50k 噸）與 `weather_state`（current + forecast + 8-tick campaign_actual 寫死表）。fog_of_war 重置為開戰預戰情報。

## 6. 工具（2026-05-29 大改版：地圖重設計 + 指揮官圖標，三檔分工 file-based 橋接）

- **`mapcore.py`** — 共用渲染核心 (library)。map.py 與 commander.py 都 import 它，座標系/標註 schema/地形/兵種定義單一來源。
  - 風格 A 擬真地形 + **固定欄位網格**：主豎線 `│` 每5格、underline 橫線每5列、四邊座標。線在專屬欄位，**永不被內容推移、不擋地形、不斷裂**（踩過很多坑才定案，勿改回「線跟內容搶格」的舊法）。
  - 離散地物（森林♣♣ /丘陵︿）尾留 1 空 → 格界靠自然空隙，不靠次線（次線會造成滿版分裂感，已棄）。
  - underline 列把「無筆畫處前景」統一成 `ULINE_FG`，否則橫線會跟著各格文字色變成一節一節（坑）。
  - 單位格 4 寬 = 番號 + 兵種(●步▲裝■擲◆摩,黃) + 朝向箭頭(亮白)，**同時顯示**。
  - API：`load()` / `index_state(s)` / `load_annot()` / `build_overlay(annot,W,H)` / `render_A(...,cursor=)` / `render_map(state,annot,grid,cursor,preview)`。
  - 也可獨立跑 `python3 mapcore.py 1|2|3|all` 看三風格對比（B=NATO、C=儀表，備選）。
- **`map.py`** — 即時檢視器 (viewer)。`python3 ~/war-game/map.py`。左側地圖(mapcore)+補給細目+指揮官圖層摘要，右側戰況/部隊/氣象/敵情/戰報。每 0.5s file-watch state.json + annotations.json 自動重繪。
- **`commander.py`** — 指揮官圖標編輯器 (curses 互動)。`python3 ~/war-game/commander.py`。方向鍵/hjkl 移游標，`m`標記 `t`文字 `a`箭頭(起→迄) `p`折線(多點,Enter結束,Esc取消) `H`單位朝向 `g`換標記字元 `c`換色 `d`刪除 `s`存 `r`重載 `q`離開 `?`說明。寫 annotations.json → map.py 自動重繪。
- **`annotations.json`** — 指揮官標註圖層。schema：`annotations[]`（type=marker/text/arrow/polyline/phase_line + pos/from/to/points + color + label）、`headings{uid:方位}`。viewer 唯讀、editor 互動編輯。phase_line=直線(平直管制線)、polyline=折線(沿河蜿蜒戰線)。
- **`map_proto.py.bak`** — 舊 prototype，被 mapcore.py 取代，封存備查。
- **舊格式相容**：`_avg_supply()` 同時吃新 `resources` dict 與舊 `supply` int。
- **終端機需求**：支援 underline（横線靠它）、256 色。overline 不可靠（user 終端機不支援，已改 underline）。
- **待加（次要）**：Adler 應變條件指示器、commander 的座標直接跳格輸入、phase_line 直線專用工具（目前用 polyline 代）。

## 6b. 多人 1v1 對戰（2026-06-02 新增，Version B）

完整操作手冊見 **`multiplayer.md`**。架構：你的 Mac = GM + 權威 state + server；對手 = 遠端 client；Claude = 裁判。

- **`mapcore.py`** 新增戰爭迷霧：`index_state(s, viewer_side)` 與 `render_map(..., viewer_side)`，三視角 god/allies/axis。`filter_state_for(state, side)` 產生「server 端過濾」的安全 state（敵方只露 位置/類型/概略兵力 strength_approx，未偵獲者消失，盟軍視角拿掉 axis_commander）。改迷霧只動這幾處。
- **`server.py`** — 跑你 Mac。`python3 server.py --port 8000`，自動產 token。端點：`GET /state?side=` `GET /report?side=` `POST /order?side=` `GET /ping`，全驗 token。對外靠 `cloudflared tunnel --url http://localhost:8000`。
- **`client.py`** — 對手端。`python3 client.py --url <網址> --token <t> --side axis`。選單 v看戰場/r看戰報/o下命令/q。對手只需 client.py + mapcore.py + rich + wcwidth。
- **資料流檔**：`order_allies.json`/`order_axis.json`（命令）、`report_allies.md`/`report_axis.md`（過濾戰報）。
- **回合**：雙方同步下令(互不可見)→你喊 Claude 結算→Claude 解算改 state + 寫兩份過濾戰報→雙方各自拉看。fog 偵獲清單(allies_spotted/axis_spotted)每次解算後要更新。
- **已驗證**：迷霧三視角過濾正確、server 全端點(含 token 403)、client↔server 端到端 HTTP(ping/view/order)、渲染不破版。

### AI 參謀（2026-06-03 新增，雙方對等）
- **三角色嚴格分離**：裁判 GM（中立、god 視角、只解算不出主意）/ 盟軍參謀 / 德軍參謀，prompt 在 `prompts/{referee_gm,advisor_allies,advisor_axis}.md`。
- **`advisor.py`** — server 端呼叫 Claude API。`claude-opus-4-8` + adaptive thinking + effort high + **prompt caching**（system=角色+6規則檔54k字整段快取；user turn 放每回合變動戰況+問題）。只吃 `filter_state_for(state,side)` → 迷霧在 AI 層守住。缺 SDK/key 時 `advisor.available()=False`，server 回 503 不崩。
- **server endpoint**：`POST /advise?side=`（即時問參謀）、`GET /advisor_status`。**client**：選單加 `a` 問參謀。
- **前置**：GM 端 `pip install anthropic` + `export ANTHROPIC_API_KEY=...`。對手不用自己有 Claude（API key 在 GM 端、費用算 GM）。**這是即時 API，不是半即時 subagent**。
- **已驗證**：缺 SDK 優雅降級、HTTP 端到端(503/400)、monkeypatch 確認 API 參數結構(model/thinking/cache_control)正確、迷霧隔離(德軍視角無盟軍 resources)。
- **限制**：Claude(你的 session)仍是唯一裁判。參謀費用算 GM 端 API key。

### hour 級對稱即時命令（2026-06-03，Version B+）
完整設計見 `design_realtime_mp.md`。把單機 Version A 的 hour 級即時命令搬進 1v1，**雙方對等**。
- **拍板**：逐 hour 都停(預留快進開關)｜主令+臨時令並存｜10 分鐘離線自動推進(中立計時器，無人能手動跳過對方)。
- **`hourstate.py`** — 核心：時間換算(global_hour/game_time/daynight)、schema 升級(hour_in_tick/global_hour/phase/pending_orders/standing_orders)、**延遲佇列**(L1=1hr/L2=2hr/L3=3hr，enqueue→due→activate)、hour 推進。`test_hourstate.py` 30 測試全過。
- **server**：`POST /hour_action?side=`(臨時令/繼續)、`GET /pending?side=`(自己佇列+倒數)、activity 追蹤(離線保護)。
- **client**：`h` 本小時動作、`p` 命令佇列、`o` tick 主令。
- **`hourwatch.py`** — hour 監聽：雙方提交到齊 or 離線>10min → 印 RESOLVE 叫醒裁判。`--once` 給 Monitor。
- **filter_state_for** 加過濾 pending/standing(敵方延遲令是機密)。**map.py** header 顯示 小時 x/6 + 延遲令數。
- **公平性已測**：閒置 5 分鐘還在想的人不會被跳過；只有真離線(零互動>10min)才中立自動推進；舊 hour 提交不誤判。
- **裁判每 hour 結算 8 步**：讀雙方 action→enqueue→activate_due→移動/戰鬥/偵察→advance_hour→寫戰報→刪 hour_action→重掛監聽。
- **tick 級粗回合仍保留**(order endpoint)，hour 級是進階玩法。

### 師的營級編制系統 ORBAT（2026-06-05，取代分遣隊舊設計）
- **演進**：先做 detachments.py(各兵種固定比例拆)，但 user 要的是「師編制完整攤開 + 最高自由度」——任一營都能單獨拉(想單拉砲營送死也行)，裁判只管真實+可行不管戰術。→ 改成營級 ORBAT，detachments.py 封存為 .bak。
- **粒度**：營(一個師 8-18 營)。設計文件 `design_division_orbat.md`。
- **`orbat.py`**：7 師完整營級編制(~110 營，含師部勤務 hq 不可拉)。人數加總對上 forces_v1 真實員額(1ID 14030、17SS 13200、352 7200…)。
  - `detach(s,div,code,pos)` 拉單營成獨立棋子(扣母師 personnel + strength，記 _str_cut)、`rejoin(s,det_uid)` 歸建(精確還原，守恆)、`ensure_orbat(s)` 補 schema、`print_orbat(side)` CLI 查詢。
  - uid = `<師>-<營碼>`(如 1ID-a1)。欄位 is_detachment/parent/bn_code。NON_DETACHABLE={hq}。
- **雙軌數值**：personnel(人數，拆/歸建守恆) + strength(0-100 戰力，戰鬥公式用，拉營按人數佔比×0.5 衰減扣除)。營自身 strength 承襲母師水準。
- **查編制**：`python3 orbat.py --side allies`(或 axis/全部) 印每師完整營表(營碼/名/兵種/人數/狀態/武器)。`--check` 跑自測。
- **state**：每師加 personnel + orbat{營碼:{name,type,personnel,note,status}}。status=in_division/detached。
- **map.py**：部隊面板師下方「└在師」摘要(步9 砲4 工1 偵1 裝1)；拉出的營縮排顯示。`render_orbat()` 完整樹(備用)。TYPE_TAG 短碼。
- **迷霧**：敵方師 orbat/personnel 自動不洩(filter_state_for 的 _ENEMY_PUBLIC 不含這些)；己方完整。
- **已驗證**：7 師員額對上真實、拉營扣兵/歸建守恆、hq 擋拉、敵方編制不洩己方完整、9 檔編譯、CLI 查詢正常。
- **待做(第二階段)**：編組(自組 RCT/CCA 把多營綁成戰鬥群)、戰鬥公式處理合成群多兵種貢獻。

### 史實校正（2026-06-05，opus subagent 史學審查後修）
審查結論：穿甲表/各師 TOE/德軍補給劣勢/疲勞系統 都扎實(別動)；但有幾項與 1944-08 史實矛盾。已修「好修+中工」四項中的前三項：
- **油料消耗**(logistics_v1)：裝甲師 L1 從 3%/hr→**6%/hr**(~16hr 耗盡)。原版可機動 33hr，與本戰役時空(1944-08 盟軍油荒、巴頓卡塞納河)矛盾。**裝甲突進須顧油**。
- **天氣表**(weather_v1 + state.json campaign_actual)：T4-8 連續中雨泥濘 → **全程晴好**(僅 T5 午後局部雷陣雨)。史實 1944-08 底法國晴好(Falaise 後大追擊期靠好天氣)。**戰略後果：德軍失去「拖到雨季」庇護，盟軍空優全程有效**。
- **戰車命中係數**(combat_v1 + determinism_v1 同步)：0.25-0.65 → **0.06-0.18**(下修~3-4倍) + 加距離修正。原版每發逾半命中→5分鐘殲滅；史實 WWII 戰車戰整場平均命中率 5-15%(ORS)。改成「一個 hour 持久交火」非瞬殺。
- **CAS 對戰車**(combat_v1)：「開闊必殺」→ **壓制為主、擊殺<5%**。ORS Mortain/Falaise：火箭對戰車命中率 0.5-5%，多數「擊毀」是乘員棄置。CAS 真正價值是釘住/遲滯德軍裝甲，殺戰車仍靠地面反裝甲。
- **師級傷亡率**(combat_v1)：strength 損失減半(原 -4%/hr 連打6hr=-24% 半天打殘師)。org 損失保留(疲勞/壓制可恢復)。
- **Bocage 樹籬地形**(2026-06-05 加，第四項完成)：地形碼 `K`、符號 `⌗⌗ `(EAW=N 不破版)、深綠底。移動：戰車 ×0.2(土堤困死，須 Cullin hedgerow cutter)、步兵 ×0.4。戰鬥：守方 ×2.0/攻方 ×0.5(逐籬爭奪)。視距：0.5 hex(撞上才發現、伏擊頻繁)。放 25 格在西岸鄉間(美軍出發區，避開單位/目標)。改 mapcore.A_TERRAIN + movement_v1 移動表 + combat_v1 地形守方表 + recon_v1 地形視距上限。三視角渲染 107 寬不破。**戰略後果：盟軍裝甲優勢在 bocage 被削弱，渡河前推進變慢血腥，符合諾曼第實況。**
- **仍未做**：壓制(suppression)可恢復獨立狀態；補給線長度懲罰。審查全文可重召 subagent a253630f62863074c。

## 7. Adler agent

- 使用 Claude opus subagent
- Run 1 用了同一個 agentId 全程接續（a288ef09f3a1e5920）—— 他保持記憶、可演進。
- Run 2 開了新 agent（aaba4e61e495ed166）—— fresh start。
- ~~Run 3 前要寫 Adler prompt 模板~~ → **✅ 2026-05-29 已寫**：`adler_brief_template.md`。含 §A 角色 + §B 規則摘要（含 TOE 紅線：無 Tiger、反戰車 ≈38 砲位上限）+ §C 戰場初始 / §C′ 續場更新 + §D 輸出格式（意圖/主計畫/應變/TOE 自檢）+ GM 檢核清單 + 變數對照表。Tick 0 給完整版（~5k token），續場給精簡版並沿用同一 agentId。

## 8. 還沒做的（按優先序）

1. ~~state.json 更新~~ ✅ 完成（2026-05-29）
2. ~~map.py 改版~~ ✅ 完成（2026-05-29）
3. ~~Adler prompt 模板~~ ✅ 完成（2026-05-29，`adler_brief_template.md`）
4. **Run 3 實戰測試** — ★下一步：三項前置已就緒，可開戰驗證整套規則
5. **次要漏洞**（指揮官人格、veterancy 細節、POW 鏈、醫療後送、戰役節奏）
6. **第二劇本**（庫斯克、阿登）測試規則跨戰役通用性
7. ~~多人版（Version B）~~ ✅ 2026-06-02 完成基礎建設（迷霧/server/client/手冊），見 §6b + `multiplayer.md`。待實戰測一場。

## 9. 已知問題

- ~~state.json 凍結在 Run 2~~ ✅ 已重置為 Run 3 Tick 0
- ~~combat_log.jsonl 需 archive~~ ✅ 舊檔移為 `combat_log_run2.jsonl.archive`、新檔含 Run 3 開場行
- ~~map.py 不顯示新 7 欄資源~~ ✅ 已改版
- ~~Adler prompt 沒模板~~ ✅ `adler_brief_template.md`
- （無已知阻擋項；三項 Run 3 前置全部完成）

## 10. 設計靈感來源/未來參考

- Combat Mission 系列（WEGO 同步回合）
- HOI4（戰役級組織度/補給）
- 1944 真實 TOE 文件（US Army FM 100-10、TOE 7-12、德軍 HDv 130）
- 各兵器穿甲歷史資料（lone-sentry.com、tankarchives.ca）
- Cornelius Ryan《The Longest Day》narrative 風格寫戰史 → `battle_record.md`

## 11. 開新 session 時的接手指引

要繼續這個專案：
1. 先讀本 memo 對齊現狀
2. 讀 `scenario.md` 知道戰役設定+TOE 嚴格規則
3. 讀 `rules_v2.md` 知道時間+命令系統
4. 其餘規則檔依需要查
5. 若要實戰：先做「8 還沒做的」第 1-3 項（state.json、map.py、Adler prompt）
