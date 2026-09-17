"""料鋒 Acies v2 — 後端、裁判工作者、引擎轉接層。

v1 引擎（arbiter.py 等）不動；本套件只透過 acies.engine 呼叫它。
設計依據：docs/design_v2_referee.md、計劃檔 ~/.claude/plans/tranquil-frolicking-pike.md。
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "runs"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def load_dotenv(path=ROOT / ".env"):
    """讀 ~/war-game/.env（KEY=VALUE 一行一個；不覆蓋既有環境變數）。金鑰不進版本控制。"""
    import os
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


load_dotenv()
