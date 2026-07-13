# 設計文件：聯機版 hour 級對稱即時命令（Version B+）

> 狀態：**✅ 已實作（2026-06-03）**。核心機制全部完成並通過測試。
> 拍板決定：逐 hour 都停（預留快進開關）｜主令+臨時令並存｜10 分鐘離線自動推進（中立計時器，無人能手動跳過）。
> 目標：把單機版 Version A 的「hour 級即時命令 + L1/L2/L3 延遲」搬進聯機 1v1，
> 且**雙方對等**（兩個真人都能 hour 級即時下令）。

---

## 0. 為什麼要做 / 現狀問題

**現狀（tick 級粗回合）**：雙方各下一次「6 小時主令」→ 裁判一次算完整 6 hour → 報告。
- 問題：粒度太粗。你下令後 6 小時內無法介入，看不到中途、改不了。不夠「即時」。

**要做的（hour 級）**：每小時雙方可下臨時令、看報告、再下令。命令依複雜度延遲生效。
這是 `rules_v2.md` 既有的設計，只是原本只給單機 Version A，現在要對稱化給 1v1。

---

## 1. 核心規則（沿用 rules_v2.md §0，雙方對等套用）

### 時間
- Tick = 6 hour；一場 8 tick = **48 個 hour**。
- Tick 0 = 06:00 開戰，Tick N 起始 = 06:00 + N×6。

### 命令延遲分級（關鍵新機制）
| 等級 | 延遲 | 例 |
|------|------|---|
| L1 反應式 | 1 hour | 停火、砲擊改打 A、啟動干擾 |
| L2 戰術改變 | 2 hour | 3AD 改往南、1ID 改防禦、CAS 重分派 |
| L3 大重組 | 3 hour | 整師反向撤退、跨軸調師、全軍轉守為攻 |

下令當下不生效，進**延遲佇列**，N hour 後才執行。裁判標註複雜度，玩家可協商。
**雙方對等**：兩個玩家下臨時令都吃同樣的 L1/L2/L3 延遲。

### 每 hour 結算順序（rules_v2 §1，對稱化）
```
1. 雙方既有移動推進 1 hour（套天氣/地形/補給修正）
2. 檢查延遲佇列：哪些命令本 hour 到期 → 生效
3. 結算接敵 / 戰鬥 / 偵察（更新 fog）
4. 生成雙方各自過濾的 Hour 報告
5. 雙方各下新臨時令（或「繼續」）→ 進佇列
6. 進下一個 hour
```

---

## 2. 每 hour 的同步流程（最大的新機制）

### 一個 hour 的生命週期
```
┌─ Hour H 開始 ────────────────────────────────────┐
│ 裁判已算完 H-1，雙方已收到 Hour 報告              │
│                                                   │
│ 雙方各自決定本 hour 動作（互不可見）：            │
│   - 下一條臨時令（標 L1/L2/L3）→ 進延遲佇列       │
│   - 或「繼續」（無新令，沿用既有主令）            │
│   - 含「無動作確認」（rules_v2 §2：必須提交）     │
│   ↓                                               │
│ 兩邊都提交 → 監聽偵測到齊 → 自動叫醒裁判          │
│   （超時規則：某方久未提交 = 視為「繼續」）       │
│   ↓                                               │
│ 裁判結算這 1 hour（上面的結算順序）              │
│   - 推進移動、檢查到期命令、戰鬥、偵察           │
│   - 更新 state.json（含 current_hour, pending）  │
│   - 寫雙方過濾 Hour 報告                          │
│   ↓                                               │
│ 雙方各自看新報告 → 進 Hour H+1                    │
└───────────────────────────────────────────────────┘
```

### 跟現有監聽怎麼接
- 現在監聽盯 `order_<side>.json`（tick 級，一場一次）。
- 改成盯 `hour_action_<side>.json`（hour 級，每 hour 一次）。
- 雙方該檔都更新到「當前 hour」→ 監聽叫醒裁判 → 結算 → 清空等下個 hour。
- 裁判結算完自動重掛監聽。

---

## 3. state.json schema 改動

新增欄位（不動現有的 units/objectives/weather/fog）：
```json
{
  "tick": 2,
  "hour_in_tick": 3,          // 0-5，本 tick 內第幾個 hour
  "global_hour": 15,          // 開戰至今第幾個 hour（0-47），= tick*6 + hour_in_tick
  "game_time": "1944-08-25 21:00",
  "phase": "awaiting_hour_actions",  // 或 "resolving" / "tick_planning"

  "pending_orders": [          // 延遲命令佇列
    {
      "id": "o12",
      "side": "axis",
      "issued_global_hour": 13,
      "effective_global_hour": 15,   // = issued + L(1/2/3)
      "level": "L2",
      "text": "2Pz 改往中橋方向機動",
      "status": "pending"            // pending → active（生效後）
    }
  ],

  "standing_orders": {         // 各方當前「主令」（沿用直到被臨時令覆蓋）
    "allies": "3AD 北線突擊、4ID 森林待命",
    "axis": "17SS 守城、2Pz 預備"
  }
}
```

### hour_action_<side>.json（每 hour 提交格式）
```json
{
  "side": "axis",
  "for_global_hour": 15,       // 這是對第幾個 hour 的動作（防錯位）
  "action": "order",           // "order" 下臨時令 / "continue" 繼續
  "order": {                   // action=order 時才有
    "level": "L2",
    "text": "2Pz 改往中橋方向機動"
  }
}
```

---

## 4. client / server / 監聽改動清單

