# 裁判備忘 — PvP「純戰場 The Open Field」

> 開這局時裁判（GM）照此跑。規則全文在 `scenario_open_field.md`；本檔是**操作流程**。
> 雙方都是真人（藍軍/紅軍），GM **中立、只解算、不出主意**。

## 0. 開局
- 載入 `maps/open_field_state.json`（藍=allies、紅=axis）。
- 觀戰：`python3 map.py --state maps/open_field_state.json --supply`（god 看雙方；`--side allies/axis` 給各玩家看自己）。
- 提醒雙方：開局**無指揮所**（吃 +2 延遲），第一優先是下令建立指揮部。

## 1. 每 tick / 每 hour 結算流程
用 hour 迴圈（`hourstate.hour_brief` / `end_hour`），每個 hour：
1. `command.activate_due_cps(state)` — 架設滿 2hr 的指揮所啟用（軍長進駐）。
2. `hourstate.hour_brief(state)` — 到期延遲令生效、看本 hour 議程。
3. 裁定移動 / 接觸 / 戰鬥 / 偵察（沿用 combat/movement/recon…）。
4. **補給**：`mapcore.compute_supply(state)` 算各編隊走廊狀態；**切斷(0%)**→該編隊停補、吃老本、觸危機閾值後戰力衰退；**受威脅(50%)**→補充減半。
5. `command.decapitation(state)` — 若某方軍長所在指揮所格被敵佔 → **該方即敗、遊戲結束**。
6. `end_hour(state, "本 hour 摘要")` — 記 log、時鐘 +1。

## 2. 處理玩家命令
- **一般命令**：玩家對編隊 U 下 L1/L2/L3 令 → 延遲用 `command.command_delay(state, side, level, U.pos)`（= 基準 + CP 調整），再 `hourstate.enqueue_order(s, side, level, text, extra_delay=command.delay_tier_adjust(...))`。
  - 延遲階梯：未建 CP **+2** / 主指揮所 **+1** / 前進指揮所罩 6 格內 **基準**。
- **建指揮所**：玩家下「在 (x,y) 建立 主/前進 指揮所」→ `command.establish_cp(state, side, 'main'/'fwd', (x,y))`，2hr 後 `activate_due_cps` 自動啟用、軍長進駐。
- **移動軍長/換位**：等同重建（拆 2hr），期間退回 +2。
- **拆營（特戰旅等）**：`orbat.detach` / `rejoin`（最高自由度，沿用）。

## 3. 勝負
- **斬首即勝**：`command.decapitation` 回傳敗方 → 立即結束。特戰旅偵察找出敵指揮所→突襲摧毀是招牌殺招。
- **殲敵計分**：撐到 **Tick 8** 結束，擊毀敵戰力（人員+裝備價值）較多者勝。
- **平手**：殲敵相當 → 自損較少者勝。

## 4. 迷霧與中立
- 玩家視角一律 `mapcore.filter_state_for(state, side)`：敵未偵獲單位、資源、命令、指揮所**都不給**。
- 特戰旅開局隱蔽（低被偵獲率）；指揮所位置須靠偵察找出。
- GM 中立：不替任一方分析怎麼打；PvP 雙方各自思考（要參謀就各開各的 advisor，只吃自己視角）。

## 5. 天氣
全程晴好開闊（`weather_state.current` 已設 CAS×1/移動×1）。純戰術、不靠天候變數。
