"""網頁後端介面（前端中立，供網頁與日後手機應用共用）。全部輪詢，無推送。

授權：Authorization: Bearer <席位權杖>。陣營由權杖推得；任何介面都不接受呼叫端宣告陣營。
"""
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from acies.db import models as M
from acies.db.session import session
from acies.engine import projection
from acies.service import auth, briefs, rounds, tables, work

app = FastAPI(title="料鋒 Acies v2", version="0.1")
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_db():
    db = session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def current_seat(authorization: Optional[str] = Header(default=None), db=Depends(get_db)):
    tok = authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None
    seat = auth.resolve_seat(db, tok)
    if seat is None:
        raise HTTPException(401, "無效權杖")
    return seat


def _table_of(seat, table_id, db):
    if seat.table_id != table_id:
        raise HTTPException(403, "此權杖不屬於該桌")
    t = tables.get_table(db, table_id)
    if t is None:
        raise HTTPException(404, "無此桌")
    return t


def _side(seat):
    if seat.role in (M.SeatRole.allies, M.SeatRole.axis):
        return seat.role.value
    return None


# ── 建桌與席位 ────────────────────────────────────────────────
class CreateTable(BaseModel):
    name: str = ""
    scenario_id: str = "open_field"
    settings: dict = {}


@app.post("/tables")
def create_table(body: CreateTable, db=Depends(get_db)):
    t, tokens = tables.create_table(db, body.name, body.scenario_id, body.settings)
    return {"table_id": t.id, "tokens": tokens}


@app.get("/me")
def me(seat=Depends(current_seat)):
    return {"table_id": seat.table_id, "role": seat.role.value, "side": _side(seat)}


