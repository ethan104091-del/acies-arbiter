"""資料表（見計劃 §3.1）。

原則：
- 事件序列（events）與快照／決定紀錄是真相，桌的「當前狀態」欄位只是方便查詢的推導。
- 決定紀錄以 (table_id, gh, attempt) 為冪等鍵，寫入後不改；掛起後重跑是新的 attempt。
- 席位的陣營由權杖推得，後端任何介面都不接受呼叫端宣告的陣營。
"""
import datetime as dt
import enum
import uuid

from sqlalchemy import (JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Json = JSON().with_variant(JSONB, "postgresql")


def _uuid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TableStatus(str, enum.Enum):
    recruiting = "募集"
    running = "進行"
    awaiting_adjudication = "待人工裁定"
    finished = "終局"


class RoundStatus(str, enum.Enum):
    open = "窗口開啟"
    reopened = "裁示後重開"
    ready = "雙方到齊"
    registering = "登記中"
    resolving = "解算中"
    committed = "已落定"


class SeatRole(str, enum.Enum):
    allies = "allies"
    axis = "axis"
    referee = "referee"       # 裁判席（人工裁定、上帝視角）
    observer = "observer"


class Table(Base):
    __tablename__ = "tables"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, default="")
    scenario_id: Mapped[str] = mapped_column(String)
    status: Mapped[TableStatus] = mapped_column(Enum(TableStatus, name="table_status"), default=TableStatus.recruiting)
    tick: Mapped[int] = mapped_column(Integer, default=0)
    global_hour: Mapped[int] = mapped_column(Integer, default=0)
    tick_hours: Mapped[int] = mapped_column(Integer, default=6)
    max_ticks: Mapped[int] = mapped_column(Integer, default=8)
    settings: Mapped[dict] = mapped_column(Json, default=dict)     # 模型、門檻、輪詢間隔、前綴 A 的 token 數與雜湊
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    seats: Mapped[list["Seat"]] = relationship(back_populates="table")


class Seat(Base):
    __tablename__ = "seats"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    role: Mapped[SeatRole] = mapped_column(Enum(SeatRole, name="seat_role"))
    label: Mapped[str] = mapped_column(String, default="")
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    table: Mapped[Table] = relationship(back_populates="seats")
    __table_args__ = (UniqueConstraint("table_id", "role", "label", name="uq_seat"),)


class Round(Base):
    """桌×tick：提交窗口與租約。"""
    __tablename__ = "rounds"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    status: Mapped[RoundStatus] = mapped_column(Enum(RoundStatus, name="round_status"), default=RoundStatus.open)
    window_opened_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_deadline: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed: Mapped[dict] = mapped_column(Json, default=dict)     # {"allies": order_version|null, "axis": ...}
    lease_worker: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)   # command_v2 §4.4：每 tick 只重開一次
    __table_args__ = (UniqueConstraint("table_id", "tick", name="uq_round"),)


class Order(Base):
    """命令原文（四段），每次修訂一列；同 (table, tick, side, version) 唯一，冪等鍵去重。"""
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("table_id", "tick", "side", "version", name="uq_order_version"),
                      UniqueConstraint("table_id", "side", "idempotency_key", name="uq_order_idem"))


class Clause(Base):
    """條款帳：裁判的外部記憶。"""
    __tablename__ = "clauses"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    clause_id: Mapped[str] = mapped_column(String)            # 例 藍T5-4、紅T5-應變2
    side: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)                 # standing/contingency/self_constraint/question/legal
    tick: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(String, nullable=True)
    issued_gh: Mapped[int] = mapped_column(Integer)
    effective_gh: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")   # pending/active/superseded/blocked/rejected/expired/consumed
    units: Mapped[list] = mapped_column(Json, default=list)
    supersedes: Mapped[list] = mapped_column(Json, default=list)
    superseded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    phase: Mapped[dict] = mapped_column(Json, default=dict)
    predicate: Mapped[str | None] = mapped_column(Text, nullable=True)      # 應變的形式化述詞
    consumed_gh: Mapped[int | None] = mapped_column(Integer, nullable=True)
    history: Mapped[list] = mapped_column(Json, default=list)
    __table_args__ = (UniqueConstraint("table_id", "clause_id", name="uq_clause"),)


