#!/usr/bin/env python3
"""多人 1v1 對戰 server（跑在「你的 Mac」= GM 端）。

權威 state.json 在這台。對手（遠端）透過 client.py 連進來：
  - 拉自己視角的 state（server 端已過濾戰爭迷霧，敵方內部資料不外洩）
  - 拉自己的戰報
  - 推送自己的命令 → 存成 order_<side>.json 供 GM 解算

GM（你 + Claude）照常編輯 state.json / 寫 report_<side>.md，server 即時讀最新檔。

啟動：
    python3 ~/war-game/server.py                 # 預設 port 8000，需 token
    python3 ~/war-game/server.py --port 8000 --token 自訂密語
對外（遠端對手）：另開一個終端機跑 Cloudflare Tunnel：
    cloudflared tunnel --url http://localhost:8000
    → 會給一個 https://xxxx.trycloudflare.com 網址，連同 token 給對手。

安全：所有端點需 ?token=... 比對；過濾在 server 端做，對手抓封包也看不到敵情。
"""
import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import mapcore as mc
import advisor   # AI 參謀（Claude API）；缺 SDK/key 時 advisor.available() 為 False
import hourstate as hs   # hour 級回合 + 延遲命令佇列

GAME_DIR = Path.home() / "war-game"
STATE_PATH = GAME_DIR / "state.json"


def hour_action_path(side):
    return GAME_DIR / f"hour_action_{side}.json"


ACTIVITY_PATH = GAME_DIR / "activity.json"


def mark_activity(side):
    """記錄某方最後互動時間（離線保護計時器用）。任何帶 side 的請求都算『人還在』。"""
    import time
    try:
        data = json.loads(ACTIVITY_PATH.read_text()) if ACTIVITY_PATH.exists() else {}
    except Exception:
        data = {}
    data[side] = time.time()
    try:
        ACTIVITY_PATH.write_text(json.dumps(data))
    except OSError:
        pass

CONFIG = {"token": None, "report": {"allies": GAME_DIR / "report_allies.md",
                                     "axis": GAME_DIR / "report_axis.md"}}


def order_path(side):
    return GAME_DIR / f"order_{side}.json"


def _valid_side(side):
    return side in ("allies", "axis")


