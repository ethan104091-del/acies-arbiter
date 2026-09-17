"""兩個獨立審查官：Claude Opus（claude -p）與 Codex 最強推理；額度不足時退成同一模型兩個席位。"""
from acies.referee import cli_backend, codex_backend

from . import dossier, schema

REVIEWERS = {
    "claude": {"call": cli_backend.call, "model": "claude-opus-5", "effort": "high"},
    "codex": {"call": codex_backend.call, "model": "gpt-5.6-terra", "effort": "xhigh"},
}


def ask(name, ruling, checks, applications, *, role, opponent=None, round_=0, backends=None, merge_of=None):
    """回傳 (審查回答 dict 或 None, info)。"""
    b = (backends or REVIEWERS)[name]
    system, user = dossier.build(ruling, checks, applications, role, opponent, round_, merge_of)
    out, info = b["call"](system, [{"role": "user", "content": user}], model=b["model"], effort=b["effort"],
                          schema_obj=schema.json_schema())
    if out is None:
        return None, info
    try:
        return schema.parse(out), info
    except Exception as e:                      # 綱要不合：算這位審查官失敗
        info["json_error"] = f"審查回答不合綱要：{e}"
        return None, info
