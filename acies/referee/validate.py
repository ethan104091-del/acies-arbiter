"""機械護欄（計劃 §4.7）。第一階段實作結構檢查與 G2／G3／G9 部分／G10 部分；
沙盒量級（G4）在 sandbox，守恆與授權（G5–G7）在落定時由 _audit 執行。
回傳 [(編號, 說明)]；空清單＝通過。
"""
import re

import pydantic

from acies.engine import verbs as V

from . import schema

FACTION_WORDS = re.compile(r"藍軍|紅軍|藍方|紅方|allies|axis|BLU-|RED-|我方|敵方|友軍")
PROBABILITY_WORDS = re.compile(r"擲骰|骰|機率|概率|隨機|大概|約略|可能性|運氣|random|roll|dice|chance|%\s*機會")


def validate(decision, state, *, kind="resolve", clause_status=None):
    """decision：dict；state：小時起始狀態；clause_status：{clause_id: status}（可省）。"""
    errs = []
    try:
        d = schema.parse(decision)
    except pydantic.ValidationError as e:
        return [("綱要", str(err["loc"]) + "：" + err["msg"]) for err in e.errors()]
    if d.get("kind", "resolve") != kind:
        errs.append(("綱要", f"卷宗種類為 {kind}，決定紀錄寫 {d.get('kind')}"))
    rulings = {r["ruling_id"]: r for r in d["rulings"]}
    units = state["units"]
    seqs = [a["seq"] for a in d["actions"]]
    if len(set(seqs)) != len(seqs):
        errs.append(("結構", "動作 seq 重複"))

    # G2／G3：裁示的形式
    for r in d["rulings"]:
        if FACTION_WORDS.search(r["condition"]) or any(u in r["condition"] for u in units):
            errs.append(("G2", f"裁示 {r['ruling_id']} 的條件指名陣營或編隊"))
        for fld in ("condition", "effect"):
            if PROBABILITY_WORDS.search(r[fld]):
                errs.append(("G3", f"裁示 {r['ruling_id']} 的{fld}含機率用語"))

    fire_targets = {}
    primary_by_unit = {}
    for a in d["actions"]:
        tag = f"seq {a['seq']}"
        if a["tier"] == 1:
            v = V.VERBS.get(a.get("verb") or "")
            if v is None:
                errs.append(("結構", f"{tag}：未知動詞 {a.get('verb')!r}")); continue
            if v.register_only and kind != "register":
                errs.append(("G10", f"{tag}：{v.name} 只准在登記卷宗"))
            if not v.register_only and kind == "register":
                errs.append(("G10", f"{tag}：登記卷宗不得執行 {v.name}"))
            missing = set(v.params) - set(a["args"]) - {"mission", "by_uid"}
            if missing:
                errs.append(("結構", f"{tag}：{v.name} 缺參數 {sorted(missing)}"))
            extra = set(a["args"]) - set(v.params)
            if extra:
                errs.append(("結構", f"{tag}：{v.name} 多了未定義的參數 {sorted(extra)}（動詞只收 {sorted(v.params)}）"))
            for uid in _units_of(a["args"]):
                if uid not in units:
                    errs.append(("G10", f"{tag}：編隊 {uid} 不存在於本小時快照"))
                elif units[uid]["side"] != a["provenance"]["side"]:
                    errs.append(("G10", f"{tag}：{uid} 不屬於出處陣營 {a['provenance']['side']}"))
                elif v.primary:
                    primary_by_unit.setdefault(uid, []).append(a["seq"])
            if v.name == "fire":
                t = a["args"].get("target")
                if t in fire_targets:
                    errs.append(("G9", f"{tag}：同小時對 {t} 已有 fire（seq {fire_targets[t]}），依裁示 63 須合併"))
                fire_targets[t] = a["seq"]
            if v.name == "register_clause" and a["args"].get("level") not in ("L1", "L2", "L3"):
                errs.append(("結構", f"{tag}：register_clause.level 須為 L1/L2/L3，不是 {a['args'].get('level')!r}（應變不登記進佇列，只寫 clause_updates）"))
            if v.name == "establish_cp" and a["args"].get("kind") not in ("main", "fwd"):
                errs.append(("結構", f"{tag}：establish_cp.kind 須為 main/fwd"))
            if v.name in ("fire", "barrage") and a["args"].get("mission", "壓制") not in V.MISSIONS:
                errs.append(("結構", f"{tag}：火力任務須為 {V.MISSIONS}"))
        else:
            if a.get("ruling_id") not in rulings:
                errs.append(("結構", f"{tag}：二級動作未指向本小時的裁示"))
            for p in a["applied"]:
                for why in V.check_primitive_args(p["primitive"], p["args"]):
                    errs.append(("G5", f"{tag}：{why}"))
                uid = p["args"].get("uid")
                if uid and uid not in units:
                    errs.append(("G1", f"{tag}：原語引用不存在的編隊 {uid}"))
        if clause_status is not None:
            st = clause_status.get(a["provenance"]["clause_id"])
            if st in ("blocked", "rejected", "superseded", "expired"):
                errs.append(("G10", f"{tag}：出處條款 {a['provenance']['clause_id']} 狀態為 {st}"))
    for uid, lst in primary_by_unit.items():
        if len(lst) > 1:
            errs.append(("G9", f"編隊 {uid} 有多個主動作 seq {lst}"))
    return errs


def _units_of(args):
    out = []
    for k in ("uid", "shooters", "attackers", "unit_uids"):
        v = args.get(k)
        if isinstance(v, str): out.append(v)
        elif isinstance(v, list): out.extend(v)
    return out
