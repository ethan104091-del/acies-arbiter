# Run 4 — 純戰場 The Open Field 首次實跑（2026-07-25）

**Codex (gpt-5.6-terra, reasoning high) 執紅軍　vs　Claude Opus 5 subagent 執藍軍**
裁判：Claude Opus 5（上帝視角、中立解算）｜48 小時／8 ticks
**終局：藍軍 8,813 : 紅軍 1,790（決定性勝利）**

## 怎麼重播

本局零擲骰、完全確定性，可從任一 tick 的快照精確重現：

```bash
cd ~/war-game
cp runs/run4_openfield/snap_T5start.json maps/open_field_state.json
python3 runs/run4_openfield/t5.py       # 重跑 Tick 5
```
從頭跑：`openfield_setup.py` → `t0.py` → `post_t0.py` → `t1.py` … → `t8.py`

**2026-07-30 修正兩件事**（原本這段指令是壞的）：

1. tick 腳本寫的是 `import of`（引擎併入專案前的舊模組名）。已補 `of.py` 相容層指向
   `arbiter`，所以重播用的是**當前**引擎 —— 這正是回歸測試要的：引擎改動若使本局分數
   變化，重播就會顯示出來。2026-07-30 加入編隊狀態機後重跑全 8 tick，逐 tick 分數
   與本目錄戰史完全相符，終局仍為 8,813 : 1,790。
2. `t2.py` 裡的 `push_log(s, ev)` 沒有指明事件目標 —— 那正是當時的**洩漏事故 #3**
   （預設雙方都收）。引擎現在會直接 `raise ValueError` 拒絕，所以單獨重播 T2 會中途中斷。
   這是刻意的：舊腳本保留原樣以存證，護欄不為了讓它跑得過而放寬。
   T2 的正確結果保存在 `snap_T3start.json`，其後各 tick 的重播鏈不受影響。

## 檔案

| 檔案 | 內容 |
|---|---|
| `battle_record_run4.md` | 931 行逐 tick 戰史（上帝視角），每場戰鬥附逐項計算 |
| `00_終局總結.md` | 覆盤：分數怎麼跑出來、決定勝負的三件事、裁判過失全紀錄 |
| `雙方命令_T0~T8.md` | 雙方每 tick 的意圖與命令原文（含誤判） |
| `snap_T*start.json` | 每個 tick 的起始狀態快照 |
| `final_state.json` | 終局狀態 |
| `t0.py ~ t8.py` | 逐 tick 解算腳本（各自載明該 tick 的延遲、命令、應變條件） |
| `tick.py` | 戰報產生與實時戰史追加 |
| `gen_handbook.py` | 從單一模板產出雙方手冊（保證對稱，可 diff 驗證） |
| `sanitize.py` | 洩漏事故的補救腳本（切除雙方日誌的洩漏段落） |
| `make_history.py` | 戰史 Markdown → 印刷級 HTML → PDF |

## 這局的核心發現

1. **工事不是加成，是勝負本身，而它只要 2.7 小時。** 暴露係數 0.7 → 0.10。
   藍軍下令開挖、紅軍全程只寫「固守」→ 同樣火砲數量打出 6.6 倍傷亡差。
2. **百分比損失表讓大單位吃虧**：13,730 人師攻 3,500 人精銳旅，攻方反而多死（206:122）。
3. **裁判的參數壓死了整個裝甲戰系統**：砲兵隔 4 格零風險殺戰車 → 裝甲永遠不該前進
   → 戰車對戰車直射交戰 0 次，穿甲表與命中係數表整局未使用。
4. **兩個 AI 的差異不在戰術，在是否追問規則**：藍軍問 30+ 條、紅軍問 0 條。
   45 條裁示雙方同時收到，但只有一方據此改變行為。

詳見 `../../precedents.md`（判例表）與 `../../prompts/referee_pvp.md`（裁判制度）。
