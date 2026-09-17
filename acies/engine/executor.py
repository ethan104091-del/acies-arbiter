"""執行器：把一份決定紀錄變成 run_hour 的 resolve 閉包，並記錄每筆執行結果。

裁判在任何情況下不得直接寫狀態：這裡是唯一把決定變成狀態變化的地方。
一級動作依 seq 呼叫動詞；二級動作只能用原語白名單，且必須指向同一份紀錄裡的裁示，
落定時同時呼叫 arbiter.ruling() 讓事實紀錄與 v1 相容。
"""
from dataclasses import dataclass, field

import arbiter as ar

from . import verbs as V


class ExecutionError(Exception):
    pass


@dataclass
class Execution:
    """一小時的執行結果（決定紀錄的 execution 區段）。"""
    results: list = field(default_factory=list)     # 每筆動作：{seq, verb, applied, result, error}
    events: list = field(default_factory=list)      # 全知事件 [(target, text)]
    rulings_applied: list = field(default_factory=list)

    def to_dict(self):
        return {"results": self.results, "events": [list(e) for e in self.events],
                "rulings_applied": self.rulings_applied}


def _run_tier1(s, act, ex):
    verb = V.VERBS.get(act["verb"])
    if verb is None:
        raise ExecutionError(f"seq {act['seq']}：未知動詞 {act['verb']!r}")
    try:
        out = verb.fn(s, **act["args"])
    except (TypeError, KeyError, ValueError) as e:      # 參數形狀錯：算決定紀錄的錯，退回重出，不是後端當機
        raise ExecutionError(f"seq {act['seq']}：{act['verb']} 執行失敗：{type(e).__name__}: {e}")
    ex.events.extend(out.events)
    ex.results.append({"seq": act["seq"], "verb": act["verb"], "applied": out.applied, "result": out.result})


def _run_tier2(s, act, rulings_by_id, ex, gh):
    rid = act.get("ruling_id")
    r = rulings_by_id.get(rid)
    if r is None:
        raise ExecutionError(f"seq {act['seq']}：二級動作指向不存在的裁示 {rid!r}")
    applied_log = []
    for prim in act.get("applied", []):
        name, args = prim["primitive"], dict(prim.get("args", {}))
        bad = V.check_primitive_args(name, args)
        if bad:
            raise ExecutionError(f"seq {act['seq']}：{'；'.join(bad)}")
        res = V.PRIMITIVES[name](s, **args)
        applied_log.append({"primitive": name, "args": args, "result": _jsonable(res)})
    if rid not in {x["ruling_id"] for x in ex.rulings_applied}:
        ar.ruling(s, r["condition"] + " → " + r["effect"], r.get("basis", ""),
                  "；".join(f"{p['primitive']}{p['args']}" for p in applied_log),
                  precedent=bool(r.get("precedent")), gh=gh)
        ex.rulings_applied.append({"ruling_id": rid, "gh": gh})
    ex.events.append(("both", f"裁示 {rid}：{r['condition']} → {r['effect']}"))
    ex.results.append({"seq": act["seq"], "tier": 2, "ruling_id": rid, "applied": True, "result": applied_log})


def _jsonable(x):
    try:
        import json; json.dumps(x); return x
    except Exception:
        return repr(x)


def make_resolve(decision, execution=None):
    """回傳 (resolve, execution)。resolve(s, gh) 供 arbiter.run_hour 使用。"""
    ex = execution or Execution()
    actions = sorted(decision.get("actions", []), key=lambda a: a["seq"])
    rulings_by_id = {r["ruling_id"]: r for r in decision.get("rulings", [])}

    def resolve(s, gh):
        ex.events.clear()
        for act in actions:
            if act.get("tier", 1) == 1:
                _run_tier1(s, act, ex)
            else:
                _run_tier2(s, act, rulings_by_id, ex, gh)
        return list(ex.events)

    return resolve, ex


def execute_hour(s, decision, *, first_hour_of_tick=False, log=None):
    """在狀態 s 上執行一小時：必要時 begin_tick，然後 run_hour。回傳 (敘事行, Execution)。"""
    if first_hour_of_tick:
        ar.begin_tick(s)
    resolve, ex = make_resolve(decision)
    line = ar.run_hour(s, resolve, log)
    return line, ex
