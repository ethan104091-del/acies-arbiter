"""hourstate 完整測試。執行：python3 test_hourstate.py"""
import hourstate as h

def check(name, cond):
    print(("OK  " if cond else "FAIL") + " " + name)
    assert cond, name

# 時間換算
check("global_hour(2,3)=15", h.global_hour(2, 3) == 15)
check("split_global(15)=(2,3)", h.split_global(15) == (2, 3))
check("game_time(0)=開戰06:00", h.game_time_str(0) == "1944-08-25 06:00")
check("game_time(6)=次tick 12:00", h.game_time_str(6) == "1944-08-25 12:00")
check("game_time(18)=隔日00:00", h.game_time_str(18) == "1944-08-26 00:00")

# 日夜（rules_v2 §0）
check("gh0(06:00)=白天", h.daynight(0) == "白天")
check("gh12(18:00)=黃昏", h.daynight(12) == "黃昏")
check("gh13(19:00)=夜間", h.daynight(13) == "夜間")
check("gh23(05:00)=黎明", h.daynight(23) == "黎明")

# schema 升級冪等
s = {"tick": 1, "game_time": "old"}
h.ensure_hour_fields(s)
check("ensure: global_hour=6", s["global_hour"] == 6)
check("ensure: game_time 對齊", s["game_time"] == "1944-08-25 12:00")
check("ensure: pending 空", s["pending_orders"] == [])
prev = dict(s)
h.ensure_hour_fields(s)  # 再跑一次不該改值
check("ensure 冪等", s["pending_orders"] == [] and s["global_hour"] == 6)

# 延遲佇列：三級延遲
s = h.ensure_hour_fields({"tick": 0})
o1 = h.enqueue_order(s, "allies", "L1", "停火")
o2 = h.enqueue_order(s, "axis", "L2", "2Pz 機動")
o3 = h.enqueue_order(s, "allies", "L3", "全軍轉攻")
check("L1 effective=1", o1["effective_global_hour"] == 1)
check("L2 effective=2", o2["effective_global_hour"] == 2)
check("L3 effective=3", o3["effective_global_hour"] == 3)
check("id 唯一", len({o1["id"], o2["id"], o3["id"]}) == 3)

# 到期逐步生效
check("gh0 無到期", h.due_orders(s) == [])
h.advance_hour(s)  # gh1
due = h.activate_due(s)
check("gh1 只 L1 到期", len(due) == 1 and due[0]["text"] == "停火")
h.advance_hour(s)  # gh2
due = h.activate_due(s)
check("gh2 只 L2 到期", len(due) == 1 and due[0]["text"] == "2Pz 機動")
h.advance_hour(s)  # gh3
due = h.activate_due(s)
check("gh3 只 L3 到期", len(due) == 1 and due[0]["text"] == "全軍轉攻")

# pending_for 各方視角 + 倒數
s2 = h.ensure_hour_fields({"tick": 0})
h.enqueue_order(s2, "axis", "L3", "撤退")  # eff=3
p_axis = h.pending_for(s2, "axis")
p_allies = h.pending_for(s2, "allies")
check("axis 看到自己 pending", len(p_axis) == 1)
check("allies 看不到 axis 的 pending", len(p_allies) == 0)
check("倒數 = 3", p_axis[0]["hours_until_effective"] == 3)
h.advance_hour(s2)
check("倒數遞減為 2", h.pending_for(s2, "axis")[0]["hours_until_effective"] == 2)

# tick 邊界
s3 = h.ensure_hour_fields({"tick": 0})
check("gh0 是 tick 邊界", h.is_tick_boundary(s3))
h.advance_hour(s3)
check("gh1 非 tick 邊界", not h.is_tick_boundary(s3))
for _ in range(5):
    h.advance_hour(s3)  # gh6
check("gh6 回到 tick 邊界 tick=1", h.is_tick_boundary(s3) and s3["tick"] == 1)

# bad level
try:
    h.enqueue_order(s3, "axis", "L9", "x")
    check("bad level 應丟錯", False)
except ValueError:
    check("bad level 丟 ValueError", True)

print("\nALL HOURSTATE TESTS PASS")
