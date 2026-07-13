# 對局架構協定（Run 4 起）— 四角色分離 + 並行派發

> 這份文件定調「誰是誰、誰跟誰講話、用什麼模型、迷霧怎麼守」。
> 2026-06 由玩家定案。違反此協定 = 破壞遊戲完整性。

## 1. 四個角色（嚴格分離）

| 角色 | 誰扮 | 視角 | 模型 | 職責 |
|------|------|------|------|------|
| **Referee 裁判** | 主 Claude session（我） | 上帝視角（god-view，看 state.json 全部） | session 模型 | 解算戰鬥、維護迷霧、寫雙方過濾戰報、驅動 Adler、跑 hour 迴圈。**絕對中立、絕不出主意。** |
| **Advisor 參謀** | in-session subagent（persistent） | **只吃** `filter_state_for(state,"allies")` + `report_allies.md` | **Haiku** | 盟軍玩家的 AI 軍師＝玩家的**唯一介面**。解讀戰報、推敲命令、列選項講利弊、把玩家決定整理成 order 轉達裁判。 |
| **Adler 德軍** | in-session subagent（persistent，整場同一個） | 只吃德軍過濾視角 + `report_axis.md` | **Haiku** | 德軍指揮官，有記憶會演進。產出 6hr 主計畫 + ≤8 應變。受 TOE 嚴格主義約束。 |
| **Player 玩家** | 真人 | 同 Advisor（過濾後盟軍視角） | — | 美軍 III Corps 指揮官，最終決策權在他。 |

## 2. 通訊拓撲（玩家定案）

```
玩家 ⇄ Advisor(Haiku) ⇄ Referee(我·god-view) ⇄ Adler(Haiku)
```

- **玩家整場不直接和裁判對話。** 玩家的對話對象永遠是 Advisor。
- **單一終端機現實**：真人只能 type 給主 session（裁判）。所以實作上＝裁判收到玩家輸入後，**一律轉給 Advisor subagent 處理，並把 Advisor 的回覆逐字轉述給玩家**（裁判的人類可見輸出＝Advisor 的口吻，不是裁判自己的口吻）。裁判在幕後 god-view 解算，絕不把全局知識漏進轉述。
- **命令也走 Advisor**：玩家講意圖 → Advisor 推敲＋確認 → Advisor 把定案 order 轉給裁判 → 裁判解算。
- 為何不反過來（Advisor 當主 session、裁判當 subagent）：裁判要驅動 Adler（另一個 subagent），而 **subagent 不能乾淨地再生成/驅動自己的 subagent**（巢狀受限）。故統籌者（orchestrator）必須是主 session＝裁判。

## 3. 並行派發迴圈（解 latency #1）

每個 tick 結算後：

```
1. Referee 解算上一 tick → 更新 state.json + 寫 report_allies / report_axis
2. ★同時★ 派發：
     report_allies → Advisor subagent（開始想）
     report_axis   → Adler   subagent（開始想）
   兩個 Haiku agent 並行推理，不互等。
3. Advisor 產出「戰報解讀 + 戰術選項」→ 裁判轉述給玩家。
   玩家在讀/想的同時，Adler 已在背景算他的命令。
4. 玩家（透過 Advisor）定案 order → 轉給裁判。
   Adler 算完 → 待機（idle），等下一份 report_axis。
5. 兩邊 order 到齊 → 裁判跑 hour 迴圈解算（hourstate.hour_brief/end_hour）→ 回到 1。
```

關鍵：Adler 與 Advisor 的思考都疊在「玩家思考時間」內並行，60–70s 的等待基本消失。

## 4. 迷霧在 AI 層的防線（不可破）

- Advisor **只**收 `filter_state_for(state,"allies")` + `report_allies.md`。裁判餵資料時逐次過濾，**絕不**把德軍未偵獲位置/資源/命令/底牌、或 Adler 的計畫漏給 Advisor。
- Adler 同理只收德軍過濾視角。
- 裁判（god-view）是唯一全知者，正因如此必須嚴守中立與過濾。

## 5. 模型成本備註

- Advisor、Adler 皆 Haiku（玩家選擇，省 token）。
- ★已知取捨★：Haiku 的 Adler 會比 Opus 版明顯變弱（計畫變淺、誘敵與忍耐的層次減少）。玩家已知並接受此代價以換成本。日後若想要更聰明對手，把 Adler 升 Sonnet/Opus 即可（單點改 spawn 模型）。

## 6. 與既有檔案的關係

- 角色 prompt：`prompts/referee_gm.md`、`prompts/advisor_allies.md`、`adler_brief_template.md`（皆已存在、已分離）。
- 過濾：`mapcore.filter_state_for`。
- hour 迴圈：`hourstate.hour_brief / end_hour / advance_hour`（2026-06 已接上）。
- 網路版 `advisor.py` 的 MODEL 同步改 haiku（單機 in-session 版用 Agent 工具的 model 參數設 haiku）。