class Handler(BaseHTTPRequestHandler):
    server_version = "WarGameMP/1.0"

    # ── 工具 ────────────────────────────────────────────────────
    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _auth_ok(self, qs):
        if CONFIG["token"] is None:
            return True
        return qs.get("token", [None])[0] == CONFIG["token"]

    def log_message(self, fmt, *args):
        # 簡潔 log（含路徑），不洩 token
        path = self.path.split("?")[0]
        print(f"  [{self.address_string()}] {self.command} {path} — {args[1] if len(args)>1 else ''}")

    def _touch(self, qs):
        """任何帶 side 的請求 → 記錄該方活躍（看戰場/問參謀都算人還在）。"""
        side = qs.get("side", [None])[0]
        if _valid_side(side):
            mark_activity(side)

    # ── GET：拉 state / 戰報 / 健康檢查 ──────────────────────────
    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if not self._auth_ok(qs):
            return self._json(403, {"error": "bad or missing token"})
        self._touch(qs)

        if u.path == "/ping":
            return self._json(200, {"ok": True, "game": "Operation Black Tide"})

        if u.path == "/state":
            side = qs.get("side", ["axis"])[0]
            if not _valid_side(side):
                return self._json(400, {"error": "side must be allies/axis"})
            try:
                state = json.loads(STATE_PATH.read_text())
            except (OSError, json.JSONDecodeError) as e:
                return self._json(500, {"error": f"state read failed: {e}"})
            return self._json(200, mc.filter_state_for(state, side))

        if u.path == "/report":
            side = qs.get("side", ["axis"])[0]
            if not _valid_side(side):
                return self._json(400, {"error": "side must be allies/axis"})
            rp = CONFIG["report"][side]
            text = rp.read_text() if rp.exists() else "（尚無戰報）"
            return self._send(200, text, ctype="text/plain")

        if u.path == "/advisor_status":
            return self._json(200, {"available": advisor.available(),
                                    "status": advisor.status()})

        if u.path == "/pending":
            # 看自己的延遲命令佇列（含生效倒數）。敵方的不可見。
            side = qs.get("side", ["axis"])[0]
            if not _valid_side(side):
                return self._json(400, {"error": "side must be allies/axis"})
            try:
                s = hs.load()
            except (OSError, json.JSONDecodeError) as e:
                return self._json(500, {"error": f"state read failed: {e}"})
            return self._json(200, {
                "global_hour": s["global_hour"], "tick": s["tick"],
                "hour_in_tick": s["hour_in_tick"], "phase": s.get("phase"),
                "game_time": s["game_time"],
                "standing_order": s.get("standing_orders", {}).get(side, ""),
                "pending": hs.pending_for(s, side),
            })

        return self._json(404, {"error": "unknown endpoint"})

    # ── POST：對手交命令 ────────────────────────────────────────
    def do_POST(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if not self._auth_ok(qs):
            return self._json(403, {"error": "bad or missing token"})
        self._touch(qs)

        if u.path == "/order":
            side = qs.get("side", ["axis"])[0]
            if not _valid_side(side):
                return self._json(400, {"error": "side must be allies/axis"})
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                order = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as e:
                return self._json(400, {"error": f"bad json: {e}"})
            # 存檔供 GM 解算（含時間欄位由 client 帶或留空）
            op = order_path(side)
            op.write_text(json.dumps(order, ensure_ascii=False, indent=2))
            print(f"  ★ 收到 {side} 命令 → {op.name}")
            return self._json(200, {"ok": True, "saved": op.name})

        if u.path == "/hour_action":
            # 對手提交「本 hour 動作」：下臨時令(L1/L2/L3) 或 繼續。
            # 存成 hour_action_<side>.json 供監聽偵測雙方到齊 → 叫醒裁判結算。
            side = qs.get("side", ["axis"])[0]
            if not _valid_side(side):
                return self._json(400, {"error": "side must be allies/axis"})
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                act = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as e:
                return self._json(400, {"error": f"bad json: {e}"})
            action = act.get("action")
            if action not in ("order", "continue", "standing"):
                return self._json(400, {"error": "action 須為 order/continue/standing"})
            if action == "order":
                lvl = (act.get("order") or {}).get("level")
                if lvl not in ("L1", "L2", "L3"):
                    return self._json(400, {"error": "order.level 須為 L1/L2/L3"})
                if not (act.get("order") or {}).get("text", "").strip():
                    return self._json(400, {"error": "order.text 不可空"})
            # 蓋上提交時間（離線保護計時器用）；存檔
            act["side"] = side
            ap = hour_action_path(side)
            ap.write_text(json.dumps(act, ensure_ascii=False, indent=2))
            print(f"  ⏱ {side} hour動作：{action} "
                  f"{(act.get('order') or {}).get('text','')[:30]}")
            return self._json(200, {"ok": True, "saved": ap.name})

        if u.path == "/advise":
            # 對手向「自己的」AI 參謀提問。server 端用該方過濾視角即時調 Claude，
            # 對手永遠拿不到對方底牌（advisor 只吃 filter_state_for(state, side)）。
            side = qs.get("side", ["axis"])[0]
            if not _valid_side(side):
                return self._json(400, {"error": "side must be allies/axis"})
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as e:
                return self._json(400, {"error": f"bad json: {e}"})
            question = (payload.get("question") or "").strip()
            if not question:
                return self._json(400, {"error": "question 不可空"})
            print(f"  ☎ {side} 參謀提問：{question[:40]}…")
            ok, answer = advisor.ask(side, question)
            return self._json(200 if ok else 503, {"ok": ok, "answer": answer})

        return self._json(404, {"error": "unknown endpoint"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--token", default=None,
                    help="連線密語；省略則自動產生一組")
    ap.add_argument("--no-token", action="store_true", help="不設 token（僅限同網路測試）")
    args = ap.parse_args()

    if args.no_token:
        CONFIG["token"] = None
    else:
        CONFIG["token"] = args.token or secrets.token_urlsafe(8)

    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print("=" * 56)
    print("  War Game 多人 server — Operation Black Tide")
    print("=" * 56)
    print(f"  本機監聽    : http://0.0.0.0:{args.port}")
    print(f"  連線 token  : {CONFIG['token'] or '(無，僅同網路)'}")
    print(f"  state 權威檔: {STATE_PATH}")
    print(f"  AI 參謀     : {advisor.status()}")
    print()
    print("  遠端對手連線步驟：")
    print("   1) 另開終端機： cloudflared tunnel --url http://localhost:%d" % args.port)
    print("   2) 把它給的 https://xxxx.trycloudflare.com 網址 + token 給對手")
    print("   3) 對手執行： python3 client.py --url <網址> --token <token> --side axis")
    print()
    print("  端點： GET /state?side= ｜ /report?side= ｜ /pending?side= ｜ /advisor_status ｜ /ping")
    print("         POST /order?side= ｜ /hour_action?side= ｜ /advise?side=（AI 參謀）")
    print("  Ctrl-C 結束。")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nserver 結束。")
        srv.shutdown()


if __name__ == "__main__":
    main()