class Snapshot(Base):
    """某小時**開始**時的全知狀態。"""
    __tablename__ = "snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    gh: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict] = mapped_column(Json)
    state_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("table_id", "gh", name="uq_snapshot"),)


class Dossier(Base):
    """每次裁判呼叫的卷宗留痕：區塊清單、雜湊、請求與回應原文、用量。"""
    __tablename__ = "dossiers"
    id: Mapped[str] = mapped_column(String, primary_key=True)          # {table}-gh{gh}-a{attempt}[-r]
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    gh: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String)                          # register / resolve
    blocks: Mapped[list] = mapped_column(Json)
    dossier_hash: Mapped[str] = mapped_column(String)
    request: Mapped[dict] = mapped_column(Json)
    response: Mapped[dict | None] = mapped_column(Json, nullable=True)
    model: Mapped[str] = mapped_column(String)
    usage: Mapped[dict] = mapped_column(Json, default=dict)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Decision(Base):
    """一小時一份的決定紀錄＋執行結果。(table, gh, attempt) 冪等；落定的那筆 committed=True。"""
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    gh: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String, default="resolve")
    dossier_id: Mapped[str | None] = mapped_column(ForeignKey("dossiers.id"), nullable=True)
    decision: Mapped[dict] = mapped_column(Json)
    validation: Mapped[list] = mapped_column(Json, default=list)
    execution: Mapped[dict | None] = mapped_column(Json, nullable=True)
    end_state_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    committed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="pending")   # pending/rejected/suspended/committed/superseded
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("table_id", "gh", "kind", "attempt", name="uq_decision_attempt"),)


class Ruling(Base):
    __tablename__ = "rulings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    ruling_id: Mapped[str] = mapped_column(String)
    seq: Mapped[int] = mapped_column(Integer)                  # 本局編號
    gh: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict] = mapped_column(Json)                   # condition/effect/basis/anchor/why_not_tier1/beneficiary/precedent
    beneficiary_actual: Mapped[str | None] = mapped_column(String, nullable=True)   # 執行後由後端另標
    text_hash: Mapped[str] = mapped_column(String)             # 公開文字雜湊（雙方相同可查）
    source: Mapped[str] = mapped_column(String, default="referee")   # referee / adjudication
    __table_args__ = (UniqueConstraint("table_id", "ruling_id", name="uq_ruling"),)


class Signal(Base):
    """單方徵候（唯一的單方通道），已過洩漏檢查。"""
    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    gh: Mapped[int] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)


class Brief(Base):
    """每 tick 每方的簡報全文＋共用段雜湊。"""
    __tablename__ = "briefs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    shared_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("table_id", "tick", "side", name="uq_brief"),)


class Pending(Base):
    """待裁定項目與人的回覆。"""
    __tablename__ = "pending"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    pending_id: Mapped[str] = mapped_column(String)
    gh: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String)             # register / resolve
    kind: Mapped[str] = mapped_column(String)
    side: Mapped[str | None] = mapped_column(String, nullable=True)
    clause_id: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[dict] = mapped_column(Json)
    material: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="open")     # open / answered
    answer: Mapped[dict | None] = mapped_column(Json, nullable=True)  # kind/public_text/private_text/applies_from_gh
    answered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("table_id", "pending_id", name="uq_pending"),)


class Question(Base):
    """給裁判的問題與答覆。"""
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    side: Mapped[str] = mapped_column(String)
    question_id: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    answer: Mapped[dict | None] = mapped_column(Json, nullable=True)   # kind(general/private)/public_text/private_text/ruling_id
    __table_args__ = (UniqueConstraint("table_id", "question_id", name="uq_question"),)


class Event(Base):
    """全部狀態變遷的事件序列。"""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    gh: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(Json, default=dict)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Precedent(Base):
    """判例（跨桌）。自 law/precedents.md 匯入＋各局新增。"""
    __tablename__ = "precedents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String, unique=True)      # 例 §二十五、E7、R-tbl01-072
    addr: Mapped[str] = mapped_column(String, default="")      # 規範住址
    body: Mapped[dict] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String, default="定案")
    origin_table_id: Mapped[str | None] = mapped_column(String, nullable=True)
