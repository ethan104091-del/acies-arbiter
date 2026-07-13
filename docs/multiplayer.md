# 多人 1v1 對戰 — 操作手冊

> Version B 對稱多人版（規則框架見 `rules_v2.md` §2）。
> 架構：**你的 Mac = GM + 權威 state + server**；**對手 = 遠端 client**；**Claude = 裁判**。

---

## 0. 角色與檔案

| 角色 | 在哪 | 用什麼 | 看到什麼 |
|------|------|--------|---------|
| 你（GM 兼一方玩家） | 你的 Mac | `map.py`（god 視角）+ Claude 解算 | 全部（上帝視角） |
| 對手（另一方） | 遠端電腦 | `client.py` | 只有自己 + 已偵獲敵軍 |
| Claude | 你的 Mac session | 讀規則、解算、改 state、寫戰報 | 全部 |

**權威資料**：`state.json` 只在你的 Mac，唯一真相。server 即時讀它。

**資料流檔案**：
- `order_allies.json` / `order_axis.json` — 各方本回合命令（client POST 進來，或你本地寫）
- `report_allies.md` / `report_axis.md` — 各方收到的過濾戰報（Claude 寫，client 拉）

**AI 參謀（雙方對等）**：每方都有自己的 AI 軍師，**即時** Claude API 回答（非半即時）。
- `prompts/advisor_allies.md` / `advisor_axis.md` — 各方參謀的 system prompt（只能看自己視角）
- `prompts/referee_gm.md` — 裁判 prompt（中立，只解算不出主意；你 GM session 用）
- `advisor.py` — server 端呼叫 Claude API 的模組（claude-opus-4-8 + adaptive thinking + prompt caching）
- 參謀只吃 `filter_state_for(state, side)` 過濾視角 + 該方戰報 → 迷霧在 AI 層也守住，看不到對方底牌
- 對手在 client 按 `a` 問參謀 → server `/advise` → 即時回答（需 GM 端裝 `anthropic` SDK + `ANTHROPIC_API_KEY`）

---

## 1. 連線建立（開局一次）

### 你的 Mac（GM 端）
```bash
# AI 參謀前置（一次性）：裝 SDK + 設 API key（沒設則參謀停用，其餘照常運作）
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# 終端機 A：啟動 server（會印出 token，也會顯示 AI 參謀狀態）
python3 ~/war-game/server.py --port 8000

# 終端機 B：開對外通道（遠端對手才需要）
cloudflared tunnel --url http://localhost:8000
# → 記下它給的 https://xxxx.trycloudflare.com

# 終端機 C：你自己看戰場（god 視角）
python3 ~/war-game/map.py
```
把 **tunnel 網址 + token** 傳給對手（用任何聊天軟體）。

> 同網路測試免 tunnel：對手直接連 `http://<你的內網IP>:8000`。
> 查內網 IP：`ipconfig getifaddr en0`

### 對手（遠端端）
對手需要：Python 3 + `pip install rich wcwidth` + `client.py` + `mapcore.py`（兩個檔給他）。
```bash
python3 client.py --url https://xxxx.trycloudflare.com --token <token> --side axis
```
連上後選單：`v` 看戰場、`r` 看戰報、`a` 問參謀、`o` 下命令、`q` 離開。
（`a` 問參謀：對手打字問題 → server 端用德軍視角即時調 Claude → 回答。對手不需自己有 Claude；
  API key 在你 GM 端，費用算你的。參謀只看得到對手該看的，不洩漏你的底牌。）

---

## 1b. hour 級即時命令（2026-06-03，Version B+，預設玩法）

> 完整設計見 `design_realtime_mp.md`。tick 級粗回合仍可用（§2），但對戰建議用 hour 級。

**核心**：tick 開頭雙方下「6 小時主令」，之後**每個 hour** 雙方可下臨時令(L1/L2/L3 延遲生效)或「繼續」。
- **命令延遲**：L1=1hr、L2=2hr、L3=3hr 後才生效（進 `pending_orders` 佇列，雙方對等）
- **每 hour 同步**：雙方各提交「本小時動作」→ `hourwatch.py` 偵測到齊 → 自動叫醒裁判結算這 1 小時
- **離線保護**：某方零互動 >10 分鐘 → 中立計時器視為「繼續」（**無人能手動跳過對方**，公平）

**GM 端多開一個終端機跑監聽**：
```bash
# 終端機 D：hour 級監聽（雙方提交到齊就喊 RESOLVE，叫醒裁判）
python3 ~/war-game/hourwatch.py
```
**client 多了三個指令**：`h` 本小時動作（臨時令/繼續）、`p` 看自己命令佇列+生效倒數、`o` tick 開頭下主令。

每 hour 流程：
```
雙方各按 h 提交本小時動作（臨時令 or 繼續，互不可見）
  → hourwatch 偵測雙方到齊（或某方離線10分）→ 印 RESOLVE → 叫醒裁判
  → 裁判結算這 1 hour：到期命令生效→移動/戰鬥/偵察→推進時鐘→寫雙方戰報→刪 hour_action
  → 雙方按 r/v 看新戰況 → 下一個 hour
```

