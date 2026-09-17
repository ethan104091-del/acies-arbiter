"""投影與洩漏檢查：用 Run 7 九份快照＋終局狀態實測。

用法：.venv/bin/python -m pytest acies/tests/ 或 python3 acies/tests/test_projection.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import acies  # noqa: E402,F401  (設定 sys.path)
from acies.engine import projection, leakcheck, state_io  # noqa: E402
import arbiter as ar  # noqa: E402

RUN = ROOT / "runs" / "run7_openfield"
SNAPS = sorted(RUN.glob("snap_T*start.json")) + [RUN / "final_state.json"]


def _load(p):
    return state_io.loads(p.read_text())


def test_projection_no_leak():
    for p in SNAPS:
        s = _load(p)
        for side in projection.SIDES:
            v = projection.project(s, side)
            bad = projection.assert_no_leak(v, s, side)
            assert not bad, f"{p.name} {side}: {bad}"
            # 投影文字化後也不得洩漏（座標、代號）。本方自己寫的文字（常設命令、延遲命令）
            # 與已在事件當時過濾過的本方日誌，本來就會提到它當時知道的敵編隊，不算洩漏。
            cur = {k: x for k, x in v.items()
                   if k not in ("hour_log_side", "standing_orders", "pending_orders")}
            txt = json.dumps(cur, ensure_ascii=False)
            leaks = leakcheck.check_leak(s, txt, side, skip_history=False)
            assert not leaks, f"{p.name} {side}: {leaks}"


def test_projection_keeps_own_side_whole():
    s = _load(SNAPS[-1])
    for side in projection.SIDES:
        v = projection.project(s, side)
        own = {u for u, x in s["units"].items() if x["side"] == side}
        assert own <= set(v["units"])
        for uid in own:
            assert v["units"][uid] == s["units"][uid]


def test_god_view_is_whole_copy():
    s = _load(SNAPS[0])
    g = projection.project(s, "god")
    assert g == s and g is not s


def test_brief_md_passes_leakcheck():
    """引擎既有的單方戰報也必須通過移植後的洩漏檢查（與 dispatch.py 行為一致）。"""
    for p in SNAPS:
        s = _load(p)
        for side in projection.SIDES:
            assert not leakcheck.check_leak(s, ar.brief_md(s, side), side), p.name


def test_state_hash_stable():
    s = _load(SNAPS[3])
    assert state_io.state_hash(s) == state_io.state_hash(state_io.clone(s))
    t = state_io.clone(s); t["units"]["BLU-1"]["org"] -= 1
    assert state_io.state_hash(s) != state_io.state_hash(t)


def test_symmetry_check():
    ok, _ = leakcheck.check_symmetry("藍軍 BLU-1 allies", "紅軍 RED-1 axis")
    assert ok
    ok, why = leakcheck.check_symmetry("藍軍 a", "紅軍 b")
    assert not ok and "2 行" in why


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"✅ {name}")
