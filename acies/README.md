# 料鋒 Acies v2 — 後端／裁判工作者／網頁前端

設計依據：`docs/design_v2_referee.md`；施工計劃：`~/.claude/plans/tranquil-frolicking-pike.md`。
v1 引擎（`arbiter.py` 等）不動，只新增 `begin_tick`／`run_hour`（`tests/test_run_hour_equivalence.py` 證明等價）。

## 結構

| 目錄 | 內容 |
|---|---|
| `acies/engine/` | 引擎轉接層：狀態進出與雜湊、單一迷霧投影（頂層鍵白名單）、洩漏／對稱檢查、一級動詞登錄表、執行器、決定紀錄→命令清單（餵 v1 `_audit`）、沙盒量級、重放器 |
| `acies/db/` | Postgres 資料表（SQLAlchemy）與遷移（alembic） |
| `acies/service/` | 席位權杖、建桌、提交窗口與命令、簡報發布、工作佇列與逐小時落定／掛起／人工裁定 |
| `acies/api/` | 網頁後端介面（前端中立，全部輪詢） |
| `acies/referee/` | 決定紀錄綱要、機械護欄、卷宗三段組裝與留痕、模型呼叫、工作者迴圈、假裁判 |
| `acies/ledger/` | 條款帳規則（到期生效、應變過期、完整性） |
| `acies/prompts/referee_v2.md` | 裁判手冊 v2（卷宗前綴 A1） |
| `web/` | React＋TypeScript 前端：入席、戰場、命令、簡報、裁示、問答、裁判席、觀戰 |

## 本機執行

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-v2.txt
createdb acies && .venv/bin/alembic upgrade head
.venv/bin/uvicorn acies.api.app:app --port 8000          # 後端
# 裁判呼叫模型的方式（每桌設定 llm_backend）：
#   cli（預設）＝這台機器已登入的 Claude Code（`claude -p`，走訂閱方案，不用金鑰）
#   api＝開發者平台金鑰用量計費，金鑰寫進 .env（ANTHROPIC_API_KEY=，不進版本控制）
.venv/bin/python -m acies.referee.worker                 # 裁判工作者（--once 只處理一件）
cd web && npm install && npm run dev                     # 前端 http://localhost:5173（/api 轉 8000）
```

測試：`.venv/bin/python -m pytest acies/tests/`（需本機 Postgres，會重建 `acies_test`）；
v1 四支舊測試與等價測試用 `python3 tests/<檔>.py`。

實測基準：`.venv/bin/python -m acies.tools.seed_run7_t5` 建一桌從 Run 7 T5（gh30）起始、雙方定稿命令已送入的桌，
再跑工作者逐小時解算，對照 `runs/run7_openfield/t5.py` 的人工展開。

## 每小時流程（摘要）

取件（租約）→ 小時起始快照 → 卷宗（前綴 A 整局凍結、前綴 B 每 tick、尾段每小時；全部留痕）→ 模型
→ 決定紀錄 → 驗證（綱要、G2 條件不指名陣營、G3 無機率、G9 完整性、G10 出處）→ 沙盒量級（G4）
→ `run_hour`（動作依序呼叫動詞）→ v1 `_audit` 十四項 → 徵候洩漏檢查 → 落定（冪等鍵 桌／小時／種類／attempt）
→ tick 末：應變過期、開新窗口、發雙方簡報（共用段雜湊相等）。
掛起（超門檻、連續退回、模型無效輸出）＝該小時不落定，桌轉「待人工裁定」，裁判席回覆後以新 attempt 重跑。

## 判例審查（`acies/review/`，2026-09-17）

終局後自動跑（工作者收到終局結果即呼叫），也可手動：`.venv/bin/python -m acies.review.run <桌前綴> [--dry] [--force]`。

1. `checks.py` 機械檢查：形式（陣營字樣、機率用語）、效果數字在規則書有無出處、與既有判例／規則段落的相似段、必要欄位（依據、錨點、為何一級不夠）、影響統計。影響門檻是通式：被引用小時沙盒量到的單方分數位移累計 ＞ `TIE_BAND × 終局較高分`，或單方戰力位移 ＞ 1%。
2. `reviewer.py` 兩官：Claude Opus（`claude -p`）與 Codex（`gpt-5.6-terra`，xhigh），同一本 `acies/prompts/reviewer.md`，結構化回答五題＋結論（定案／推翻／改寫）。
3. `debate.py`：結論不一致就把對方意見交給彼此重答，最多三輪；仍不一致 → 爭議，不入判例。
4. `writer.py`：定案／改寫／推翻都追加 `law/precedents.md` 新節；推翻／改寫另在規則檔對應節插入「★ 判例 §N（自動審查）」一句；資料庫裁示標狀態；每次寫 `law/review_log/<日期>_<桌>.md`，逐項記改動點、改動前原文、兩官意見與辯論。

不需要人按；你只看 `law/review_log/`。