| 元件 | 改動 |
|------|------|
| `state.json` | 加 hour_in_tick / global_hour / phase / pending_orders / standing_orders |
| `server.py` | `/state` 回傳含 hour 資訊；新增 `POST /hour_action?side=`（取代或並存 /order）；`/pending`（看自己的延遲佇列） |
| `client.py` | tick 開頭：下主令；每 hour：選「下臨時令(選 L1/L2/L3) / 繼續」；顯示自己的 pending 佇列與生效倒數 |
| 監聽 | 盯 `hour_action_<side>.json` 雙方到齊 → 叫醒裁判結算單一 hour |
| `map.py` | header 顯示 global_hour / hour_in_tick；可選顯示 pending 命令數 |
| `mapcore.filter_state_for` | 過濾時：pending_orders 只給自己那方（敵方的延遲命令是機密）；standing_orders 同理 |
| 迷霧 / 參謀 / 裁判 prompt | 不變，照用（參謀會自動看到新的 hour 資訊與自己的 pending） |

---

## 5. ★ 最大的權衡：48 個 hour 的互動成本

**逐 hour 都停（你目前選的）**：
- 一場 = 48 個同步點，每個雙方各操作一次 = **最多 96 次人類操作**。
- 每次操作含思考、看報告、下令，估 1-3 分鐘 → 一場可能 2-5 小時。
- 優點：最即時、最細、最接近真實指揮節奏。每個小時都能介入。
- 缺點：很長。多數 hour 其實「沒事發生」（部隊還在行軍），卻仍要雙方各點一次「繼續」。

**備選 A：混合式（WEGO，我原本推薦的）**
- 雙方按「繼續」後，裁判**連續快進多個 hour**，直到中斷條件：
  接敵 / 應變觸發 / 抵達目標 / 任一方下新臨時令 / tick 邊界。
- 把「沒事的 hour」自動跑掉，只在「有事 or 想介入」時停。
- 一場互動次數從 ~96 降到可能 ~15-25 次，但**保留 hour 級即時介入**（隨時可下令打斷快進）。
- 這是 Combat Mission 系列的做法，公認在「即時感」與「不冗長」間最佳平衡。

**備選 B：只在關鍵 hour 停**
- 預設自動跑到 tick 結束，只有接敵/重大事件強制停。互動最少但可能錯過想介入的時機。

> **建議**：先用「逐 hour 都停」實際打**半個 tick（3 hour）試水溫**，體感「沒事的 hour 也要互動」有多冗。
> 若覺得冗，切換成備選 A 只是改「快進中斷條件」一個參數，core 機制（延遲佇列、同步）完全共用、不浪費。
> 所以**先做逐 hour 都停，但 code 架構預留快進開關**，是最穩的路。

---

## 6. 跟單機版的關係

- 單機版 Version A（你 vs Adler AI）：你 hour 級即時、Adler 只 tick 開頭。**保留不動**。
- 本設計 = Version B 的 hour 級對稱版，可叫 **Version B+**。
- 兩者共用同一套「延遲佇列 + hour 結算順序」，只差「誰能在哪個粒度下令」。
- 延遲佇列機制做好後，單機版 Version A 也能直接受益（你下臨時令也走同一個佇列）。

---

## 7. 實作順序（待確認後執行）

1. state.json schema 升級（hour 欄位 + pending_orders + standing_orders）
2. 延遲佇列邏輯（裁判結算時檢查到期命令）— 這是核心，先做
3. server `/hour_action` + `/pending` endpoint
4. client hour 級下令介面（主令 / 臨時令選 L1-L3 / 繼續 + 顯示 pending）
5. 監聽改盯 hour_action 雙方到齊
6. filter_state_for 過濾 pending/standing（不洩漏敵方延遲命令）
7. map.py 顯示 hour/pending
8. （預留）快進開關 + 中斷條件，方便日後切混合式
9. 半 tick 試打驗證

---

## 8. 拍板決定（已定案）

- [x] **逐 hour 都停**（已預留快進開關：hourwatch 的中斷條件可改；目前每 hour 停）
- [x] **並存**：tick 開頭下主令（client `o`）+ 每 hour 下臨時令（client `h`）
- [x] **離線保護 10 分鐘**：中立計時器，零互動 >600s 才視為「繼續」。**無人能手動跳過對方**（公平性：閒置 5 分鐘還在想的人不會被跳過，已測）。

## 9. 實作成果（檔案）

- **`hourstate.py`** — 核心：時間換算、schema 升級、延遲佇列(enqueue/due/activate/pending_for)、hour 推進。`test_hourstate.py` 30 測試全過。
- **`mapcore.filter_state_for`** — 加過濾 pending_orders/standing_orders（敵方的不可見）。
- **`server.py`** — `POST /hour_action?side=`、`GET /pending?side=`、activity 追蹤（任何帶 side 請求刷新，離線保護用）。
- **`client.py`** — `h` 本小時動作(臨時令 L1/L2/L3 或繼續)、`p` 看自己命令佇列+倒數、`o` tick 開頭主令。
- **`hourwatch.py`** — hour 級監聽：雙方提交到齊 or 離線保護 → 印 `RESOLVE` 信號叫醒裁判。`--once` 給 Monitor until-loop。
- **`map.py`** — header 顯示 小時 x/6、global_hour、phase、延遲令數。

## 10. 裁判（Claude）每 hour 結算步驟

被 hourwatch 的 RESOLVE 叫醒後：
1. 讀 `hour_action_allies.json` + `hour_action_axis.json`（離線方視為 continue）
2. 各方 action=order → `hourstate.enqueue_order`(進佇列、依 L 延遲)
3. `hourstate.activate_due` → 本 hour 到期的命令生效
4. 推進移動/戰鬥/偵察(規則檔)，更新 units/fog
5. `hourstate.advance_hour` 推進時鐘
6. 寫雙方過濾 Hour 報告 report_*.md
7. 刪除 hour_action_*.json（等下個 hour）
8. 重掛 hourwatch 監聽
