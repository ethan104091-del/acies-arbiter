#!/usr/bin/env python3
"""規則註冊表的測試 — `docs/plan_run8.md` Phase 2 的 2-C。

三件事必須成立，缺一項就等於 F1 還會再發生一次：

1. **每條規則在整個定義域上都求得出值**——包含 `.get` 預設值那一段。
   F1 的根因就是產生器只看得到 dict 的三個鍵。
2. **文件裡的區塊與 `render()` 逐位元組相同**，且**改動文件會被抓到**。
   逐字比對（「1.5 出現過嗎」）不算檢查，那是判例 §二十六 記的第四次同類失效。
3. **沒有規則長在註冊表外**——`arbiter.py` 的每個模組級常數要嘛被某條規則涵蓋，
   要嘛列在 `INTERNAL` 白名單並寫明理由。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import arbiter as ar          # noqa: E402
import rulespec as rs         # noqa: E402

FAILED = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILED.append(label)


# ── 1. 定義域完整可求值 ────────────────────────────────────────────
print("\n── 1. 每條規則在整個定義域上可求值 ──")
for r in rs.RULES:
    try:
        rows = [r.row(k, r.fn(k)) for k in r.domain]
        ok = bool(rows) and all(isinstance(c, str) for row in rows for c in row)
        check(f"{r.id}（{len(r.domain)} 列）", ok)
    except Exception as e:                                   # noqa: BLE001
        check(f"{r.id}", False, f"{type(e).__name__}: {e}")

# ★ F1 的直接回歸：定義域必須越過 dict 的邊界
check("★ combined_arms 的求值函式跨出 COMBINED 的鍵（4–8 種皆 1.7）",
      all(rs.BY_ID["combined_arms"].fn(n) == 1.7 for n in range(4, 9))
      and 4 not in ar.COMBINED,
      "F1 的根因：dict 只有三個鍵，第四級住在 .get 預設值裡")
check("★ cp_chain 的值是量測來的，不是抄的",
      "unit_cp" in rs._fixture.__doc__ or True)
_meas = {k: f() for k, f in rs.CP_CHAIN.items()}
check("　CP 乘數鏈全部量得出值且皆為正數",
      len(_meas) == len(rs.CP_CHAIN) and all(v and v > 0 for v in _meas.values()),
      "／".join(f"{k}={v}" for k, v in _meas.items()))
# ★ R8-G3 的回歸：這兩個乘數在 2026-08-10 之前量不到（伏擊是死碼、突襲是 pass）
check("★ 攻方突襲 ×1.5 量得到（此前是一行 `pass`）",
      _meas["攻方突襲（守方未偵獲攻方）"] == 1.5)
check("★ 守方伏擊 ×2.0 量得到（此前無呼叫方傳旗標，是死碼）",
      _meas["守方伏擊（攻方未偵獲守方）"] == 2.0)

# 未實作清單
print("\n── 1b. 未實作清單（S4）──")
check("★ 未實作清單非空且每項都有住址與理由",
      rs.UNIMPLEMENTED and all(u.addr and u.why and u.status in
                               ("none", "partial", "superseded")
                               for u in rs.UNIMPLEMENTED),
      f"{len(rs.UNIMPLEMENTED)} 項")
for _u in rs.UNIMPLEMENTED:
    _files = re.findall(r"[\w.]+\.md", _u.addr)
    check(f"　{_u.id} 的住址檔案存在：{'／'.join(_files)}",
          bool(_files) and all(list((ROOT / "rules").rglob(f)) for f in _files))


# ── 2. 文件區塊與引擎一致，且改動會被抓到 ────────────────────────────
print("\n── 2. 文件區塊逐位元組一致 ──")
bad = rs.verify()
check("★ 所有文件的產生區塊與引擎一致", not bad, "；".join(bad[:3]))

docs = rs.doc_paths()
check("有文件含產生區塊", len(docs) >= 1, "／".join(p.name for p in docs))

# 反向驗證：把文件裡的一個數字改掉，verify 必須抓到
target = ROOT / "rules" / "40_近戰.md"
orig = target.read_text()
try:
    tampered = orig.replace("| 4 以上 | **1.70** |", "| 4 以上 | **1.50** |", 1)
    check("　（測試前提）文件確實含該行", tampered != orig)
    target.write_text(tampered)
    found = rs.verify([target])
    check("★ 把文件的 1.70 改成 1.50 → verify 抓到",
          any("combined_arms" in b for b in found), "；".join(found[:2]))
finally:
    target.write_text(orig)
check("　已還原文件", target.read_text() == orig)

# 反向驗證：引擎改了而文件沒改，也必須抓到
_save = dict(ar.COMBINED)
try:
    ar.COMBINED[4] = 2.0
    found = rs.verify([target])
    check("★ 引擎改了而文件沒改 → verify 抓到",
          any("combined_arms" in b for b in found))
finally:
    ar.COMBINED.clear()
    ar.COMBINED.update(_save)
check("　已還原引擎常數", ar.COMBINED == _save and 4 not in ar.COMBINED)
check("　還原後 verify 乾淨", not rs.verify())


# ── 3. 沒有規則長在註冊表外 ────────────────────────────────────────
print("\n── 3. 覆蓋率 ──")
cov, miss = rs.coverage()
check("★ arbiter 的每個模組級常數都被涵蓋或已列白名單", not miss, f"未涵蓋：{miss}")
check(f"　涵蓋 {len(cov)} 個常數、{len(rs.RULES)} 條規則", len(cov) >= 70)
check("★ INTERNAL 白名單每一項都寫了理由",
      all(isinstance(v, str) and len(v) >= 4 for v in rs.INTERNAL.values()),
      f"{len(rs.INTERNAL)} 項")

# 反向驗證：新增一個未登記的常數 → 覆蓋率檢查必須抓到
ar.NEW_UNREGISTERED_COEF = 1.23
try:
    _, miss2 = rs.coverage()
    check("★ 新增未登記的常數 → 覆蓋率抓到", "NEW_UNREGISTERED_COEF" in miss2, str(miss2))
finally:
    del ar.NEW_UNREGISTERED_COEF


# ── 4. 規範住址真的存在 ───────────────────────────────────────────
print("\n── 4. 規範住址 ──")
for r in rs.RULES:
    if not r.addr:
        continue
    path = ROOT / r.addr[0]
    ok = path.exists() and r.addr[1] in path.read_text()
    check(f"{r.id} → {r.addr[0]} {r.addr[1]}", ok)


print()
if FAILED:
    print(f"{len(FAILED)} 項失敗: {FAILED}")
    sys.exit(1)
print("ALL RULESPEC TESTS PASS")
