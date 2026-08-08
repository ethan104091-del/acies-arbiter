#!/usr/bin/env python3
"""每個 tick 的命令清單 — `docs/plan_run8.md` 的 1-C，S2 的承重牆。

## 為什麼存在

Run 7 的八個裁判錯誤裡有五個是同一件事：**「雙方皆適用」的規則被實作成
裁判寫的清單或腳本步驟。** 而稽核抓不到它們，因為
「某編隊的移動是否符合其命令」需要**命令的機器可讀表示**（判例 §二十四 定案第 3 點）。

本模組就是那個表示。tick 腳本必須先把該 tick 的動作登記進 `TickOrders`，
`_audit` 再拿它與實際的 state 變化對帳。

| 抓到的瑕疵 | 判例 | 對應檢查 |
|---|---|---|
| 構工批次化 `set(DEST)`，白給一方 13,988 man-hr | §二十一 | A3 |
| 沿用已被新命令取代的目的地 | §二十四 錯誤三 | A4／A7 |
| 逼退被實作成行軍 | §二十五 | A5 |
| 攻方逼退（`push < 0`）從未執行 | R8-G1 | A5 |
| 裁示 47 只套在一方身上 | §二十四 錯誤一 | A8（現已由引擎擋掉） |

## 三條硬規則

1. **`dig` / `camo` / `barrage` 只接受逐一列舉。** 手冊明定這三者須明確下令
   （裁示 33、17、攔阻射擊），故本模組**拒絕**任何由其他集合推導而來的形式：
   傳入 `set(DEST)`、`set(s["units"])`、或任何非 `str` 的可迭代成員都會 raise。
2. **每個登記的動作都要有 `src`（命令出處）**，且 `src` 必須含本 tick 的代號
   （如 `T6`）。這是對判例 §二十四「不得從上一 tick 的腳本複製」的機械檢查——
   複製過來的出處字串會寫著 `T5`，於是 `validate()` 失敗。
3. **不得從上一個 tick 的物件複製。** `TickOrders` 沒有 `copy()`，
   且 `merge()` 會 raise。每個 tick 從命令原文重新建立。

## 用法

    mf = _manifest.TickOrders(tick=8)
    mf.march("BLU-AD", (15, 8), src="藍軍 T8 第 1 條")
    mf.dig_order("BLU-1", src="藍軍 T8 第 3 條")
    mf.fire_mission(["BLU-1"], target="RED-2", mission="壓制", src="藍軍 T8 第 4 條")
    mf.validate()                       # ← 缺 src／出處不含 T8 即 raise

    # 應變觸發時，在 resolve 裡登記，否則 A6 會把它報成無出處的射擊
    mf.contingency_fired("RED-SF", src="紅軍 T8 應變第 2 條")

    _audit.require_clean(s, before, manifest=mf)
"""
import re


class ManifestError(AssertionError):
    """清單本身不合法——在解算之前就該擋下來。"""


def _one_uid(x, what):
    if not isinstance(x, str) or not x:
        raise ManifestError(
            f"{what} 只接受單一編隊代號（str），收到 {type(x).__name__}：{x!r}。"
            f"★ 構築工事／偽裝作業／攔阻射擊必須逐一列舉並標明命令出處——"
            f"不得寫成 set(DEST)、all_units 或任何由其他集合推導的形式"
            f"（判例 §二十一：批次化的預設值總是偏向某一方）。")
    return x


