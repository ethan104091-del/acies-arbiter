"""指揮部橋接：把某桌某方的簡報寫進資料夾、把資料夾裡的命令檔送進後端。給在該資料夾裡工作的 AI 指揮官用。

用法：.venv/bin/python -m acies.tools.hq_bridge --table <桌號> --token <該方權杖> --dir <資料夾> [--poll 20]
資料夾內：00_讀我.md、指揮官手冊.md、本回簡報.md（每 tick 覆寫）、_歷史簡報_T{n}.md、命令_T{n}.md（指揮官寫）、_狀態.md
命令檔存檔即送出（同內容不重送）；窗口因裁示重開時，改檔即為修改、建立空檔 確認_T{n} 即為確認不改。
"""
import argparse
import hashlib
import importlib.util
import json
import time
import urllib.request
from pathlib import Path

import acies

ZH = {"allies": "藍", "axis": "紅"}

README = """# {ZH}軍指揮部 — 桌 {table}

## 每個 tick 你只需要讀一個檔案、寫一個檔案

1. 讀 `本回簡報.md`（本 tick 的戰報、徵候、裁示全集、命令樣板）。
2. 把命令寫進 `命令_T{{n}}.md`（n 為本回簡報標題上的 tick），**不要改四個 ## 標題**。存檔即送出。
3. `_狀態.md` 會顯示送出結果與窗口狀態。若窗口因裁示重開，改檔＝修改；不改就建立空檔 `確認_T{{n}}`。

## 硬性限制
- 只能讀寫**本目錄**內的檔案。嚴禁讀取引擎目錄、對手的資料夾、或裁判的資料。
- 你對敵情的全部認知只能來自 `本回簡報.md`。
- 規則細節在 `指揮官手冊.md`；規則沒寫的動作你一律得嘗試，裁判不得以「規則沒寫」拒絕。
"""


def _api(base, token, method, path, body=None):
    req = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"detail": str(e)}


def handbook(side):
    p = acies.ROOT / "runs" / "run8_openfield" / "gen_handbook.py"
    spec = importlib.util.spec_from_file_location("gen_handbook_run8", p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.render(mod.TPL, side)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--table", required=True); ap.add_argument("--token", required=True)
    ap.add_argument("--dir", required=True); ap.add_argument("--poll", type=float, default=20)
    a = ap.parse_args()
    d = Path(a.dir).expanduser(); d.mkdir(parents=True, exist_ok=True)
    st, me = _api(a.base, a.token, "GET", "/me")
    side = me["side"]
    (d / "00_讀我.md").write_text(README.format(ZH=ZH[side], table=a.table[:8]))
    (d / "指揮官手冊.md").write_text(handbook(side))
    sent = {}      # tick -> 已送內容雜湊
    confirmed = set()
    seen_brief = {}
    while True:
        st, summ = _api(a.base, a.token, "GET", f"/tables/{a.table}")
        if st != 200:
            time.sleep(a.poll); continue
        tick = summ["tick"]
        # 簡報（每輪都查；共用段雜湊變了＝有新裁示或答覆，重寫）
        st, b = _api(a.base, a.token, "GET", f"/tables/{a.table}/brief?tick={tick}")
        brief_note = ""
        if st == 200 and seen_brief.get(tick) != b["shared_hash"]:
            (d / "本回簡報.md").write_text(b["text"])
            (d / f"_歷史簡報_T{tick}.md").write_text(b["text"])
            if seen_brief.get(tick) is not None:
                brief_note = f"本回簡報.md 已更新（新裁示或答覆）。窗口重開：改 命令_T{tick}.md 即為修改；不改請建立空檔 確認_T{tick}。"
            seen_brief[tick] = b["shared_hash"]
        # 命令
        f = d / f"命令_T{tick}.md"
        rs = summ.get("round") or {}
        note = ""
        if f.exists():
            txt = f.read_text()
            h = hashlib.sha256(txt.encode()).hexdigest()[:16]
            if sent.get(tick) != h and txt.strip():
                st, r = _api(a.base, a.token, "PUT", f"/tables/{a.table}/rounds/{tick}/order", {"text": txt, "idempotency_key": h})
                if st == 200:
                    sent[tick] = h; note = f"命令_T{tick}.md 已送出（第 {r['version']} 版）；窗口：{r['round_status']}"
                else:
                    note = f"命令_T{tick}.md 未送出：{r.get('detail')}"
        cf = d / f"確認_T{tick}"
        if cf.exists() and (tick, cf.stat().st_mtime) not in confirmed and rs.get("status") == "裁示後重開":
            st, r = _api(a.base, a.token, "POST", f"/tables/{a.table}/rounds/{tick}/confirm")
            confirmed.add((tick, cf.stat().st_mtime)); note = f"已確認不改：{r.get('round_status') or r.get('detail')}"
        if brief_note:
            note = (note + "；" if note else "") + brief_note
        status = (f"# 狀態（{time.strftime('%H:%M:%S')}）\n\n桌 {a.table[:8]}　{ZH[side]}軍　Tick {tick}/{summ['max_ticks']}　gh{summ['global_hour']}　"
                  f"{summ['status']}　窗口：{rs.get('status')}　你已確認：{rs.get('confirmed')}\n\n"
                  + (f"{note}\n" if note else "") + (f"\n終局：{summ['verdict']}\n" if summ.get("verdict") else ""))
        (d / "_狀態.md").write_text(status)
        if note:
            print(f"[{ZH[side]}] {note}", flush=True)
        if summ["status"] == "終局":
            print(f"[{ZH[side]}] 終局：{summ.get('verdict')}"); return
        time.sleep(a.poll)


if __name__ == "__main__":
    main()
