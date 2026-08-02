#!/usr/bin/env python3
"""監看紅軍指揮部資料夾，命令檔寫完就發一則事件（給裁判用，雙方皆不得讀）。

「寫完」的判準是**內容雜湊穩定 STABLE 秒**——codex 可能分次寫入，
若一有變動就報，會在同一次編輯中噴出好幾則。穩定後才報，一次編輯一則事件。

只監看紅軍。藍軍是 agent，完成時會自己回報。
"""
import hashlib
import json
import sys
import time
from pathlib import Path

RED = Path.home() / "Desktop" / "料鋒_Run5_紅軍指揮部"
# 已通知過的雜湊持久化：否則重啟監看時，空窗期內發生的變動會被當成基準而吞掉
SEEN_FILE = Path(__file__).resolve().parent / "_watch_seen.json"
WATCH_GLOBS = ("命令_T*.md", "紅軍作戰日誌.md")
POLL = 5.0        # 本地檔案，5 秒一輪
STABLE = 15.0     # 雜湊連續 15 秒不變才視為寫完
# 空白樣板的判準：意圖區塊的佔位文字。原本用開頭引言「填完存檔即可」，
# 但指揮官填寫時常保留那句引言 → 已填寫的檔案被誤判為空白樣板（2026-07-30 發現）。
TEMPLATE_MARK = "（一到三句：這個 tick 你想達成什麼"


def digest(p):
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def scan():
    out = {}
    for g in WATCH_GLOBS:
        for p in sorted(RED.glob(g)):
            d = digest(p)
            if d:
                out[p.name] = d
    return out


def load_seen():
    try:
        return json.loads(SEEN_FILE.read_text())
    except (OSError, ValueError):
        return None


def save_seen(seen):
    try:
        SEEN_FILE.write_text(json.dumps(seen))
    except OSError:
        pass


def main():
    # 首次啟動：以現況為基準。重啟：沿用上次的紀錄，補報空窗期的變動。
    seen = load_seen()
    if seen is None:
        seen = scan()
        save_seen(seen)
    pending = {}                        # name -> (hash, 首次觀察到的時刻)
    while True:
        time.sleep(POLL)
        try:
            cur = scan()
        except OSError:
            continue
        now = time.time()

        for name, h in cur.items():
            if seen.get(name) == h:
                pending.pop(name, None)
                continue
            prev = pending.get(name)
            if prev is None or prev[0] != h:
                pending[name] = (h, now)          # 還在寫，重新計時
                continue
            if now - prev[1] >= STABLE:
                p = RED / name
                try:
                    txt = p.read_text()
                except OSError:
                    continue
                seen[name] = h
                pending.pop(name, None)
                if TEMPLATE_MARK in txt:
                    save_seen(seen)
                    continue          # 裁判自己放的空白樣板：記錄但不通知
                save_seen(seen)
                print(f"[紅軍] {name} 寫入完成（{len(txt)} 字，已填寫）", flush=True)

        for name in list(seen):
            if name not in cur:
                print(f"[紅軍] {name} 已被刪除", flush=True)
                seen.pop(name, None)


if __name__ == "__main__":
    if not RED.is_dir():
        print(f"[監看錯誤] 找不到 {RED}", flush=True)
        sys.exit(1)
    try:
        main()
    except KeyboardInterrupt:
        pass