# ── 對局 ──────────────────────────────────────────────────────
@app.get("/tables/{table_id}")
def table_summary(table_id: str, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    r = tables.get_round(db, t.id, t.tick)
    side = _side(seat)
    out = {"table_id": t.id, "name": t.name, "status": t.status.value, "tick": t.tick, "global_hour": t.global_hour,
           "max_ticks": t.max_ticks, "poll_seconds": t.settings.get("poll_seconds", 30),
           "round": {"status": r.status.value, "deadline": r.window_deadline,
                     "confirmed": (r.confirmed.get(side) is not None) if side else r.confirmed} if r else None}
    if t.status == M.TableStatus.finished:
        out["verdict"] = t.settings.get("verdict")
    return out


@app.get("/tables/{table_id}/state")
def table_state(table_id: str, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    snap = tables.latest_snapshot(db, t.id, t.global_hour)
    side = _side(seat)
    if side is None:
        if seat.role == M.SeatRole.referee or t.status == M.TableStatus.finished:
            return projection.project(snap.state, "god")
        # 觀戰席終局前只看雙方公開段（計分）
        return {"global_hour": t.global_hour, "score": projection.project(snap.state, "allies")["score"]}
    return projection.project(snap.state, side)


@app.get("/tables/{table_id}/brief")
def table_brief(table_id: str, tick: Optional[int] = None, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    side = _side(seat)
    if side is None:
        raise HTTPException(403, "只有陣營席位有簡報")
    b = briefs.get(db, t.id, t.tick if tick is None else tick, side)
    if b is None:
        # T0 尚未產生：即時產出並存檔
        snap = tables.latest_snapshot(db, t.id, t.tick * t.tick_hours)
        briefs.publish(db, t, snap.state, t.tick)
        b = briefs.get(db, t.id, t.tick, side)
    return {"tick": b.tick, "text": b.text, "shared_hash": b.shared_hash}


# ── 命令 ──────────────────────────────────────────────────────
class OrderIn(BaseModel):
    text: str
    idempotency_key: str


@app.put("/tables/{table_id}/rounds/{tick}/order")
def put_order(table_id: str, tick: int, body: OrderIn, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    side = _side(seat)
    if side is None:
        raise HTTPException(403, "只有陣營席位能下命令")
    try:
        o, r = rounds.submit_order(db, t, side, tick, body.text, body.idempotency_key)
    except rounds.WindowClosed as e:
        raise HTTPException(409, str(e))
    return {"version": o.version, "round_status": r.status.value}


@app.post("/tables/{table_id}/rounds/{tick}/confirm")
def confirm(table_id: str, tick: int, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    side = _side(seat)
    if side is None:
        raise HTTPException(403)
    try:
        r = rounds.confirm_unchanged(db, t, side, tick)
    except rounds.WindowClosed as e:
        raise HTTPException(409, str(e))
    return {"round_status": r.status.value}


@app.get("/tables/{table_id}/rounds/{tick}/order")
def get_order(table_id: str, tick: int, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    side = _side(seat)
    if side is None:
        raise HTTPException(403)
    o = rounds.latest_order(db, t.id, tick, side)
    return {"version": o.version, "text": o.text} if o else {"version": 0, "text": ""}


# ── 裁示、問答、待裁定 ───────────────────────────────────────
@app.get("/tables/{table_id}/rulings")
def rulings(table_id: str, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    rows = db.scalars(select(M.Ruling).where(M.Ruling.table_id == t.id).order_by(M.Ruling.seq)).all()
    return [{"seq": r.seq, "ruling_id": r.ruling_id, "gh": r.gh, **r.body, "text_hash": r.text_hash} for r in rows]


class QuestionIn(BaseModel):
    text: str


@app.post("/tables/{table_id}/questions")
def ask(table_id: str, body: QuestionIn, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    side = _side(seat)
    if side is None:
        raise HTTPException(403)
    n = db.scalar(select(M.Question).where(M.Question.table_id == t.id, M.Question.side == side)
                  .order_by(M.Question.id.desc()).limit(1))
    qid = f"Q-{side}-T{t.tick}-{(len(db.scalars(select(M.Question).where(M.Question.table_id == t.id, M.Question.tick == t.tick, M.Question.side == side)).all()) + 1)}"
    q = M.Question(table_id=t.id, tick=t.tick, side=side, question_id=qid, text=body.text)
    db.add(q); db.flush()
    return {"question_id": qid}


@app.get("/tables/{table_id}/questions")
def questions(table_id: str, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    side = _side(seat)
    rows = db.scalars(select(M.Question).where(M.Question.table_id == t.id)).all()
    out = []
    for q in rows:
        a = q.answer or {}
        if side is None or q.side == side:
            out.append({"question_id": q.question_id, "tick": q.tick, "text": q.text, "answer": a})
        elif a.get("kind") == "general":
            out.append({"question_id": q.question_id, "tick": q.tick, "answer": {"public_text": a.get("public_text", "")}})
    return out


@app.get("/tables/{table_id}/adjudications")
def adjudications(table_id: str, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    if seat.role != M.SeatRole.referee:
        raise HTTPException(403, "只有裁判席")
    rows = db.scalars(select(M.Pending).where(M.Pending.table_id == t.id).order_by(M.Pending.gh)).all()
    return [{"pending_id": p.pending_id, "gh": p.gh, "phase": p.phase, "kind": p.kind, "side": p.side,
             "clause_id": p.clause_id, "body": p.body, "status": p.status, "answer": p.answer} for p in rows]


class AdjudicationIn(BaseModel):
    kind: str                      # public_ruling / referee_instruction / clause_rewrite / reject
    public_text: str = ""
    private_text: str = ""
    beneficiary: str = "neutral"
    applies_from_gh: Optional[int] = None


@app.post("/tables/{table_id}/adjudications/{pending_id}/answer")
def answer(table_id: str, pending_id: str, body: AdjudicationIn, seat=Depends(current_seat), db=Depends(get_db)):
    t = _table_of(seat, table_id, db)
    if seat.role != M.SeatRole.referee:
        raise HTTPException(403, "只有裁判席")
    try:
        work.adjudicate(db, t.id, pending_id, body.model_dump())
    except work.WorkError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


# ── 工作者 ────────────────────────────────────────────────────
class ClaimIn(BaseModel):
    worker_id: str
    lease_seconds: int = 900


@app.post("/work/claim")
def claim(body: ClaimIn, db=Depends(get_db)):
    return work.claim(db, body.worker_id, body.lease_seconds)


class DecisionIn(BaseModel):
    worker_id: str
    decision: dict
    dossier_id: Optional[str] = None


@app.post("/work/{table_id}/decision")
def submit_decision(table_id: str, body: DecisionIn, db=Depends(get_db)):
    try:
        return work.submit(db, table_id, body.worker_id, body.decision, body.dossier_id)
    except work.WorkError as e:
        raise HTTPException(409, str(e))


class HeartbeatIn(BaseModel):
    worker_id: str
    lease_seconds: int = 900


@app.post("/work/{table_id}/heartbeat")
def heartbeat(table_id: str, body: HeartbeatIn, db=Depends(get_db)):
    try:
        work.heartbeat(db, table_id, body.worker_id, body.lease_seconds)
    except work.WorkError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/work/{table_id}/release")
def release(table_id: str, body: ClaimIn, db=Depends(get_db)):
    work.release(db, table_id, body.worker_id)
    return {"ok": True}