class TickOrders:
    """一個 tick 的命令清單。每個 tick 重新建立，不得複製。"""

    def __init__(self, tick):
        if not isinstance(tick, int) or tick < 0:
            raise ManifestError(f"tick 須為非負整數，收到 {tick!r}")
        self.tick = tick
        self.tag = f"T{tick}"
        self.move = {}          # uid -> (x, y)
        self.dig = set()
        self.camo = set()
        self.fire = []          # {"shooters": [uid], "target": uid|None, "hex": (x,y)|None, "mission": str}
        self.barrage = []       # {"shooters": [uid], "hex": (x,y)}
        self.triggered = set()  # 應變觸發而開火／位移的編隊
        self.src = {}           # 鍵（uid 或 "動作:key"）-> 命令出處字串

    # ── 登記 ────────────────────────────────────────────────────
    def march(self, uid, dest, src):
        """登記行軍目的地。dest 為命令原文所寫的格，護欄改趨相鄰格不必另記。"""
        self.move[_one_uid(uid, "march")] = (int(dest[0]), int(dest[1]))
        self.src[f"move:{uid}"] = src
        return self

    def dig_order(self, uid, src):
        self.dig.add(_one_uid(uid, "dig_order"))
        self.src[f"dig:{uid}"] = src
        return self

    def camo_order(self, uid, src):
        self.camo.add(_one_uid(uid, "camo_order"))
        self.src[f"camo:{uid}"] = src
        return self

    def fire_mission(self, shooters, src, target=None, hexpos=None, mission="壓制"):
        sh = [_one_uid(x, "fire_mission") for x in shooters]
        if (target is None) == (hexpos is None):
            raise ManifestError("fire_mission 須指定 target 或 hexpos，恰好其一")
        self.fire.append({"shooters": sh, "target": target,
                          "hex": None if hexpos is None else (int(hexpos[0]), int(hexpos[1])),
                          "mission": mission})
        self.src[f"fire:{'+'.join(sh)}->{target or hexpos}"] = src
        return self

    def barrage_order(self, shooters, hexpos, src):
        sh = [_one_uid(x, "barrage_order") for x in shooters]
        self.barrage.append({"shooters": sh, "hex": (int(hexpos[0]), int(hexpos[1]))})
        self.src[f"barrage:{'+'.join(sh)}->{hexpos}"] = src
        return self

    def contingency_fired(self, uid, src):
        """應變條件觸發而開火或位移。

        應變欄是 Run 7 三個轉折的來源，卻只存在於命令的散文裡
        （`docs/TODO.md` R8-H2：它在 PvP 甚至沒有規範住址）。
        登記它使 A6 得以機械化，同時讓「哪一條應變在第幾小時觸發」進入稽核紀錄。
        """
        self.triggered.add(_one_uid(uid, "contingency_fired"))
        self.src[f"contingency:{uid}"] = src
        return self

    # ── 查詢 ────────────────────────────────────────────────────
    def shooters(self):
        out = set()
        for f in self.fire:
            out |= set(f["shooters"])
        for b in self.barrage:
            out |= set(b["shooters"])
        return out

    # ── 驗證 ────────────────────────────────────────────────────
    def validate(self):
        """每個動作都要有出處，且出處必須指向**本** tick。不合法即 raise。"""
        bad = []
        for key, src in self.src.items():
            if not src or not str(src).strip():
                bad.append(f"{key}：出處為空")
            elif not re.search(rf"\bT{self.tick}\b", str(src)):
                bad.append(f"{key}：出處「{src}」未指向本 tick（應含 {self.tag}）"
                           f"——★ 判例 §二十四：不得從上一 tick 的腳本複製")
        expect = ({f"move:{u}" for u in self.move} | {f"dig:{u}" for u in self.dig}
                  | {f"camo:{u}" for u in self.camo})
        for key in sorted(expect - set(self.src)):
            bad.append(f"{key}：未登記出處")
        if bad:
            raise ManifestError("命令清單不合法（解算前即擋下）：\n  - " + "\n  - ".join(bad))
        return self

    def merge(self, other):
        raise ManifestError(
            "★ 不得合併或沿用上一個 tick 的命令清單。"
            "判例 §二十四 定案第 2 點：每個 tick 的目的地／作業／火力清單，"
            "必須自該 tick 雙方的命令文字重新建立。")

    copy = __copy__ = __deepcopy__ = merge

    def __repr__(self):
        return (f"TickOrders({self.tag}: move={len(self.move)} dig={len(self.dig)} "
                f"camo={len(self.camo)} fire={len(self.fire)} barrage={len(self.barrage)} "
                f"triggered={len(self.triggered)})")
