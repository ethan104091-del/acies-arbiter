# archive/ — 不再使用但保留的東西

刪檔不可逆，所以這裡不刪任何東西。放進來的條件是：
**沒有任何程式或文件引用它，而且它已被更好的東西取代。**

| 檔案 | 是什麼 | 為何在這裡 |
|---|---|---|
| `mapgen.py` | 早期的地圖生成器 | 零引用。地圖現由 `scenarios/*_setup.py` 直接寫入 state，並由 `mapcore.py` 渲染 |
| `openfield_preview.py` | 純戰場的靜態預覽圖產生器 | 零引用。預覽改用 `tools/map.py --state …`，那支是活的、吃真實 state |
| `detachments.py.bak` | 抽離營機制的早期原型（2026-06-05） | 已整併進 `orbat.py` 的 `detach` / `rejoin` 與 `arbiter.py` 的 `detach_bn` / `rejoin_bn`（含裝備與彈藥守恆） |
| `map_proto.py.bak` | 地圖渲染原型（2026-05-29） | 已整併進 `mapcore.py` |
| `combat_log_run2.jsonl.archive` | Run 2 的逐小時戰鬥日誌（2026-05-23） | Run 2、Run 3 沒有留下 `runs/` 目錄；這是那個時期唯一的殘存紀錄，故保留 |

## 這裡的東西不受測試與規格一致性檢查約束

`tests/` 不載入本目錄。若要復用其中任何一支，**先確認它引用的引擎 API 還存在**——
`arbiter.py` 自 Run 4 以來改動甚多（缺陷 1–24、裁示 17／18／25／32），
這些檔案停在更早的版本。
