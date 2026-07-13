#!/usr/bin/env python3
"""多人 1v1 對戰 client（跑在「對手的電腦」= 遠端玩家端）。

連到 GM 端的 server（直連或經 Cloudflare Tunnel 網址），做三件事：
  v  view   — 拉自己視角的 state，用 mapcore 渲染地圖（戰爭迷霧已由 server 過濾）
  r  report — 看自己的最新戰報
  o  order  — 編輯命令並送出（intent + 主計畫 + 應變條件，存到 GM 端）

對手只需要：Python 3 + rich + wcwidth + 這個 client.py + mapcore.py（渲染共用）。
不需要 state.json / server.py。

用法：
    python3 client.py --url https://xxxx.trycloudflare.com --token <token> --side axis
    （同網路測試： --url http://192.168.x.x:8000 ）
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
from urllib.parse import urlencode

from rich.console import Console

import mapcore as mc

console = Console()


class Client:
    def __init__(self, url, token, side):
        self.base = url.rstrip("/")
        self.token = token
        self.side = side

    def _get(self, path, **params):
        params["token"] = self.token
        if "side" not in params:
            params["side"] = self.side
        full = f"{self.base}{path}?{urlencode(params)}"
        with urllib.request.urlopen(full, timeout=15) as r:
            return r.read().decode("utf-8")

    def _post(self, path, payload, **params):
        params["token"] = self.token
        params.setdefault("side", self.side)
        full = f"{self.base}{path}?{urlencode(params)}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(full, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8")

    def ping(self):
        try:
            d = json.loads(self._get("/ping"))
            return d.get("ok", False)
        except Exception:
            return False

    def view(self):
        try:
            state = json.loads(self._get("/state"))
        except urllib.error.HTTPError as e:
            console.print(f"[red]拉取 state 失敗：{e.code} {e.reason}[/]")
            if e.code == 403:
                console.print("[yellow]token 不對？檢查 --token[/]")
            return
        except Exception as e:
            console.print(f"[red]連線失敗：{e}[/]")
            return
        side_zh = "盟軍 III Corps" if self.side == "allies" else "德軍 Panzergruppe Hartmann"
        console.print(f"\n[bold]你的視角：{side_zh}[/]  "
                      f"回合 {state.get('tick','?')}/{state.get('max_ticks','?')}  "
                      f"⏱ {state.get('game_time','?')}  ☁ {state.get('weather','?')}")
        # server 已過濾，這裡用對應 viewer_side 渲染（敵方只剩公開欄，仍能畫位置）
        console.print(mc.render_map(state, grid=True, viewer_side=self.side,
                                    annot={"annotations": [], "headings": {}}))
        # 文字列出自己部隊與已偵獲敵軍
        own, enemy = [], []
        for uid, u in state["units"].items():
            if u["side"] == self.side:
                own.append(u)
            else:
                enemy.append(u)
        console.print("[bold cyan]你的部隊：[/]")
        for u in own:
            console.print(f"  {u['short']:5} {mc.TYPE_GLYPH.get(u['type'],'')} "
                          f"@({u['pos'][0]},{u['pos'][1]}) 兵{u.get('strength','?')} "
                          f"組{u.get('org','?')} 疲{u.get('fatigue',0)}")
        console.print("[bold red]偵獲敵軍：[/]" if enemy else "[dim]（未偵獲敵軍）[/]")
        for u in enemy:
            console.print(f"  {u['short']:5} {mc.TYPE_GLYPH.get(u['type'],'')} "
                          f"@({u['pos'][0]},{u['pos'][1]}) 概略兵力~{u.get('strength_approx','?')}")

    def report(self):
        try:
            text = self._get("/report")
        except Exception as e:
            console.print(f"[red]拉取戰報失敗：{e}[/]")
            return
        console.print("\n[bold yellow]═══ 最新戰報 ═══[/]")
        console.print(text)

    def order(self):
        console.print("\n[bold]下達本回合命令[/]（直接打字，空行結束每段）：")
        intent = input("【意圖】(1-2句)：").strip()
        console.print("【主計畫】每行一條（如 '17SS：守 Saint-Vivien'），空行結束：")
        plan = []
        while True:
            line = input("  ").strip()
            if not line:
                break
            plan.append(line)
        console.print("【應變條件】每行一條（如 '若3AD越中橋→引爆預埋'），空行結束：")
        conting = []
        while True:
            line = input("  ").strip()
            if not line:
                break
            conting.append(line)
        order = {"side": self.side, "intent": intent,
                 "plan": plan, "contingencies": conting}
        console.print("\n[bold]即將送出：[/]")
        console.print_json(json.dumps(order, ensure_ascii=False))
        if input("確認送出？(y/n)：").strip().lower() != "y":
            console.print("[yellow]已取消。[/]")
            return
        try:
            resp = json.loads(self._post("/order", order))
            console.print(f"[green]✅ 主令已送達 GM（{resp.get('saved')}）。[/]")
        except Exception as e:
            console.print(f"[red]送出失敗：{e}[/]")

    def pending(self):
        """看自己的延遲命令佇列 + 當前時間/主令。"""
        try:
            d = json.loads(self._get("/pending"))
        except Exception as e:
            console.print(f"[red]拉取失敗：{e}[/]")
            return
        console.print(f"\n[bold]Tick {d['tick']} / 第 {d['hour_in_tick']} 小時"
                      f"（global hour {d['global_hour']}）  ⏱ {d['game_time']}[/]")
        console.print(f"[dim]你的主令：{d.get('standing_order') or '（未下）'}[/]")
        pend = d.get("pending", [])
        if not pend:
            console.print("[dim]延遲命令佇列：空[/]")
        else:
            console.print("[bold]延遲命令佇列（尚未生效）：[/]")
            for o in pend:
                console.print(f"  [{o['level']}] {o['text']} "
                              f"[yellow]（{o['hours_until_effective']} 小時後生效）[/]")

    def hour_action(self):
        """提交本 hour 動作：下臨時令(L1/L2/L3) 或 繼續。"""
        console.print("\n[bold]本小時動作：[/] [cyan]1[/]下臨時令  [cyan]2[/]繼續(沿用既有令)")
        choice = input("選 1/2：").strip()
        if choice == "2":
            try:
                resp = json.loads(self._post("/hour_action", {"action": "continue"}))
                console.print(f"[green]✅ 已提交「繼續」。等待對手與裁判。[/]")
            except Exception as e:
                console.print(f"[red]送出失敗：{e}[/]")
            return
        if choice != "1":
            console.print("[yellow]已取消。[/]")
            return
        console.print("臨時令延遲分級：[cyan]L1[/]=1hr(停火/改砲擊目標) "
                      "[cyan]L2[/]=2hr(改方向/轉守) [cyan]L3[/]=3hr(整師撤退/跨軸調動)")
        level = input("選 L1/L2/L3：").strip().upper()
        if level not in ("L1", "L2", "L3"):
            console.print("[yellow]分級無效，已取消。[/]")
            return
        text = input("命令內容：").strip()
        if not text:
            console.print("[yellow]內容為空，已取消。[/]")
            return
        body = {"action": "order", "order": {"level": level, "text": text}}
        try:
            resp = json.loads(self._post("/hour_action", body))
            delay = {"L1": 1, "L2": 2, "L3": 3}[level]
            console.print(f"[green]✅ 臨時令已送達（{level}，{delay} 小時後生效）。[/]")
        except urllib.error.HTTPError as e:
            console.print(f"[red]送出失敗：{e.code} {e.reason}[/]")
        except Exception as e:
            console.print(f"[red]送出失敗：{e}[/]")

    def advise(self):
        """問自己的 AI 參謀（server 端用你的過濾視角即時調 Claude）。"""
        q = input("問參謀（你的軍師，只看得到你的視角）：").strip()
        if not q:
            console.print("[yellow]已取消（問題為空）。[/]")
            return
        console.print("[dim]參謀思考中…[/]")
        try:
            resp = json.loads(self._post("/advise", {"question": q}))
        except urllib.error.HTTPError as e:
            console.print(f"[red]參謀請求失敗：{e.code} {e.reason}[/]")
            return
        except Exception as e:
            console.print(f"[red]連線失敗：{e}[/]")
            return
        if resp.get("ok"):
            console.print("\n[bold green]═══ 參謀建議 ═══[/]")
            console.print(resp.get("answer", ""))
        else:
            console.print(f"[yellow]參謀暫時無法回答：{resp.get('answer','')}[/]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="GM server 網址（tunnel 或 http://ip:port）")
    ap.add_argument("--token", default="", help="連線 token")
    ap.add_argument("--side", required=True, choices=["allies", "axis"])
    args = ap.parse_args()

    cli = Client(args.url, args.token, args.side)
    if not cli.ping():
        console.print(f"[red]連不上 server：{args.url}[/]")
        console.print("[yellow]檢查：1) server 有開？ 2) tunnel 網址對？ 3) token 對？[/]")
        sys.exit(1)
    console.print(f"[green]已連上 GM server。你是 [{args.side}] 方。[/]")

    menu = ("\n[bold]指令：[/] [cyan]v[/]戰場  [cyan]r[/]戰報  [cyan]p[/]我的命令佇列  "
            "[cyan]h[/]本小時動作  [cyan]o[/]下主令(tick開頭)  [cyan]a[/]問參謀  [cyan]q[/]離開")
    while True:
        console.print(menu)
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "v":
            cli.view()
        elif cmd == "r":
            cli.report()
        elif cmd == "p":
            cli.pending()
        elif cmd == "h":
            cli.hour_action()
        elif cmd == "o":
            cli.order()
        elif cmd == "a":
            cli.advise()
        elif cmd == "q":
            break
    console.print("再見，指揮官。")


if __name__ == "__main__":
    main()
