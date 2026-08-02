"""相容層：Run 4 的 tick 腳本寫的是 `import of`。

★ 2026-07-30 起指向**凍結的 Run 4 引擎副本** `arbiter_run4.py`，不是專案根目錄的
  `arbiter.py`。理由：Run 5 要補齊 combat_v1 的 org 損失六項與缺陷 8，那會改變
  Run 4 的重播分數（那是刻意的改進），但 Run 4 本身必須永久可重播為 8813:1790。

  想拿**當前**引擎重播 Run 4 來看差異，改成 `import arbiter` 即可——那是有價值的
  對照實驗，但不是回歸測試。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # 專案根（mapcore 等）
sys.path.insert(0, str(Path(__file__).resolve().parent))        # 本目錄（凍結副本）
import arbiter_run4                                             # noqa: E402

sys.modules[__name__] = arbiter_run4
