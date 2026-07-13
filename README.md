# 料鋒 Acies · 樞衡 Arbiter

**一款終端機 WWII 師級戰棋，由大型語言模型（LLM）擔任裁判。**
*A terminal WWII division-level wargame where a Large Language Model is the referee.*

![黑潮行動 — La Sève 河防區](assets/screenshot_blacktide.png)

---

> **English abstract.** Most wargames encode their rules as executable code — which is why they are rigid and complex. This project takes a different bet: the rules live as **natural language** (~a dozen Markdown files), and an **LLM plays the referee** — reading the rules, adjudicating combat, maintaining fog of war, and writing after-action reports. There are **no dice**: outcomes are determined by defined inputs; the only uncertainty comes from information asymmetry, hidden state, and reading indicators. You command through a Python/Rich terminal viewer; the AI referee resolves. Two scenarios ship: a single-player campaign vs. an AI opponent, and a symmetric 1v1 PvP map. **This is a concept/experiment, not a plug-and-play game — it needs an LLM and a human running the referee loop** (see below).

---

## 這是什麼

大多數戰棋把規則寫成 code，於是又硬又複雜。這個專案賭另一條路：

- **規則用自然語言寫**（十來個 Markdown 檔），**LLM 當裁判**——讀規則、解算戰鬥、維護戰爭迷霧、產出戰報。
- **不擲骰**：結果由定義好的輸入推出；不確定性只來自**資訊不對稱、隱藏狀態、徵候推理**三件事。
- 你透過 Python/Rich 的終端機介面下令，AI 裁判結算。

**「料鋒 Acies」是遊戲、「樞衡 Arbiter」是引擎**（中樞全知 + 權衡裁決）。

## ⚠️ 先講清楚：這不是「下載就能玩」的遊戲

- 裁判和 AI 對手都是 **LLM**——你需要一把 [Anthropic Claude API](https://www.anthropic.com/api) key（環境變數 `ANTHROPIC_API_KEY`）。
- 目前是**由人（GM）驅動裁判流程**的框架/概念驗證，不是全自動、點兩下就開局的成品。
- 尚在開發中、實戰測試有限。當作「一個新穎的戰棋引擎實驗」來看比較準。

## 特色

- **LLM-as-referee**：規則即自然語言，AI 讀規則、判勝負。
- **零機率確定性**：無骰、無亂數；戰場迷霧來自偵察與隱藏，不是運氣。
- **三層戰爭迷霧**：server 端 `filter_state_for` 過濾 → 玩家視角 → AI 參謀只吃過濾後資料。
- **小時級命令 + 延遲佇列**：命令按複雜度延遲生效（L1/L2/L3），模擬指揮鏈時滯。
- **營級 ORBAT**：師完整攤開到營，可拆出任一營單獨運用。
- **擬真終端機地圖**：Rich 渲染地形/兵種/朝向/補給線，固定緩衝網格對齊座標。

## 兩個劇本

| 劇本 | 類型 | 特色 |
|------|------|------|
| **黑潮行動 Black Tide** | 單機 vs AI | 美軍 III Corps 48 小時強渡 La Sève 河、奪 Saint-Vivien；敵軍由 Claude 扮演的「Adler」指揮官應戰（有記憶、會學習）。 |
| **純戰場 Open Field** | 1v1 PvP | 對稱平衡、地形中立的純戰術對決。含**補給線攔截**與**指揮所/斬首**機制；勝負看殲敵。 |

![純戰場 — 補給線（虛線）+ 指揮所（主/前★）](assets/screenshot_openfield.png)

*純戰場：虛線是補給走廊（藍暢通／黃受威脅／紅切斷）；`主`/`前★` 是指揮所（★=軍長所在）。*

## 安裝

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...        # AI 裁判/參謀需要
```

## 開始

```bash
# 生成乾淨開局
python3 blacktide_setup.py             # 黑潮行動 → state.json
python3 openfield_setup.py             # 純戰場   → maps/open_field_state.json

# 觀戰（終端機地圖）
python3 map.py                                                    # 黑潮，god 視角
python3 map.py --state maps/open_field_state.json --supply       # 純戰場 + 補給線層
python3 map.py --side allies                                     # 玩家視角（只看自己+偵獲敵軍）

# 查營級編制
python3 orbat.py --side allies
```

裁判實際怎麼跑一局，見 `prompts/referee_gm.md`（黑潮）與 `prompts/referee_pvp.md`（純戰場）。

## 架構（主要模組）

| 檔案 | 職責 |
|------|------|
| `mapcore.py` | 共用渲染核心：地形/單位/補給線層、迷霧過濾 |
| `map.py` | 終端機即時觀戰器 |
| `orbat.py` | 營級編制、拆分/歸建 |
| `hourstate.py` | 小時級時鐘 + 命令延遲佇列 |
| `command.py` | 指揮所/通訊延遲/斬首（PvP） |
| `advisor.py` | AI 參謀（Claude API，只吃過濾後視角） |
| `server.py` / `client.py` | 1v1 聯機（token 驗證 + Cloudflare Tunnel） |
| `*_v1.md` / `scenario*.md` | 自然語言規則與劇本定義 |

## 現狀

概念驗證階段。引擎與兩個劇本已成形、有單元測試（`python3 test_hourstate.py`、`python3 command.py`），但實戰對局測試仍有限。歡迎當成 LLM 驅動遊戲設計的一個實驗來把玩、批評、fork。

## 授權

[MIT](LICENSE)
