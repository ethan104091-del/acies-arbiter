"""重放器：小時起始快照 ＋ 已落定的決定紀錄序列 → 逐小時重建 → 雜湊比對。

重放 ＝ 引擎 ＋ 已落定的決定。只吃決定紀錄的 actions（含二級 applied），
裁判的文字輸出不參與。落定時存下的 end_state_hash 必須逐小時相等。
"""
from . import executor, state_io


def replay(snapshot, decisions, *, tick_hours=6):
    """snapshot：起始狀態（dict）；decisions：依 gh 排序的決定紀錄清單，
    每筆須含 gh，可含 end_state_hash。回傳 [(gh, hash, 是否相符或 None)]。"""
    s = state_io.clone(snapshot)
    out = []
    for d in decisions:
        gh = d["gh"]
        if s["global_hour"] != gh:
            raise ValueError(f"重放序列斷裂：狀態在 gh{s['global_hour']}，決定紀錄是 gh{gh}")
        executor.execute_hour(s, d, first_hour_of_tick=(gh % tick_hours == 0))
        h = state_io.state_hash(s)
        expect = d.get("end_state_hash")
        out.append((gh, h, None if expect is None else h == expect))
    return s, out
