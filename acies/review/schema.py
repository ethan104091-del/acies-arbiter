"""審查官的結構化回答。"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Conflict(Strict):
    source: str = Field(description="規則檔名與節，或判例節號")
    quote: str = Field(description="引用原文")
    why: str


class Revision(Strict):
    condition: str = Field(description="修訂後的條件；不得指名陣營")
    effect: str = Field(description="修訂後的效果；不得含機率")


class Amendment(Strict):
    file: str = Field(description="要註記的規則檔，例 60_指揮.md")
    section: str = Field(description="節，例 §2")
    sentence: str = Field(description="要插入規則檔的一句話（規則語氣，不是敘事）")


class Review(Strict):
    derivable_from_rules: bool = Field(description="能否從現行規則直接推出（是→它不是新規則，只是解讀）")
    derivation: str = Field(description="推出的依據或推不出的原因")
    conflicts: list[Conflict] = Field(default_factory=list, description="與規則或既有判例的衝突，附引文；無則空")
    exploit: str = Field(description="指揮官會怎麼濫用這條裁示；若無則說明為何無")
    beneficiary_ok: bool
    beneficiary_should_be: Literal["favours_attacker", "favours_defender", "favours_mover",
                                   "favours_stationary", "favours_fortified", "neutral"]
    verdict: Literal["定案", "推翻", "改寫"]
    revision: Optional[Revision] = None
    amendment: Optional[Amendment] = Field(default=None, description="推翻或改寫時，規則檔要加的一句話")
    reasoning: str = Field(description="結論的理由，三到八句")


def json_schema():
    return Review.model_json_schema()


def parse(obj):
    return Review.model_validate(obj).model_dump()