---

## 2. 一個 Tick 的回合流程（tick 級粗回合，仍可用）

```
┌─ Tick 開頭 ──────────────────────────────────────────┐
│ 1. 雙方同步下「6 小時主令 + 應變條件」，互不可見       │
│    - 對手：client 按 o，填 intent/主計畫/應變 → 送出   │
│      → server 存成 order_axis.json                     │
│    - 你：直接跟 Claude 講你的命令（或本地寫 order_allies.json）│
│ 2. 兩份命令都到齊後，告訴 Claude「雙方命令已交，結算」  │
└──────────────────────────────────────────────────────┘
        ↓
┌─ Claude（GM）解算 ───────────────────────────────────┐
│ 3. 讀 order_allies.json + order_axis.json + 規則檔     │
│ 4. 逐 hour 推進：移動→應變觸發→接敵→戰鬥(CP公式)→偵察 │
│ 5. 更新 state.json（位置/兵力/組織/補給/fog 偵獲）     │
│ 6. 寫兩份「過濾後」戰報：                              │
│    - report_allies.md（盟軍只知道自己偵察到的）       │
│    - report_axis.md（德軍只知道自己偵察到的）         │
└──────────────────────────────────────────────────────┘
        ↓
┌─ 回報 ───────────────────────────────────────────────┐
│ 7. 你的 map.py 自動重繪（god 視角看全局）             │
│ 8. 對手 client 按 r 拉 report_axis、按 v 看更新後戰場  │
│ 9. 進下一個 Tick，回到 1                              │
└──────────────────────────────────────────────────────┘
```

**同步規則（rules_v2.md §2）**：
- Hour 結算前雙方需提交（含「無動作」確認）。超時 = 繼續既有令。
- 報告同時送雙方，內容依各自陣營資訊過濾。

---

## 3. 戰爭迷霧（已在程式層強制）

過濾在 **server 端**做，對手即使抓封包也看不到不該看的：
- **己方單位**：完整資料（資源/組織/命令）。
- **敵方已偵獲**：只露 位置 / 類型 / 概略兵力（取整到 10）。不露資源/精確組織/命令。
- **敵方未偵獲**：完全不出現在 client 的 state 裡。
- 盟軍 client 看不到 `axis_commander`（Adler 內部）。

可見性由 `state.json` 的 `fog_of_war.allies_spotted` / `axis_spotted` 決定 →
**Claude 每次解算偵察後要更新這兩個清單**，迷霧才會正確變動。

---

## 4. order / report schema

### order_<side>.json（client 送出格式）
```json
{
  "side": "axis",
  "intent": "後手反擊，誘敵過河再用 2Pz 側擊",
  "plan": ["17SS：守 Saint-Vivien 城本體", "2Pz：(22,5) 待命為反擊預備隊"],
  "contingencies": ["若美軍裝甲越中橋→引爆中橋預埋", "若 352 組織<30→後撤焦土"]
}
```
（你方 order_allies.json 同格式；可由 client 或本地手寫。）

### report_<side>.md（Claude 寫，純文字/markdown）
自由格式戰報，但**只能寫該方偵察得到的資訊**。範例見 rules_v2.md §3 Hour 報告格式。

---

## 5. GM（Claude）解算檢查清單

每個 tick 收到雙方 order 後：
- [ ] 兩份 order 都到齊？（缺一方 = 視為繼續既有令）
- [ ] TOE 嚴格主義：命令所用單位/武器/彈藥都在 forces/equipment 內？（雙方對等）
- [ ] 逐 hour 解算，套天氣（weather_state）、地形、補給修正
- [ ] 應變條件觸發判定（觸發即生效、用過即廢）
- [ ] 更新 state.json：pos / strength / org / resources / fatigue / **fog 偵獲清單**
- [ ] 寫 report_allies.md + report_axis.md（各自過濾、互不洩密）
- [ ] 勝負判定（scenario.md §4）

---

## 6. 安全與疑難

- **token**：server 啟動自動產生（或 `--token` 自訂）。所有端點都驗。`--no-token` 僅限同網路測試。
- **連不上**：檢查 server 有開 / tunnel 網址對 / token 對 / 對手裝了 rich+wcwidth。
- **過濾正確性**：`filter_state_for()` 在 mapcore.py，server 用它產生視角 state。改迷霧邏輯只動這一處。
- **不需要對手裝的**：state.json、server.py、規則檔。對手只要 client.py + mapcore.py。

---

## 7. 已知限制（未來可加）

- 目前同步靠人工協調（雙方下完令你喊 Claude 結算）。未做自動「雙方都提交才解算」的 server 鎖。
- client 下令是純文字三段式，未做 TOE 即時檢查（由 Claude 解算時把關）。
- 未做斷線重連／回合計時器。
- 兩個人類對戰時，Claude 仍是唯一裁判（非自動引擎）——這是設計，不是缺陷。
