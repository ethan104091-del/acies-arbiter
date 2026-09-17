"""端到端：建桌 → 兩席位送命令 → 窗口到齊 → 假裁判登記＋解算六小時 → 新 tick 簡報對稱 → 重放雜湊一致。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import acies  # noqa: E402,F401
from acies.referee import stub  # noqa: E402
from acies.engine import replay, state_io  # noqa: E402
from acies.db import models as M  # noqa: E402
from acies.db import session as S  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _run_worker(client, worker="w1", max_steps=20):
    """假裁判：反覆取件、決定、提交，直到沒工作。回傳提交結果清單。"""
    out = []
    for _ in range(max_steps):
        w = client.post("/work/claim", json={"worker_id": worker}).json()
        if w is None:
            break
        d = stub.decide(w)
        r = client.post(f"/work/{w['table_id']}/decision", json={"worker_id": worker, "decision": d}).json()
        assert r["status"] == "committed", r
        out.append((w["kind"], w["gh"], r))
    return out


def test_full_tick_with_stub_referee(client):
    r = client.post("/tables", json={"name": "測試桌"}).json()
    tid, tok = r["table_id"], r["tokens"]
    # 席位身分由權杖推得
    assert client.get("/me", headers=_h(tok["allies"])).json()["side"] == "allies"
    assert client.get("/me", headers=_h(tok["axis"])).json()["side"] == "axis"
    assert client.get("/me", headers={"Authorization": "Bearer nope"}).status_code == 401

    # 投影：藍軍看不到紅軍未偵獲編隊、看不到紅軍指揮所
    st = client.get(f"/tables/{tid}/state", headers=_h(tok["allies"])).json()
    pub = {"side", "short", "name", "type", "pos", "visibility_state", "hidden", "strength_approx", "fortification_bucket"}
    for uid, u in st["units"].items():
        if u["side"] == "axis":
            assert uid in st["fog_of_war"]["allies_spotted"] and set(u) <= pub, uid
    assert "axis" not in st["command"]
    # 觀戰席終局前只看計分
    ob = client.get(f"/tables/{tid}/state", headers=_h(tok["observer"])).json()
    assert set(ob) == {"global_hour", "score"}

    # T0 簡報：雙方共用段雜湊相同
    b_a = client.get(f"/tables/{tid}/brief", headers=_h(tok["allies"])).json()
    b_x = client.get(f"/tables/{tid}/brief", headers=_h(tok["axis"])).json()
    assert b_a["shared_hash"] == b_x["shared_hash"]
    assert "藍軍戰報" in b_a["text"] and "紅軍戰報" in b_x["text"]

    # 沒工作可取
    assert client.post("/work/claim", json={"worker_id": "w1"}).json() is None

    # 送命令：冪等鍵重送不加版本；雙方到齊
    o1 = client.put(f"/tables/{tid}/rounds/0/order", headers=_h(tok["allies"]),
                    json={"text": "## 命令\n1. [L2] BLU-1：向 (5,4) 戰備推進", "idempotency_key": "a1"}).json()
    o1b = client.put(f"/tables/{tid}/rounds/0/order", headers=_h(tok["allies"]),
                     json={"text": "改了", "idempotency_key": "a1"}).json()
    assert o1["version"] == o1b["version"] == 1 and o1["round_status"] == "窗口開啟"
    assert client.put(f"/tables/{tid}/rounds/1/order", headers=_h(tok["allies"]),
                      json={"text": "x", "idempotency_key": "z"}).status_code == 409
    o2 = client.put(f"/tables/{tid}/rounds/0/order", headers=_h(tok["axis"]),
                    json={"text": "## 命令\n1. [—] 維持原命令", "idempotency_key": "x1"}).json()
    assert o2["round_status"] == "雙方到齊"
    # 窗口關閉後不能再改
    assert client.put(f"/tables/{tid}/rounds/0/order", headers=_h(tok["allies"]),
                      json={"text": "晚了", "idempotency_key": "a2"}).status_code == 409

    # 假裁判：登記一次＋解算六小時 → T1 窗口開啟
    results = _run_worker(client)
    assert [k for k, _, _ in results] == ["register"] + ["resolve"] * 6
    summ = client.get(f"/tables/{tid}", headers=_h(tok["allies"])).json()
    assert summ["tick"] == 1 and summ["global_hour"] == 6 and summ["round"]["status"] == "窗口開啟"

    # T1 簡報已由落定流程發布，雙方共用段雜湊相同
    b1a = client.get(f"/tables/{tid}/brief", headers=_h(tok["allies"])).json()
    b1x = client.get(f"/tables/{tid}/brief", headers=_h(tok["axis"])).json()
    assert b1a["tick"] == 1 and b1a["shared_hash"] == b1x["shared_hash"]

    # 資料庫裡：七筆已落定決定、七份快照（gh0..6）、事件序列；重放雜湊逐小時一致
    with S.session() as db:
        decs = db.scalars(select(M.Decision).where(M.Decision.table_id == tid, M.Decision.committed.is_(True))
                          .order_by(M.Decision.gh, M.Decision.kind.desc())).all()
        snaps = {s.gh: s for s in db.scalars(select(M.Snapshot).where(M.Snapshot.table_id == tid)).all()}
        assert sorted(snaps) == list(range(0, 7))
        # 重放：登記後的 gh0 快照＋六份解算決定 → 逐小時雜湊
        resolves = [{**d.decision, "end_state_hash": d.end_state_hash} for d in decs if d.kind == "resolve"]
        _final, rows = replay.replay(snaps[0].state, resolves)
        assert all(ok for _, _, ok in rows), rows
        assert rows[-1][1] == snaps[6].state_hash
        kinds = [e.kind for e in db.scalars(select(M.Event).where(M.Event.table_id == tid).order_by(M.Event.id)).all()]
        assert kinds[:2] == ["窗口開啟", "建桌"] and "雙方到齊" in kinds and "回合落定" in kinds


def test_rejected_decision_and_lease(client):
    r = client.post("/tables", json={}).json()
    tid, tok = r["table_id"], r["tokens"]
    for sd, k in (("allies", "a"), ("axis", "x")):
        client.put(f"/tables/{tid}/rounds/0/order", headers=_h(tok[sd]), json={"text": "維持", "idempotency_key": k})
    w = client.post("/work/claim", json={"worker_id": "w1"}).json()
    assert w["kind"] == "register"
    # 別的工作者取不到（租約）
    assert client.post("/work/claim", json={"worker_id": "w2"}).json() is None
    # 無租約者提交 → 409
    assert client.post(f"/work/{tid}/decision", json={"worker_id": "w2", "decision": stub.decide(w)}).status_code == 409
    # 登記卷宗塞解算動詞 → 拒收，附錯誤
    bad = {"schema": "acies.HourDecision/1", "kind": "register", "gh": 0, "actions": [
        {"seq": 1, "tier": 1, "verb": "dig", "args": {"uid": "BLU-1"},
         "provenance": {"side": "allies", "clause_id": "藍T0-1", "quote": "x"}}]}
    res = client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": bad}).json()
    assert res["status"] == "rejected" and any(e[0] == "G10" for e in res["errors"])
    # 正確登記後，解算卷宗：條件指名陣營的裁示 → G2
    assert client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": stub.decide(w)}).json()["status"] == "committed"
    w2 = client.post("/work/claim", json={"worker_id": "w1"}).json()
    assert w2["kind"] == "resolve" and w2["attempt"] == 1
    d = stub.decide(w2)
    d["rulings"] = [{"ruling_id": "R1", "condition": "藍軍於夜間", "effect": "大概少一半"}]
    res = client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": d}).json()
    codes = {e[0] for e in res["errors"]}
    assert res["status"] == "rejected" and {"G2", "G3"} <= codes
    # 二級動作量級超門檻 → 掛起、桌轉待裁定、裁判席看得到、回覆後恢復
    d = stub.decide(w2)
    d["rulings"] = [{"ruling_id": "R2", "condition": "遭集中射擊之步兵", "effect": "人員 -3000"}]
    d["actions"].append({"seq": 99, "tier": 2, "ruling_id": "R2",
                         "applied": [{"primitive": "hurt", "args": {"uid": "RED-1", "personnel": 3000}}],
                         "provenance": {"side": "axis", "clause_id": "紅T0-1", "quote": "x"}})
    res = client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": d}).json()
    assert res["status"] == "suspended"
    assert client.get(f"/tables/{tid}", headers=_h(tok["axis"])).json()["status"] == "待人工裁定"
    assert client.get(f"/tables/{tid}/adjudications", headers=_h(tok["allies"])).status_code == 403
    items = client.get(f"/tables/{tid}/adjudications", headers=_h(tok["referee"])).json()
    assert items and items[0]["kind"] == "magnitude_threshold"
    ok = client.post(f"/tables/{tid}/adjudications/{items[0]['pending_id']}/answer", headers=_h(tok["referee"]),
                     json={"kind": "reject", "private_text": "量級過大，駁回"}).json()
    assert ok["ok"]
    assert client.get(f"/tables/{tid}", headers=_h(tok["axis"])).json()["status"] == "進行"
    w3 = client.post("/work/claim", json={"worker_id": "w1"}).json()
    assert w3["kind"] == "resolve" and w3["attempt"] == 3 and w3["adjudications"][0]["answer"]["kind"] == "reject"


def test_registration_ruling_reopens_window_once(client):
    r = client.post("/tables", json={}).json()
    tid, tok = r["table_id"], r["tokens"]
    for sd, k in (("allies", "a"), ("axis", "x")):
        client.put(f"/tables/{tid}/rounds/0/order", headers=_h(tok[sd]), json={"text": "維持", "idempotency_key": k})
    w = client.post("/work/claim", json={"worker_id": "w1"}).json()
    reg = {"schema": "acies.HourDecision/1", "kind": "register", "gh": 0, "actions": [
        {"seq": 1, "tier": 1, "verb": "register_clause",
         "args": {"side": "allies", "level": "L2", "text": "BLU-1 向 (5,4)", "unit_uids": ["BLU-1"]},
         "provenance": {"side": "allies", "clause_id": "藍T0-1", "quote": "x"}}],
        "rulings": [{"ruling_id": "R-T0-1", "condition": "同小時複數編隊射擊同一目標", "effect": "合併解算"}],
        "clause_updates": [{"clause_id": "藍T0-1", "side": "allies", "kind": "standing", "text": "BLU-1 向 (5,4)", "status": "pending"}]}
    res = client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": reg}).json()
    assert res["status"] == "committed" and res.get("reopened")
    summ = client.get(f"/tables/{tid}", headers=_h(tok["allies"])).json()
    assert summ["round"]["status"] == "裁示後重開" and summ["round"]["confirmed"] is False
    # 佇列裡已有一條登記的命令；沒工作可取（等雙方確認）
    st = client.get(f"/tables/{tid}/state", headers=_h(tok["allies"])).json()
    assert len(st["pending_orders"]) == 1
    assert client.post("/work/claim", json={"worker_id": "w1"}).json() is None
    # 雙方確認（一方改、一方不改）→ 到齊 → 重新登記：快照還原、條款清空
    client.put(f"/tables/{tid}/rounds/0/order", headers=_h(tok["allies"]), json={"text": "改了", "idempotency_key": "a2"})
    assert client.post(f"/tables/{tid}/rounds/0/confirm", headers=_h(tok["axis"])).json()["round_status"] == "雙方到齊"
    w2 = client.post("/work/claim", json={"worker_id": "w1"}).json()
    assert w2["kind"] == "register" and w2["reopened"] and w2["previous_register"]["rulings"]
    assert w2["orders"]["allies"] == "改了"
    reg2 = {**reg, "rulings": [{"ruling_id": "R-T0-2", "condition": "再一條", "effect": "e"}]}
    res2 = client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": reg2}).json()
    assert res2["status"] == "committed" and not res2.get("reopened")      # 每 tick 只重開一次
    st = client.get(f"/tables/{tid}/state", headers=_h(tok["allies"])).json()
    assert len(st["pending_orders"]) == 1                                   # 沒有重複登記
    assert len(client.get(f"/tables/{tid}/rulings", headers=_h(tok["axis"])).json()) == 2
    assert client.post("/work/claim", json={"worker_id": "w1"}).json()["kind"] == "resolve"


def test_pending_reemitted_each_hour_is_upserted(client):
    r = client.post("/tables", json={}).json()
    tid, tok = r["table_id"], r["tokens"]
    for sd, k in (("allies", "a"), ("axis", "x")):
        client.put(f"/tables/{tid}/rounds/0/order", headers=_h(tok[sd]), json={"text": "維持", "idempotency_key": k})
    w = client.post("/work/claim", json={"worker_id": "w1"}).json()
    pend = [{"pending_id": "P-T0-1", "kind": "unexpandable_clause", "side": "allies", "clause_id": "藍T0-應變1",
             "question": "「掃蕩」展不開", "material": False}]
    reg = {**stub.decide(w), "pending": pend}
    assert client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": reg}).json()["status"] == "committed"
    for _ in range(2):                      # 解算小時裁判重申同一件 → 不得撞唯一鍵
        w2 = client.post("/work/claim", json={"worker_id": "w1"}).json()
        d = {**stub.decide(w2), "pending": [{**pend[0], "question": "仍然展不開"}]}
        assert client.post(f"/work/{tid}/decision", json={"worker_id": "w1", "decision": d}).json()["status"] == "committed"
    items = client.get(f"/tables/{tid}/adjudications", headers=_h(tok["referee"])).json()
    assert len(items) == 1 and items[0]["body"]["question"] == "仍然展不開"
