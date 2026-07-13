#!/usr/bin/env python3
"""生成黑潮行動 Operation Black Tide 的乾淨開局 → state.json（Tick 0）。
沿用現有 state 的 map/objectives 結構、重建 7 個師的初始部署（scenario.md §3）。
"""
import json
from pathlib import Path
import orbat, hourstate as hs

G = Path.home() / "war-game"
old = json.load(open(G / "state.json"))     # 重用 map 結構

# (short, name, type, pos, strength, org, xp, resources)  依 scenario.md §3
UNITS = {
    "1ID":  ("1ID", "1st Infantry 'Big Red One'", "infantry", (3, 8), 100, 98, 4,
             {"POL": 90, "SA": 95, "HE": 90, "AT": 95, "RAT": 95, "MED": 95, "PARTS": 90}),
    "4ID":  ("4ID", "4th Infantry 'Ivy'", "infantry", (4, 11), 100, 95, 3,
             {"POL": 85, "SA": 90, "HE": 85, "AT": 85, "RAT": 90, "MED": 90, "PARTS": 80}),
    "3AD":  ("3AD", "3rd Armored 'Spearhead'", "armor", (5, 5), 100, 95, 4,
             {"POL": 80, "SA": 90, "HE": 80, "AT": 90, "RAT": 90, "MED": 85, "PARTS": 75}),
    "90ID": ("90ID", "90th Infantry 'Tough Ombres'", "infantry", (3, 15), 100, 92, 2,
             {"POL": 85, "SA": 90, "HE": 80, "AT": 80, "RAT": 90, "MED": 85, "PARTS": 80}),
    "17SS": ("17SS", "17.SS-PzGren 'Götz'", "panzergrenadier", (18, 9), 85, 85, 4,
             {"POL": 70, "SA": 80, "HE": 65, "AT": 70, "RAT": 75, "MED": 60, "PARTS": 55}),
    "2Pz":  ("2Pz", "2. Panzer-Division", "armor", (22, 5), 90, 90, 5,
             {"POL": 65, "SA": 80, "HE": 60, "AT": 60, "RAT": 70, "MED": 55, "PARTS": 50}),
    "352":  ("352", "352. Infanterie", "infantry", (18, 14), 70, 70, 2,
             {"POL": 60, "SA": 75, "HE": 55, "AT": 50, "RAT": 65, "MED": 50, "PARTS": 40}),
}
SIDE = {"1ID": "allies", "4ID": "allies", "3AD": "allies", "90ID": "allies",
        "17SS": "axis", "2Pz": "axis", "352": "axis"}

OBJ = {   # scenario.md §3：開局全在軸心手上
    "saint_vivien":  {"name": "Saint-Vivien", "pos": [18, 9], "controller": "axis", "value": "major"},
    "la_hetraie":    {"name": "La Hêtraie", "pos": [16, 2], "controller": "axis", "value": "minor"},
    "beaumont":      {"name": "Beaumont-sur-Sève", "pos": [19, 14], "controller": "axis", "value": "minor"},
    "bridge_north":  {"name": "Pont du Nord 北橋", "pos": [13, 3], "controller": "axis", "value": "bridge"},
    "bridge_central": {"name": "Pont du Centre 中橋", "pos": [14, 9], "controller": "axis", "value": "bridge"},
    "bridge_south":  {"name": "Pont du Sud 南橋", "pos": [12, 14], "controller": "axis", "value": "bridge"},
}

s = {
    "scenario_name": "黑潮行動 — Operation Black Tide",
    "scenario_id": "black_tide",
    "campaign_run": 1,
    "tick": 0, "max_ticks": 8,
    "map": old["map"],
    "weather": "晴 多雲 微風SW",
    "weather_state": {"current": {"tick": 0, "precipitation": "none", "cloud": "scattered",
                                  "visibility_km": 12, "cas_modifier": 1.0, "move_modifier": 1.0}},
    "campaign_pool": {"allies_tons": 120000, "axis_tons": 50000},
    "objectives": OBJ,
    "units": {},
    "fog_of_war": {"allies_spotted": ["352"], "axis_spotted": ["1ID", "3AD"],
                   "_note": "開戰預戰情報：美軍已知 352 在 Beaumont；Adler 已知 1ID、3AD 大致位置。"},
}
for uid, (short, name, typ, pos, strv, org, xp, res) in UNITS.items():
    s["units"][uid] = {
        "side": SIDE[uid], "short": short, "name": name, "type": typ, "pos": list(pos),
        "strength": strv, "org": org, "xp": xp, "fatigue": 0, "visibility_state": "STANDARD",
        "hidden": False, "resources": res, "broken_down_vehicles": 0,
        "orders": "", "last_action": "開戰部署",
    }

hs.ensure_hour_fields(s)
orbat.ensure_orbat(s)
json.dump(s, open(G / "state.json", "w"), ensure_ascii=False, indent=2)

print("=== 黑潮行動 乾淨開局 ===")
print(f"tick {s['tick']}/{s['max_ticks']}  {len(s['units'])} 師  地圖 {s['map']['width']}×{s['map']['height']}")
for uid, u in s["units"].items():
    print(f"  {uid:5} {u['side']:6} pos{u['pos']} 兵{u.get('personnel','?'):>6} 戰力{u['strength']}")
print("✅ state.json 已重置為乾淨 Tick 0")
