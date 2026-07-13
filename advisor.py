#!/usr/bin/env python3
"""AI 參謀 — 即時呼叫 Claude API 回答某一方的戰術提問。

由 server.py 的 /advise endpoint 呼叫。嚴格分離：
  - 參謀只吃「該方過濾後視角」(mapcore.filter_state_for) + 該方戰報，
    絕不接觸對方底牌 —— 迷霧在 AI 層的防線。
  - system prompt 用 prompts/advisor_<side>.md（裁判/參謀角色分離）。

設計（依 claude-api skill）：
  - 模型 claude-opus-4-8、adaptive thinking。
  - Prompt caching：system（角色設定 + 規則，穩定）打 cache breakpoint；
    每次變動的戰況(state+report+問題)放在 user turn，在 breakpoint 之後。
  - 缺 anthropic SDK 或 ANTHROPIC_API_KEY 時回傳友善錯誤，不讓 server 崩潰。

需求：pip install anthropic ；環境變數 ANTHROPIC_API_KEY。
"""
import json
from pathlib import Path

GAME_DIR = Path.home() / "war-game"
PROMPTS_DIR = GAME_DIR / "prompts"
STATE_PATH = GAME_DIR / "state.json"

MODEL = "claude-haiku-4-5"   # 2026-06 玩家定案：參謀用 Haiku 省 token（見 run_architecture.md）
SIDE_ZH = {"allies": "盟軍 III Corps（Phoenix）", "axis": "德軍 Panzergruppe Hartmann（Adler）"}

# 規則檔：當作參謀的共用知識（公開資訊，雙方都能讀）。
# 放進 system 一起 cache，讓參謀真的「懂規則」。
RULE_FILES = ["scenario.md", "forces_v1.md", "combat_v1.md",
              "weather_v1.md", "recon_v1.md", "rules_v2.md"]

_client = None
_import_error = None
try:
    import anthropic
    _client = anthropic.Anthropic()   # 從 ANTHROPIC_API_KEY 解析
except Exception as e:                 # 缺套件或缺 key 都接住
    _import_error = str(e)


def available():
    """參謀通道是否可用（SDK 裝了 + client 建得起來）。"""
    return _client is not None


def status():
    if _client is not None:
        return "ready"
    return f"unavailable: {_import_error or 'anthropic SDK 未安裝或 ANTHROPIC_API_KEY 未設'}"


def _load_system(side):
    """組 system prompt：角色模板 + 共用規則知識（穩定內容，整段 cache）。"""
    role_path = PROMPTS_DIR / f"advisor_{side}.md"
    role = role_path.read_text() if role_path.exists() else \
        f"你是{SIDE_ZH.get(side, side)}的參謀，協助指揮官推敲命令、解讀戰報。"
    parts = [role, "\n\n===== 戰役規則參考（公開資訊）=====\n"]
    for fn in RULE_FILES:
        p = GAME_DIR / fn
        if p.exists():
            parts.append(f"\n### {fn}\n{p.read_text()}\n")
    return "".join(parts)


def _load_context(side):
    """組每回合變動的戰況：過濾後 state + 該方戰報。"""
    import mapcore as mc
    try:
        state = json.loads(STATE_PATH.read_text())
    except Exception as e:
        return f"(讀不到 state.json：{e})"
    filt = mc.filter_state_for(state, side)
    report_path = GAME_DIR / f"report_{side}.md"
    report = report_path.read_text() if report_path.exists() else "（尚無戰報）"
    return (
        f"=== 你的視角戰況（已過濾，看不到敵方底牌）===\n"
        f"```json\n{json.dumps(filt, ensure_ascii=False, indent=1)}\n```\n\n"
        f"=== 你方最新戰報 ===\n{report}\n"
    )


def ask(side, question):
    """回答某一方的參謀提問。回傳 (ok: bool, text: str)。"""
    if side not in ("allies", "axis"):
        return False, "side 必須是 allies 或 axis"
    if not available():
        return False, f"參謀暫時無法使用（{status()}）。請 GM 確認 anthropic SDK 與 API key。"

    system = _load_system(side)
    context = _load_context(side)
    user_content = f"{context}\n=== 指揮官提問 ===\n{question.strip()}\n"

    try:
        # system 放穩定內容並打 cache breakpoint；user turn 放每回合變動的戰況+問題。
        resp = _client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=[{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},   # 角色+規則整段快取
            }],
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as e:
        # anthropic 各類錯誤（rate limit / auth / network）統一回友善訊息
        return False, f"參謀呼叫失敗：{type(e).__name__}: {e}"

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    # 記錄快取命中（除錯用，不影響回覆）
    try:
        u = resp.usage
        print(f"  [advisor:{side}] cache_read={u.cache_read_input_tokens} "
              f"cache_write={u.cache_creation_input_tokens} in={u.input_tokens} out={u.output_tokens}")
    except Exception:
        pass
    return True, text.strip() or "(參謀沒有回覆內容)"


if __name__ == "__main__":
    # 本機快速測試： python3 advisor.py axis "我該怎麼守 Saint-Vivien？"
    import sys
    print("advisor 狀態：", status())
    if len(sys.argv) >= 3 and available():
        ok, ans = ask(sys.argv[1], " ".join(sys.argv[2:]))
        print("=" * 50)
        print(ans)
