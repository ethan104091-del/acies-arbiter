"""以這台機器已登入的 Codex（`codex exec`）呼叫模型——走 OpenAI 方案，不用金鑰。

與 llm.call 同介面。整份卷宗（前綴 A＋B＋尾段）從標準輸入送入；OpenAI 對相同前綴自動快取。
結構化輸出用 --output-schema（OpenAI 嚴格綱要變體），最後訊息寫到檔案再讀回。
不載入使用者設定（避免掛上一堆 MCP 伺服器），沙盒唯讀、不落地工作階段。
重出：把上一份決定與錯誤清單接在提示後面（不沿用工作階段）。
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from . import schema

CODEX_BIN = os.environ.get("ACIES_CODEX_BIN", "codex")
TIMEOUT = int(os.environ.get("ACIES_CODEX_TIMEOUT", "2400"))
CWD = Path(os.environ.get("ACIES_CODEX_CWD", Path.home() / ".acies" / "referee_codex"))
EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}


def call(system, messages, *, model="gpt-5.6-terra", effort="high", resume=None, max_tokens=None, schema_obj=None):
    """schema_obj：結構化輸出的 JSON 綱要（預設為決定紀錄）；會轉成 OpenAI 嚴格變體。"""
    # 系統提示只放前綴 A（整局凍結）；前綴 B（每 tick、且條款狀態逐小時會變）併進使用者訊息開頭。
    # CLI 只有一個快取斷點在系統提示末尾，B 放進去會讓 A 每小時都重建（實測 209k token 重建 vs 5 秒命中）。
    blocks = system if isinstance(system, list) else [{"text": str(system)}]
    sys_text = blocks[0]["text"]
    b_text = "\n\n".join(b["text"] for b in blocks[1:])
    convo = "\n\n".join(f"### {'裁判上一份輸出' if m['role'] == 'assistant' else '訊息'}\n\n{m['content']}" for m in messages)
    prompt = f"{sys_text}\n\n---\n\n{b_text}\n\n---\n\n{convo}\n\n只輸出符合輸出綱要的 JSON。"
    CWD.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="acies-codex-") as tmp:
        sp, lp = os.path.join(tmp, "schema.json"), os.path.join(tmp, "last.json")
        with open(sp, "w") as f:
            json.dump(schema.openai_strict_schema(schema_obj), f)
        cmd = [CODEX_BIN, "exec", "-", "--ignore-user-config", "-m", model,
               "-c", f"model_reasoning_effort={EFFORT.get(effort, 'high')}",
               "--output-schema", sp, "-o", lp, "--ephemeral", "--skip-git-repo-check",
               "-s", "read-only", "-C", str(CWD), "--color", "never"]
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT, cwd=str(CWD))
        except subprocess.TimeoutExpired:
            return None, {"backend": "codex", "error": "timeout", "text": ""}
        info = {"backend": "codex", "returncode": p.returncode, "stderr": p.stderr[-2000:], "stdout": p.stdout[-3000:],
                "model": model, "text": "", "usage": {}}
        # 用量：codex exec 的輸出末尾有 tokens used 行
        for line in p.stdout.splitlines()[::-1]:
            if "tokens used" in line.lower():
                info["usage"]["note"] = line.strip(); break
        if not os.path.exists(lp):
            info["json_error"] = f"codex exec 未產生最後訊息（returncode {p.returncode}）"; info["infra_error"] = True
            return None, info
        raw = open(lp).read()
    try:
        out = schema.from_strict(json.loads(raw), phase_as_list=schema_obj is None)
    except json.JSONDecodeError as e:
        info["json_error"] = str(e); info["raw"] = raw[-2000:]
        return None, info
    info["text"] = json.dumps(out, ensure_ascii=False)
    return out, info
