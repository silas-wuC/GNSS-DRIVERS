# GNSS-DRIVERS

本倉庫專門用來對 **各種型號 GNSS／RTK 模組** 做實驗，不是產品飛行軟體、也不是 ACU 主線。

這裡放的是各廠牌／各型號的讀取驅動、NMEA 解析、定位與定向輸出對比，以及實驗時需要的腳本與紀錄。正式系統（例如 CDP-JSAT-ACU）只吃驗證過的結果，實驗屎山不要往那邊塞。

## 這倉庫做什麼

- 接不同 GNSS／RTK 模組（序列埠、USB、廠商指令集、ROS 2 driver 都算）
- 核對原始 NMEA 幀、經緯度、橢球高／海拔高、DOP 是否合理
- 比對雙天線定向（yaw）與單點／RTK 解在同一台架上的收斂與漂移
- 留下可重跑的實驗紀錄與驅動草稿

## 這倉庫不做什麼

- 不承載衛星追蹤、波束控制、Modem 等 ACU 業務
- 不保證介面穩定；實驗結論通過後，再把精簡驅動搬進正式專案

倉庫目前剛起步，後續會依實際實驗對象（型號、介面、協定）補目錄與說明。

## 目錄結構

| 路徑 | 內容 |
|---|---|
| `src/gnss_drivers/nmea.py` | NMEA 語句解析，純函數、零 IO |
| `src/gnss_drivers/fix.py` | `GnssFix` 接收機狀態與狀態行格式化 |
| `src/gnss_drivers/serial_port.py` | 埠列舉與 Windows `COM10+` 路徑修正 |
| `src/gnss_drivers/um982/` | UM982 驅動、設定檔、CLI 與說明，見[該目錄 README](src/gnss_drivers/um982/README.md) |
| `tests/` | 解析層單元測試，**不需要硬體** |

解析與傳輸刻意分層：`nmea.py` / `fix.py` 不 import `serial`，所以測試直接餵字串、不用 mock，錄下來的 log 也能離線重放。

> ⚠️ **安裝需要 `setuptools>=61`（editable 需 `>=64`）與 `pip>=21.3`**。舊版 setuptools 會**靜默忽略** `pyproject.toml` 的 `[project]` 區塊，裝出一個名為 `UNKNOWN-0.0.0` 的空套件且不報錯。因此 `pytest` 走 `pythonpath` 設定、不依賴安裝 —— clone 下來就能跑測試。

## 安裝與執行

```bash
python -m pytest                     # 不接硬體、免安裝；只需 pyserial（3.10 另需 tomli）

# 想以套件方式 import 才需要安裝
pip install -e ".[dev]"

python -m gnss_drivers.um982                          # 不帶 --port 列出可用埠
python -m gnss_drivers.um982 --port COM29             # 參數也可寫進 ./um982.toml
```

各裝置的參數、設定檔與接線細節寫在各自目錄的 README。

## 支援裝置

| 型號 | 目錄 | 說明 |
|---|---|---|
| Unicore UM982 | `src/gnss_drivers/um982/` | 雙天線 RTK，定位＋定向（yaw）→ [README](src/gnss_drivers/um982/README.md) |
