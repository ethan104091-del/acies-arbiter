"""模型呼叫：claude-opus-5、自適應思考、結構化輸出、兩個一小時的快取斷點、串流取完整回應。
回傳 (決定 dict 或 None, 回應摘要 dict)。驗證失敗的重出用同一段對話追加錯誤訊息。
"""
import json
import os

from . import schema

MODEL_DEFAULT = "claude-opus-5"

_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or _try_client()


def _try_client():
    try:
        client(); return True
    except Exception:
        return False


def call(system, messages, *, model=MODEL_DEFAULT, effort="high", max_tokens=32000, resume=None):
    """messages：[{role, content}]；回傳 (decision|None, info)。"""
    with client().messages.stream(
        model=model, max_tokens=max_tokens, system=system, messages=messages,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema.json_schema()}},
    ) as stream:
        resp = stream.get_final_message()
    text = next((b.text for b in resp.content if b.type == "text"), "")
    info = {"request_id": getattr(resp, "_request_id", None), "model": resp.model, "stop_reason": resp.stop_reason,
            "usage": {k: getattr(resp.usage, k, None) for k in
                      ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")},
            "text": text, "content": [b.model_dump() for b in resp.content]}
    if resp.stop_reason == "refusal":
        info["refusal"] = getattr(resp, "stop_details", None) and resp.stop_details.model_dump()
        return None, info
    try:
        return json.loads(text), info
    except json.JSONDecodeError as e:
        info["json_error"] = str(e)
        return None, info
