"""決定紀錄的綱要（單一來源）：同時用於模型的結構化輸出、後端驗證、重放器輸入。"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Side = Literal["allies", "axis"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(Strict):
    side: Side
    clause_id: str = Field(description="條款識別，例 藍T5-4、紅T5-應變2")
    quote: str = Field(description="命令原文逐字引用")
    predicate_eval: Optional[str] = Field(default=None, description="述詞如何求值（挑執行者、挑目標的依據）")


class Primitive(Strict):
    primitive: str
    args: dict = Field(default_factory=dict)


class Action(Strict):
    seq: int
    tier: Literal[1, 2] = 1
    verb: Optional[str] = Field(default=None, description="一級動詞名稱；二級動作留空")
    args: dict = Field(default_factory=dict)
    ruling_id: Optional[str] = Field(default=None, description="二級動作必須指向本小時的裁示")
    applied: list[Primitive] = Field(default_factory=list, description="二級動作的原語清單")
    provenance: Provenance


class Anchor(Strict):
    period: str = ""
    equipment: str = ""
    situation: str = ""
    magnitude: str = ""


class Ruling(Strict):
    ruling_id: str
    condition: str = Field(description="條件，不得指名陣營")
    effect: str = Field(description="效果，必須由狀態算得出來，不得含機率")
    basis: str = ""
    anchor: Optional[Anchor] = None
    why_not_tier1: str = ""
    beneficiary: Literal["favours_attacker", "favours_defender", "favours_mover",
                         "favours_stationary", "favours_fortified", "neutral"] = "neutral"
    precedent: bool = False


class ContingencyCheck(Strict):
    cont_id: str
    evaluated: bool = True
    fired: bool = False
    evidence: str = ""


class PendingItem(Strict):
    pending_id: str
    kind: Literal["unexpandable_clause", "undecidable_condition", "ambiguous_unit",
                  "material_ambiguity", "audit_failed", "magnitude_threshold", "other"]
    side: Optional[Side] = None
    clause_id: Optional[str] = None
    quote: str = ""
    question: str
    material: bool = False


class Answer(Strict):
    question_id: str
    kind: Literal["general", "private"]
    public_text: str = ""
    private_text: str = ""
    ruling_id: Optional[str] = None


class ClauseUpdate(Strict):
    clause_id: str
    side: Optional[Side] = None
    kind: Optional[Literal["standing", "contingency", "self_constraint", "question", "legal"]] = None
    text: Optional[str] = None
    level: Optional[str] = None
    units: Optional[list[str]] = None
    status: Optional[Literal["pending", "active", "superseded", "blocked", "rejected", "expired", "consumed"]] = None
    supersedes: Optional[list[str]] = None
    superseded_by: Optional[str] = None
    phase: Optional[dict] = None
    predicate: Optional[str] = None


class Signals(Strict):
    allies: list[str] = Field(default_factory=list)
    axis: list[str] = Field(default_factory=list)


class HourDecision(Strict):
    schema_: str = Field(default="acies.HourDecision/1", alias="schema")
    kind: Literal["register", "resolve"] = "resolve"
    gh: int
    contingency_checks: list[ContingencyCheck] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    rulings: list[Ruling] = Field(default_factory=list)
    signals: Signals = Field(default_factory=Signals)
    pending: list[PendingItem] = Field(default_factory=list)
    answers: list[Answer] = Field(default_factory=list)
    clause_updates: list[ClauseUpdate] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def json_schema():
    return HourDecision.model_json_schema(by_alias=True)


def parse(obj):
    return HourDecision.model_validate(obj).model_dump(by_alias=True)


# ── OpenAI 嚴格綱要變體（codex exec --output-schema 用）─────────────────────
# OpenAI 結構化輸出要求：每個物件 additionalProperties=false、所有屬性都在 required；
# 自由字典（動作參數、原語參數、條款階段）要換成固定鍵的物件，缺的鍵填 null，回來時再剝掉。
ARG_KEYS = ["uid", "dest", "shooters", "target", "mission", "hex", "attackers", "div", "code", "pos",
            "side", "kind", "level", "text", "unit_uids", "by_uid",
            "personnel", "tanks", "guns", "org", "str_pct", "fatigue", "note", "hexes", "man_hours", "occupant"]
_ARG_TYPES = {"dest": {"type": "array", "items": {"type": "integer"}}, "hex": {"type": "array", "items": {"type": "integer"}},
              "pos": {"type": "array", "items": {"type": "integer"}},
              "shooters": {"type": "array", "items": {"type": "string"}}, "attackers": {"type": "array", "items": {"type": "string"}},
              "unit_uids": {"type": "array", "items": {"type": "string"}},
              "personnel": {"type": "integer"}, "tanks": {"type": "integer"}, "guns": {"type": "integer"},
              "hexes": {"type": "integer"}, "org": {"type": "number"}, "str_pct": {"type": "number"},
              "fatigue": {"type": "number"}, "man_hours": {"type": "number"}}


def _nullable(t):
    return {"anyOf": [t, {"type": "null"}]}


def _args_object():
    return {"type": "object", "additionalProperties": False, "required": list(ARG_KEYS),
            "properties": {k: _nullable(_ARG_TYPES.get(k, {"type": "string"})) for k in ARG_KEYS}}


def _strictify(node, path=()):
    if isinstance(node, dict):
        if node.get("type") == "object":
            props = node.get("properties")
            if props is None:                                   # 自由字典
                if path and path[-1] == "phase":
                    return {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                       "required": ["unit", "phase"],
                                                       "properties": {"unit": {"type": "string"}, "phase": {"type": "string"}}}}
                return _args_object()
            req = set(node.get("required", []))
            new_props = {}
            for k, v in props.items():
                v2 = _strictify(v, path + (k,))
                v2.pop("default", None)
                if k not in req and not (isinstance(v2, dict) and "anyOf" in v2 and any(x.get("type") == "null" for x in v2["anyOf"])):
                    v2 = _nullable(v2)
                new_props[k] = v2
            out = {k: v for k, v in node.items() if k not in ("properties", "required", "additionalProperties", "default", "$defs")}
            if "$defs" in node:
                out["$defs"] = {k: _strictify(v, path + ("$defs", k)) for k, v in node["$defs"].items()}
            out.update({"properties": new_props, "required": list(props.keys()), "additionalProperties": False})
            return out
        return {k: (_strictify(v, path + (k,)) if k in ("items", "anyOf", "$defs", "properties") or isinstance(v, (dict, list)) else v)
                for k, v in node.items() if k != "default"}
    if isinstance(node, list):
        return [_strictify(x, path) for x in node]
    return node


def openai_strict_schema(schema_obj=None):
    return _strictify(schema_obj or json_schema())


def from_strict(obj, phase_as_list=True):
    """把嚴格變體的輸出還原：剝掉 null 鍵、（決定紀錄的）階段陣列還原成字典。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if v is None:
                continue
            if phase_as_list and k == "phase" and isinstance(v, list):
                out[k] = {x["unit"]: x["phase"] for x in v if isinstance(x, dict)}
            else:
                out[k] = from_strict(v, phase_as_list)
        return out
    if isinstance(obj, list):
        return [from_strict(x, phase_as_list) for x in obj]
    return obj
