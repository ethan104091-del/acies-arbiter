#!/usr/bin/env python3
"""生成 PvP「純戰場 Open Field」的 state → maps/open_field_state.json。
雙方 10 編隊 180° 對稱部署、鏡像編制、指揮所與補給欄位齊備。可載入開局。
藍軍=allies、紅軍=axis（沿用既有 fog/filter 機制）。
"""
import json
from pathlib import Path
import orbat, hourstate as hs

G = Path.home() / "war-game"
W, H = 30, 18
mp = json.load(open(G / "maps" / "open_field.json"))

XP = {"infantry": 3, "armor": 4, "ranger": 5}
FULL = {"POL": 100, "SA": 100, "HE": 100, "AT": 100, "RAT": 100, "MED": 100, "PARTS": 100}

# 藍軍部署（西）；紅軍 = 180° 旋轉 (x,y)->(W-1-x,H-1-y)
BLUE = [
    ("BLU-1", "藍1步", "第1步兵師", "infantry", (1, 4)),
    ("BLU-2", "藍2步", "第2步兵師", "infantry", (1, 9)),
    ("BLU-3", "藍3步", "第3步兵師", "infantry", (1, 14)),
    ("BLU-AD", "藍裝", "藍軍裝甲師", "armor", (2, 9)),
    ("BLU-SF", "藍特", "藍軍特戰旅", "ranger", (2, 2)),
]
BLUE_MAIN_CP = (0, 9)


def rot(p): return (W - 1 - p[0], H - 1 - p[1])


def mk_unit(uid, short, name, typ, pos, side, concealed=False):
    return {
        "side": side, "short": short, "name": name, "type": typ,
        "pos": list(pos), "strength": 100, "org": 100, "xp": XP.get(typ, 3),
        "fatigue": 0, "visibility_state": "CONCEALED" if concealed else "STANDARD",
        "hidden": concealed, "resources": dict(FULL),
        "broken_down_vehicles": 0, "orders": "", "last_action": "開局部署",
    }


s = {
    "scenario_name": "純戰場 The Open Field",
    "scenario_id": "open_field",
    "mode": "pvp",
    "tick": 0, "max_ticks": 8,
    "map": mp,
    "units": {},
    "command": {
        # ★開局無指揮所——玩家須自行下令建立（scenario §5-B）。commander_at=None → +2 級延遲
        "allies": {"main_cp": None, "fwd_cp": None, "commander_at": None},
        "axis":   {"main_cp": None, "fwd_cp": None, "commander_at": None},
    },
    "weather_state": {"current": {"tick": 0, "precipitation": "none", "cloud": "clear",
                                  "visibility_km": 15, "cas_modifier": 1.0, "move_modifier": 1.0,
                                  "note": "全程晴好開闊、純戰術"}},
    "objectives": {"type": "attrition", "note": "殲敵較多者勝；斬首即勝；平手比自損"},
    "victory_state": None,
    "supply_note": "補給走廊/效率於渲染與結算時由單位位置即時計算（見 scenario_open_field.md §5-A）",
}

for uid, short, name, typ, pos in BLUE:
    s["units"][uid] = mk_unit(uid, short, name, typ, pos, "allies", concealed=(typ == "ranger"))
    ruid = uid.replace("BLU", "RED")
    rshort = short.replace("藍", "紅")
    rname = name.replace("藍軍", "紅軍").replace("第", "紅第")
    s["units"][ruid] = mk_unit(ruid, rshort, rname, typ, rot(pos), "axis", concealed=(typ == "ranger"))

# fog：雙方互見對方主力（步兵+裝甲），特戰旅隱蔽、指揮所須偵察
s["fog_of_war"] = {
    "allies_spotted": ["RED-1", "RED-2", "RED-3", "RED-AD"],
    "axis_spotted":   ["BLU-1", "BLU-2", "BLU-3", "BLU-AD"],
    "_note": "特戰旅開局隱蔽(未列)、指揮所位置須靠偵察找出。",
}

hs.ensure_hour_fields(s)      # 補 hour/延遲佇列/standing 欄位
orbat.ensure_orbat(s)         # 補 personnel + 營級編制樹

out = G / "maps" / "open_field_state.json"
out.write_text(json.dumps(s, ensure_ascii=False, indent=2))

# ── 驗證 ──
print("=== 純戰場 state 生成 ===")
print(f"編隊 {len(s['units'])} 個  地圖 {W}×{H}  上限 {s['max_ticks']} ticks")
for uid, u in s["units"].items():
    print(f"  {uid:7} {u['side']:6} pos{u['pos']} 兵{u['personnel']:>6} 兵種{u['type']:9} vis{u['visibility_state']}")
# 對稱檢查
ok = all(s["units"][b]["personnel"] == s["units"][b.replace("BLU", "RED")]["personnel"]
         for b in ["BLU-1", "BLU-2", "BLU-3", "BLU-AD", "BLU-SF"])
print("鏡像人數對稱：", "✅" if ok else "❌")
print("指揮所：開局皆未建（玩家須自行下令建立）→ 起始 +2 級延遲")
print("✅", out)
