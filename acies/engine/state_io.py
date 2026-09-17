"""狀態的進出與雜湊。

- normalize(s)：與 arbiter.load 逐行相同的正規化，但不經檔案系統（資料庫取出的狀態用）。
- canonical(s) / state_hash(s)：鍵排序、無空白的確定性序列化與 SHA-256；重放器與落定比對用。
- dumps(s)：與 arbiter.save 相同的可讀格式（快照存檔用，方便與 runs/ 的舊快照逐位元組比對）。
"""
import copy
import hashlib
import json

import arbiter as ar
import hourstate as hs
import orbat


def normalize(s):
    """arbiter.load 的正規化部分（arbiter.py:183-199），逐行對應；就地修改並回傳 s。"""
    hs.ensure_hour_fields(s)
    orbat.ensure_orbat(s)
    for uid, u in s["units"].items():
        if "equip" not in u:
            if u.get("is_detachment") and u.get("parent") in s["units"]:
                u["equip"] = ar.bn_equip(s["units"][u["parent"]], u.get("bn_code"))
            else:
                u["equip"] = dict(ar.EQUIP.get(u["type"], {"tanks": 0, "guns": 0}))
        u.setdefault("losses", {"personnel": 0, "tanks": 0, "guns": 0})
        u.setdefault("static_hours", 0)
        if u.get("side") in ("allies", "axis"):
            ar.ensure_ammo(u)
        u.setdefault("move_progress", 0.0)
        u.setdefault("flags", {})
    return s


def loads(text):
    return normalize(json.loads(text))


def dumps(s):
    """與 arbiter.save 相同格式。"""
    return json.dumps(s, ensure_ascii=False, indent=2)


def canonical(s):
    return json.dumps(s, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def state_hash(s):
    return hashlib.sha256(canonical(s).encode("utf-8")).hexdigest()


def clone(s):
    return copy.deepcopy(s)
