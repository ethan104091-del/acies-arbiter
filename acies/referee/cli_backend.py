"""以這台機器已登入的 Claude Code（`claude -p`）呼叫模型——走訂閱方案，不用 API 金鑰。

與 llm.call 同介面：call(system, messages, *, model, effort, resume=None) → (decision|None, info)。
- 系統提示（前綴 A＋B）寫進暫存檔用 --system-prompt-file 傳入，並排除 Claude Code 的動態段落。
- 使用者訊息走標準輸入；重出時用 --resume <session_id> 在同一段對話追加錯誤訊息。
- 結構化輸出用 --json-schema，結果在 structured_output。
- 不給任何工具（--tools ""），單回合。
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from . import schema

CLAUDE_BIN = os.environ.get("ACIES_CLAUDE_BIN", "claude")
# 固定工作目錄：Claude Code 會把工作目錄放進系統提示，每次用不同暫存目錄會讓 19 萬 token 的前綴每小時重建快取
# （Run 8 實測：cache_creation 188k／cache_read 65k，每小時皆然）。
CWD = Path(os.environ.get("ACIES_CLAUDE_CWD", Path.home() / ".acies" / "referee_cwd"))
TIMEOUT = int(os.environ.get("ACIES_CLAUDE_TIMEOUT", "2400"))


def call(system, messages, *, model="claude-opus-5", effort="high", resume=None, max_tokens=None, schema_obj=None):
    """schema_obj：結構化輸出的 JSON 綱要（預設為決定紀錄）。"""
    # 系統提示只放前綴 A（整局凍結）；前綴 B（每 tick、且條款狀態逐小時會變）併進使用者訊息開頭。
    # CLI 只有一個快取斷點在系統提示末尾，B 放進去會讓 A 每小時都重建（實測 209k token 重建 vs 5 秒命中）。
    blocks = system if isinstance(system, list) else [{"text": str(system)}]
    sys_text = blocks[0]["text"]
    b_text = "\n\n".join(b["text"] for b in blocks[1:])
    user = messages[-1]["content"]
    if not resume and b_text:
        user = b_text + "\n\n---\n\n" + user
    with tempfile.TemporaryDirectory(prefix="acies-cli-") as tmp:
        sp = os.path.join(tmp, "system.md")
        with open(sp, "w") as f:
            f.write(sys_text)
        cmd = [CLAUDE_BIN, "-p", "--output-format", "json", "--json-schema", json.dumps(schema_obj or schema.json_schema()),
               "--model", model, "--effort", effort, "--max-turns", "3", "--tools", ""]   # 結構化輸出在 CLI 內是一次工具呼叫；給它重試的餘地
        if resume:
            cmd += ["--resume", resume]
        else:
            cmd += ["--system-prompt-file", sp, "--exclude-dynamic-system-prompt-sections"]
        try:
            CWD.mkdir(parents=True, exist_ok=True)
            p = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=TIMEOUT, cwd=str(CWD))
        except subprocess.TimeoutExpired:
            return None, {"backend": "cli", "error": "timeout", "text": ""}
    info = {"backend": "cli", "returncode": p.returncode, "stderr": p.stderr[-2000:], "text": ""}
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        info["json_error"] = "claude -p 未回 JSON"; info["raw"] = p.stdout[-2000:]
        return None, info
    info["cli"] = {k: d.get(k) for k in ("subtype", "terminal_reason", "num_turns", "api_error_status", "permission_denials")}
    info.update({"session_id": d.get("session_id"), "stop_reason": d.get("stop_reason"),
                 "request_id": d.get("uuid"), "model": model, "is_error": d.get("is_error"),
                 "usage": {k: (d.get("usage") or {}).get(k) for k in
                           ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")},
                 "list_price_usd": d.get("total_cost_usd"), "text": d.get("result") if isinstance(d.get("result"), str) else ""})
    if d.get("is_error"):
        info["json_error"] = f"claude -p 錯誤：{d.get('subtype')}／{d.get('terminal_reason')}／{str(d.get('result'))[:300]}"
        info["infra_error"] = True
        return None, info
    out = d.get("structured_output")
    if out is None and isinstance(d.get("result"), str):
        try:
            out = json.loads(d["result"])
        except json.JSONDecodeError as e:
            info["json_error"] = str(e)
            return None, info
    info["text"] = json.dumps(out, ensure_ascii=False)
    return out, info
