"""裁判工作者：取件 → 組卷宗 → 呼叫模型 → 提交 → （被退回則同對話重出一次）→ 落定／掛起。

直接以服務層對資料庫操作（與後端同一信任域）；也可改走 /work 介面。
用法：python -m acies.referee.worker [--once] [--worker-id 名稱]
"""
import argparse
import json
import sys
import time
import uuid

from sqlalchemy import func, select

from acies.db import models as M
from acies.db.session import session
from acies.service import work as W

from . import cli_backend, codex_backend, dossier, llm

BACKENDS = {"api": llm.call, "cli": cli_backend.call, "codex": codex_backend.call}
DEFAULT_MODEL = {"api": "claude-opus-5", "cli": "claude-opus-5", "codex": "gpt-5.6-terra"}

MAX_ATTEMPTS = 2
EFFORT_LADDER = ["low", "medium", "high", "high"]


def _rulings(db, table_id):
    rows = db.scalars(select(M.Ruling).where(M.Ruling.table_id == table_id).order_by(M.Ruling.seq)).all()
    return [{"seq": r.seq, "ruling_id": r.ruling_id, "gh": r.gh, **r.body} for r in rows]


def run_one(worker_id, *, decide=None, prefix_a=None, model=None, log=print):
    """處理一個工作項。decide(system, messages) → (decision, info) 可注入（測試用假模型）。回傳結果 dict 或 None。"""
    with session() as db:
        w = W.claim(db, worker_id)
        db.commit()
        if w is None:
            return None
        w["rulings"] = _rulings(db, w["table_id"])
    settings = w["settings"]
    backend = settings.get("llm_backend", "cli")
    injected = decide is not None
    decide = decide or BACKENDS[backend]
    model = model or settings.get("model") or DEFAULT_MODEL[backend]
    effort0 = settings.get("effort_register" if w["kind"] == "register" else "effort_resolve", "high")
    max_attempts = int(settings.get("max_attempts", MAX_ATTEMPTS))
    messages = []
    result = None
    resume = None
    infra_failures = 0
    for attempt in range(1, max_attempts + 1):
        # 被退回一次就升一級推理強度（低功率省時間，錯了再花錢）
        effort = effort0 if attempt == 1 else EFFORT_LADDER[min(len(EFFORT_LADDER) - 1, EFFORT_LADDER.index(effort0) + attempt - 1 if effort0 in EFFORT_LADDER else attempt)]
        d = dossier.build(w, prefix_a)
        messages = messages or [{"role": "user", "content": d["user"]}]
        with session() as db:      # 同一小時可能多次呼叫（額度失敗、重試、重跑）：卷宗編號用實際序號，不會撞
            n = db.scalar(select(func.count()).select_from(M.Dossier).where(M.Dossier.table_id == w["table_id"],
                                                                          M.Dossier.gh == w["gh"], M.Dossier.kind == w["kind"])) or 0
        dossier_id = f"{w['table_id'][:8]}-gh{w['gh']}-{w['kind']}{w['attempt']}-{n + 1}"
        log(f"[{worker_id}] {dossier_id} 呼叫模型 {model}（{len(d['user'])} 字尾段）")
        decision, info = decide(d["system"], messages, model=model, effort=effort, resume=resume)
        resume = info.get("session_id")
        with session() as db:
            db.add(M.Dossier(id=dossier_id, table_id=w["table_id"], gh=w["gh"], attempt=w["attempt"], kind=w["kind"],
                             blocks=d["blocks"], dossier_hash=d["hash"],
                             request={"system_hashes": [d["prefix_a_hash"], d["prefix_b_hash"]], "messages": messages},
                             response=info, model=model, usage=info.get("usage", {}), request_id=info.get("request_id")))
            db.commit()
        if decision is None:
            log(f"[{worker_id}] 模型未回有效 JSON：{info.get('json_error') or info.get('refusal') or info.get('stop_reason')}")
            if info.get("infra_error") or info.get("json_error"):
                # 呼叫層的錯（額度、CLI 失敗、非 JSON）：第一次改用備援後端重試；再失敗就釋放租約回報錯誤，桌保持進行，不掛起
                infra_failures += 1
                fb = settings.get("llm_fallback_backend")
                if infra_failures == 1 and fb and fb in BACKENDS and not injected:
                    log(f"[{worker_id}] 改用備援後端 {fb}")
                    decide = BACKENDS[fb]; model = DEFAULT_MODEL[fb]
                    messages, resume = [], None
                    continue
                if infra_failures < 2:
                    messages, resume = [], None
                    continue
                with session() as db:
                    W.release(db, w["table_id"], worker_id)
                    from acies.service import events as EV
                    EV.emit(db, w["table_id"], "模型呼叫失敗", gh=w["gh"], info={k: info.get(k) for k in ("json_error", "cli", "stderr")})
                    db.commit()
                return {"status": "error", "why": "invalid_output", "info": info.get("json_error")}
            with session() as db:                 # 模型拒答：掛起等人
                W.suspend(db, w["table_id"], worker_id, "audit_failed",
                          {"question": "模型拒絕輸出決定紀錄", "info": {k: info.get(k) for k in ('stop_reason', 'refusal')}})
                db.commit()
            return {"status": "suspended", "why": "refusal"}
        decision.setdefault("kind", w["kind"]); decision.setdefault("gh", w["gh"])
        try:
            with session() as db:
                result = W.submit(db, w["table_id"], worker_id, decision, dossier_id)
                db.commit()
        except Exception as e:                 # 後端自身的錯：釋放租約、留事件，不吞掉
            log(f"[{worker_id}] {dossier_id} 後端錯誤：{type(e).__name__}: {str(e)[:300]}")
            with session() as db:
                W.release(db, w["table_id"], worker_id)
                from acies.service import events as EV
                EV.emit(db, w["table_id"], "後端錯誤", gh=w["gh"], dossier_id=dossier_id, error=f"{type(e).__name__}: {str(e)[:500]}")
                db.commit()
            return {"status": "error", "error": str(e)[:300], "dossier_id": dossier_id}
        log(f"[{worker_id}] {dossier_id} → {result['status']}")
        if result["status"] != "rejected":
            if result.get("finished"):
                try:                                       # 終局：自動跑判例審查
                    from acies.review import run as review_run
                    log(f"[{worker_id}] 終局，開始判例審查")
                    review_run.run_table(w["table_id"], log=log)
                except Exception as e:
                    log(f"[{worker_id}] 判例審查失敗：{type(e).__name__}: {str(e)[:300]}")
            return result
        w["errors"] = result["errors"]
        messages = messages + [{"role": "assistant", "content": info.get("text", json.dumps(decision, ensure_ascii=False))},
                               {"role": "user", "content": "上一份決定紀錄被退回，錯誤如下，請修正後重出完整一份：\n" +
                                "\n".join(f"- [{c}] {m}" for c, m in result["errors"])}]
    with session() as db:
        W.suspend(db, w["table_id"], worker_id, "audit_failed",
                  {"question": "決定紀錄連續兩次未通過驗證", "errors": result["errors"] if result else []})
        db.commit()
    return {"status": "suspended", "why": "validation"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--worker-id", default=f"referee-{uuid.uuid4().hex[:6]}")
    ap.add_argument("--poll", type=float, default=15.0)
    a = ap.parse_args(argv)
    pa = dossier.prefix_a()
    while True:
        try:
            r = run_one(a.worker_id, prefix_a=pa)
        except Exception as e:                    # 任何未預期的錯都不能讓工作者死掉
            print(f"[{a.worker_id}] 未預期錯誤：{type(e).__name__}: {str(e)[:300]}", flush=True)
            time.sleep(60); continue
        if a.once:
            print(json.dumps(r, ensure_ascii=False)); return 0
        if r is None:
            time.sleep(a.poll)
        elif r.get("status") == "error":         # 呼叫層失敗（額度、網路）：退避 5 分鐘再試，別每 15 秒撞一次
            print(f"[{a.worker_id}] 呼叫失敗，5 分鐘後再試：{r.get('info') or r.get('error')}", flush=True)
            time.sleep(300)


if __name__ == "__main__":
    sys.exit(main())
