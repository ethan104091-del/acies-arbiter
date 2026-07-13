#!/usr/bin/env python3
"""Hour 級結算觸發監聽（GM 端）。

盯雙方的 hour_action_<side>.json。當「雙方都已對當前 global_hour 提交動作」，
或「某方離線超過 OFFLINE_SECS（零互動）」→ 印一行 RESOLVE 信號到 stdout，
讓裁判（Claude，透過 Monitor 工具或人工 tail）被叫醒、結算這 1 個 hour。

設計重點（公平性）：
  - 沒有任何一方能「手動跳過」對方 —— 跳過只由中立計時器（離線保護）觸發。
  - 離線判定 = 該方在 activity.json 的最後互動時間距今 > OFFLINE_SECS。
    任何帶 side 的請求（看戰場/問參謀/下令）都會刷新 activity → 只有「真的人不見了」才算離線。
  - for_global_hour 必須等於當前 global_hour，避免拿上一個 hour 的舊提交誤判到齊。

用法：
  python3 hourwatch.py          # 持續監聽，印 WAIT/RESOLVE 行
  python3 hourwatch.py --once   # 檢查一次就退出（給 Monitor until-loop 用）
被叫醒後，裁判讀雙方 hour_action_*.json + state.json，結算單一 hour、
推進時鐘(hourstate.advance_hour)、更新 fog/pending、寫雙方戰報，
然後刪除/清空 hour_action_*.json 等下一個 hour。
"""
import argparse
import json
import time
from pathlib import Path

import hourstate as hs

GAME_DIR = Path.home() / "war-game"
ACTIVITY_PATH = GAME_DIR / "activity.json"
OFFLINE_SECS = 600   # 10 分鐘零互動 → 離線保護自動視為「繼續」


def _read_action(side, expect_gh):
    """讀某方 hour_action，若 for_global_hour 對得上當前 hour 才算有效提交。"""
    p = GAME_DIR / f"hour_action_{side}.json"
    if not p.exists():
        return None
    try:
        a = json.loads(p.read_text())
    except Exception:
        return None
    fgh = a.get("for_global_hour")
    # for_global_hour 省略時寬鬆接受（client 可不帶）；有帶就必須相符
    if fgh is not None and fgh != expect_gh:
        return None
    return a


def _last_activity(side):
    try:
        d = json.loads(ACTIVITY_PATH.read_text())
        return d.get(side)
    except Exception:
        return None


def check_once():
    """回傳 (ready: bool, info: dict)。ready=True 表示可結算這個 hour。"""
    try:
        s = hs.load()
    except Exception as e:
        return False, {"reason": f"state 讀取失敗: {e}"}
    gh = s["global_hour"]
    now = time.time()

    status = {}
    for side in ("allies", "axis"):
        act = _read_action(side, gh)
        la = _last_activity(side)
        idle = (now - la) if la else None
        offline = (idle is not None and idle > OFFLINE_SECS)
        status[side] = {
            "submitted": act is not None,
            "action": (act or {}).get("action"),
            "idle_secs": round(idle) if idle is not None else None,
            "offline": offline,
        }

    def settled(side):
        st = status[side]
        return st["submitted"] or st["offline"]   # 提交了 或 離線(中立計時器)

    ready = settled("allies") and settled("axis")
    info = {"global_hour": gh, "tick": s["tick"], "hour_in_tick": s["hour_in_tick"],
            "game_time": s["game_time"], "status": status, "ready": ready}
    return ready, info


def fmt(info):
    gh = info["global_hour"]
    parts = []
    for side in ("allies", "axis"):
        st = info["status"][side]
        if st["offline"]:
            tag = "離線→視為繼續"
        elif st["submitted"]:
            tag = f"已提交({st['action']})"
        else:
            idle = st["idle_secs"]
            tag = f"等待中(閒置{idle}s)" if idle is not None else "等待中"
        parts.append(f"{side}:{tag}")
    return f"gh{gh} T{info['tick']}h{info['hour_in_tick']} {info['game_time']} | " + " | ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="檢查一次就退出")
    ap.add_argument("--interval", type=float, default=5.0, help="輪詢秒數")
    args = ap.parse_args()

    if args.once:
        ready, info = check_once()
        line = ("RESOLVE " if ready else "WAIT ") + fmt(info)
        print(line, flush=True)
        return 0 if ready else 1

    last_line = None
    announced_gh = None
    while True:
        ready, info = check_once()
        line = fmt(info)
        if line != last_line:               # 狀態變了才印（WAIT 進度）
            print("WAIT " + line, flush=True)
            last_line = line
        if ready and announced_gh != info["global_hour"]:
            print("RESOLVE " + fmt(info), flush=True)   # ← 叫醒裁判的信號
            announced_gh = info["global_hour"]          # 同一 hour 只喊一次
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
