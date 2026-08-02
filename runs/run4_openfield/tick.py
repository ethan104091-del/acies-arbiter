#!/usr/bin/env python3
"""每 tick 的檔案產出：雙方戰報、上帝視角快照、實時戰史追加。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import of

SP = Path(__file__).parent
BLUE_HQ = SP.parent / "blue_hq"   # 裁判工具移進 referee/ 後，blue_hq 在上一層
RED_HQ = Path.home() / "Desktop" / "料鋒_紅軍指揮部"
OBS = Path.home() / "Desktop" / "料鋒_觀戰席"


def briefs(n, extra_blue="", extra_red=""):
    s = of.load()
    of.refresh_visibility(s)
    of.spot(s)
    of.save(s)
    (BLUE_HQ / f"戰報_T{n}.md").write_text(of.brief_md(s, "allies") + extra_blue)
    (RED_HQ / f"戰報_T{n}.md").write_text(of.brief_md(s, "axis") + extra_red)
    (OBS / f"地圖_T{n}.txt").write_text(of.ascii_map(s, "god"))
    print(f"✅ 戰報 T{n} 已產出")
    print(of.ascii_map(s, "god"))
    return s


def append(text):
    p = OBS / "戰報_實時.md"
    p.write_text(p.read_text() + text)
    print(f"✅ 已追加 {len(text)} 字到實時戰史")


def orders_doc(n, blue_orders, red_orders):
    (OBS / f"雙方命令_T{n}.md").write_text(
        f"# Tick {n} 雙方命令（上帝視角，兩邊都看得到）\n\n"
        f"## 藍軍（Opus 5）\n\n{blue_orders}\n\n---\n\n## 紅軍（Codex gpt-5.6-terra）\n\n{red_orders}\n")
    print(f"✅ 雙方命令_T{n}.md")


if __name__ == "__main__":
    if sys.argv[1] == "briefs":
        briefs(int(sys.argv[2]))
    elif sys.argv[1] == "god":
        s = of.load()
        print(of.god_md(s))
