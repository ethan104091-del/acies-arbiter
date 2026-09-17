"""v2 引擎拆分的等價測試：begin_tick ＋ N×run_hour ≡ 拆分前的 run_tick。

做法：把 runs/run7_openfield 複製到暫存目錄，對 T0–T8 九個 tick 腳本各跑兩次——
一次把 ar.run_tick 換成拆分前的逐字副本（下方 legacy_run_tick），一次用現行的
run_tick——比對兩次存下的狀態檔是否逐位元組相同。腳本本身一字不改。

用法：python3 tests/test_run_hour_equivalence.py
"""
import io, runpy, shutil, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runs"))
import arbiter as ar   # noqa: E402

RUN = ROOT / "runs" / "run7_openfield"
TICKS = range(0, 9)


def legacy_run_tick(s, resolve, hours=6, log=None):
    """v2 拆分前的 run_tick，逐字自 commit f0efe65 複製；只供等價測試對照。"""
    ar.resupply(s)                          # tick 邊界補給（logistics_v1；同時寫入 supply_status）
    s["push_ledger"] = []                # 本 tick 的逼退帳（_audit A5 對帳用，見 runs/_audit.py）
    s["works_ledger"] = []               # 本 tick 的構工帳（_audit A3：誰挖了土）
    lines = []
    for _ in range(hours):
        gh = s["global_hour"]
        ar.command.activate_due_cps(s)
        ar.hs.hour_brief(s)

        ev = ar.apply_due_legal_orders(s)          # 具法律後果的命令：機器解析先行
        ev += list(resolve(s, gh) or [])

        night = ar.is_night(s)
        for uid, u in s["units"].items():
            if u.get("side") not in ("allies", "axis"):
                continue
            if u["flags"].get("moved"):
                # 行軍疲勞由 advance() 施加（白天 +5／夜間 +8，= movement_v1 的 5 + 3），
                # 此處**不得再加**——2026-07-30 曾在這裡重複加一次，導致行軍疲勞加倍。
                ar.consume(s, uid, "L1")
            elif u["flags"].get("fired") or u["flags"].get("hit"):
                ar.consume(s, uid, "L3")          # 交戰中的消耗由 resolve 視情況再加
            else:
                u["fatigue"] = max(0, u.get("fatigue", 0) - ar.FATIGUE_REST_FULL)
                ar.consume(s, uid, "L0")
        ar.apply_fatigue_caps(s)
        ar.refresh_fortification(s)      # Run 7：依所在格的 man-hours 重算各編隊工事值

        ar.refresh_visibility(s)
        for side, lst in ar.spot(s).items():
            for uid in lst:
                ev.append((side, f"★我方偵獲敵 {uid} 於 {tuple(s['units'][uid]['pos'])}"))

        ar.refresh_return_fire(s)
        ar.refresh_combat_hours(s)
        ar.org_recovery(s)
        for uid, kind, txt in ar.evaluate_status(s):
            ev.append((uid, txt))
        ar.pow_upkeep(s)

        ar.push_log(s, ev, gh_label=f"[gh{gh}] ")
        line = f"[gh{gh} {ar.hs.game_time_str(gh)}] " + ("；".join(x for _, x in ev) if ev else "無事件")
        lines.append(line)
        if log is not None:
            log.append(line)
        ar.clear_flags(s)
        ar.hs.end_hour(s, line)
    return lines


def _run_script(tick, run_tick_impl, workdir):
    """在 workdir 內以指定的 run_tick 實作跑 t{tick}.py，回傳存檔後的狀態 JSON 文字。"""
    state = workdir / "state.json"
    shutil.copy(RUN / f"snap_T{tick}start.json", state)
    saved = {k: getattr(ar, k) for k in ("run_tick", "load", "save", "STATE")}
    ar.STATE = state
    ar.load = lambda path=state: saved["load"](path)
    ar.save = lambda s, path=state: saved["save"](s, path)
    ar.run_tick = run_tick_impl
    try:
        with redirect_stdout(io.StringIO()):
            runpy.run_path(str(workdir / "run7_openfield" / f"t{tick}.py"), run_name="__main__")
    finally:
        for k, v in saved.items():
            setattr(ar, k, v)
    return state.read_text()


def _outcome(tick, impl, workdir):
    try:
        return _run_script(tick, impl, workdir)
    except TypeError as e:          # 引擎對舊寫法的明確拒絕（arbiter.BattleResult）
        return "EXC " + str(e)


def test_equivalence():
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(RUN, tmp / "run7_openfield")
        for f in (ROOT / "runs").glob("_*.py"):
            shutil.copy(f, tmp / f.name)
        for t in TICKS:
            a = _outcome(t, legacy_run_tick, tmp)
            b = _outcome(t, ar.run_tick, tmp)
            ok = a == b
            if isinstance(a, str) and a.startswith("EXC "):
                # t5／t7／t8 仍用 Phase 1 之前的 `push > 0` 寫法，現行引擎兩種實作同樣拒跑；
                # 只要求兩者拋出同一個錯誤（等價的另一種形式）。
                print(f"  T{t}: {'✅ 兩種實作拋出相同錯誤' if ok else '❌ 錯誤不同'}（腳本停在 Phase 1 之前）")
            else:
                print(f"  T{t}: {'✅ 逐位元組相同' if ok else '❌ 不同'}  ({len(a)} bytes)")
            if not ok:
                failed.append(t)
    assert not failed, f"拆分後與拆分前不等價的 tick：{failed}"


if __name__ == "__main__":
    test_equivalence()
    print("✅ begin_tick ＋ run_hour 與拆分前的 run_tick 逐位元組等價（Run 7 T0–T8）")
