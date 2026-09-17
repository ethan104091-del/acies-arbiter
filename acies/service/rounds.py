"""提交窗口與命令。"""
from sqlalchemy import select

from acies.db import models as M

from . import events, tables

SIDES = ("allies", "axis")


class WindowClosed(Exception):
    pass


def submit_order(db, t, side, tick, text, idempotency_key):
    """收命令原文。窗口關閉即拒；同冪等鍵重送回同一筆；否則版本 +1 並記為該方已確認。"""
    if tick != t.tick:
        raise WindowClosed(f"現在是 T{t.tick}，不能提交 T{tick} 的命令")
    r = tables.get_round(db, t.id, tick, lock=True)
    if r is None or r.status not in (M.RoundStatus.open, M.RoundStatus.reopened):
        raise WindowClosed(f"T{tick} 的提交窗口未開啟（{r.status.value if r else '無回合'}）")
    existing = db.scalar(select(M.Order).where(M.Order.table_id == t.id, M.Order.side == side,
                                               M.Order.idempotency_key == idempotency_key))
    if existing:
        return existing, r
    ver = (db.scalar(select(M.Order.version).where(M.Order.table_id == t.id, M.Order.tick == tick,
                                                    M.Order.side == side)
                     .order_by(M.Order.version.desc()).limit(1)) or 0) + 1
    o = M.Order(table_id=t.id, tick=tick, side=side, version=ver, idempotency_key=idempotency_key, text=text)
    db.add(o)
    _confirm(db, t, r, side, ver)
    events.emit(db, t.id, "命令送達", gh=t.global_hour, tick=tick, side=side, version=ver)
    db.flush()
    return o, r


def confirm_unchanged(db, t, side, tick):
    """裁示重開窗口後「確認不改」：與修改同等效力，沒有回應不算。"""
    r = tables.get_round(db, t.id, tick, lock=True)
    if r is None or r.status not in (M.RoundStatus.open, M.RoundStatus.reopened):
        raise WindowClosed("窗口未開啟")
    o = latest_order(db, t.id, tick, side)
    if o is None:
        raise WindowClosed("尚未提交過命令，不能只確認")
    _confirm(db, t, r, side, o.version)
    events.emit(db, t.id, "確認不改", gh=t.global_hour, tick=tick, side=side)
    db.flush()
    return r


def _confirm(db, t, r, side, version):
    c = dict(r.confirmed or {}); c[side] = version; r.confirmed = c
    if all(c.get(sd) for sd in SIDES):
        r.status = M.RoundStatus.ready
        events.emit(db, t.id, "雙方到齊", gh=t.global_hour, tick=r.tick)


def latest_order(db, table_id, tick, side):
    return db.scalar(select(M.Order).where(M.Order.table_id == table_id, M.Order.tick == tick,
                                           M.Order.side == side).order_by(M.Order.version.desc()).limit(1))


def current_orders(db, table_id, tick):
    return {sd: latest_order(db, table_id, tick, sd) for sd in SIDES}


def reopen_window(db, t, tick, why):
    """tick 內公告新通則裁示 → 窗口對雙方重開（command_v2 §4），雙方都要再確認。"""
    r = tables.get_round(db, t.id, tick)
    r.status = M.RoundStatus.reopened
    r.confirmed = {"allies": None, "axis": None}
    r.reopen_count = (r.reopen_count or 0) + 1
    import datetime as _dt
    r.window_opened_at = _dt.datetime.now(_dt.timezone.utc)
    events.emit(db, t.id, "窗口重開", gh=t.global_hour, tick=tick, why=why)
    return r
