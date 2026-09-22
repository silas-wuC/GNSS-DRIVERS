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
| `src/gnss_drivers/um982.py` | UM982 序列埠傳輸、初始化時序、讀取迴圈 |
| `scripts/read_um982.py` | CLI：列埠、初始化、即時狀態輸出 |
| `tests/` | 解析層單元測試，**不需要硬體** |

解析與傳輸刻意分層：`nmea.py` / `fix.py` 不 import `serial`，所以測試直接餵字串、不用 mock，錄下來的 log 也能離線重放。

## 安裝與執行

```bash
pip install -e ".[dev]"
python -m pytest                     # 不接硬體即可全綠

python scripts/read_um982.py                          # 不帶 --port 列出可用埠
python scripts/read_um982.py --port /dev/ttyUSB0      # Linux／WSL
python scripts/read_um982.py --port COM29             # Windows
python scripts/read_um982.py --port COM29 --no-init   # 設定已存 flash 時跳過初始化
python scripts/read_um982.py --port COM29 --dump      # 印出未解析的語句類型
```

## 裝置：Unicore UM982

雙天線 RTK 模組，同時輸出定位與定向（yaw）。

### 接線

- **ANT1＝主天線**，決定位置解；**ANT2＝從天線**，與 ANT1 共同決定航向。
- 兩根天線必須**剛性固連**，基線長度不可變動 —— 這是 `CONFIG HEADING FIXLENGTH` 能成立的前提。
- 基線越長角精度越高（角度誤差 ≈ 相位誤差 ÷ 基線長），但太長不利安裝，實務上取捨。
- 只接 ANT1 時 THS 會回報 `V`（無效），`YAW` 顯示 `--`，**這是正確行為不是故障**。

### 序列埠參數

`230400 8N1`，無流控。

> ⚠️ **模組出廠預設是 115200**。沒改過的新模組要先用 115200 連上，下 `CONFIG COM1 230400` 改速率後才能用預設參數連。腳本在連續 5 秒收不到有效 NMEA 時會提示這件事。

### 初始化指令

| 指令 | 作用 | 不下的後果 |
|---|---|---|
| `UNLOGCOM` | 清掉當前埠既有的週期輸出 | 新舊設定疊加而非取代，頻寬爆掉且每次上電行為不同 |
| `CONFIG MODE UAV` | 動態模型設為無人機 | 快速運動時濾波器把真實運動當雜訊壓掉，位置／航向滯後 |
| `CONFIG HEADING FIXLENGTH` | 宣告雙天線基線長度固定 | 模糊度搜索空間變大，heading 收斂慢，THS 長時間回 `V` |
| `CONFIG NMEA GGA/RMC/THS/VTG ONCHANGED 0.05` | 20 Hz 主資料流 | 控制迴路吃不到足夠更新率 |
| `CONFIG NMEA GSV/GSA/GST ONCHANGED 1` | 1 Hz 診斷流 | 全開 20 Hz 約吃掉 70% 埠容量，buffer 滿會吐截斷語句 |
| `KSXT 0.05` | 20 Hz 廠商專有句 | 目前未解析，見「已知限制」 |
| `SAVECONFIG` | 寫入 flash | 預設**不執行**，需 `--save-config`；見下方說明 |

**各指令細節**

- **`UNLOGCOM` 為什麼必須第一條**：設定存在 flash，上電會自動恢復上次的輸出清單。不先清空就下 `CONFIG NMEA`，等於在舊清單上疊加 —— 你以為只開了 7 種語句，實際可能吐十幾種。症狀是 checksum 偶發失敗、資料跳拍，而且**每次上電表現不一樣**，除錯毫無再現性。

- **為什麼診斷語句降到 1 Hz**：230400 baud ÷ 10 bit/byte ≈ 23 KB/s。若全部 20 Hz，約 20 × 800 bytes ≈ 16 KB/s，逼近容量 70%。GSV 尤其肥（11 顆可見衛星要 3 句），20 Hz 純屬浪費。DOP 與衛星清單是給人看的，1 Hz 綽綽有餘。

- **`SAVECONFIG` 為什麼預設關閉**：NOR flash 寫入壽命典型 10K–100K 次。設定下過一次就存住了，日常跑腳本只需要 `UNLOGCOM` + `CONFIG NMEA`（揮發性設定本來就要重下）。每次都寫、而且寫的內容一模一樣，純粹消耗壽命。寫爛的症狀是 `SAVECONFIG` 靜默失敗或上電設定丟失 —— 屆時你不會聯想到 flash 壽命。

### NMEA 語句對照表

| 語句 | 內容 | 本驅動 |
|---|---|---|
| `GGA` | UTC、經緯度、解算品質、使用衛星數、HDOP、海拔高、大地水準面差距 | ✅ 解析 |
| `GSA` | 各系統使用衛星、PDOP／HDOP／VDOP | ✅ 解析（取 HDOP／VDOP） |
| `THS` | 真航向與狀態旗標 | ✅ 解析（雙天線 yaw） |
| `RMC` | UTC、日期、定位、地速、航跡角 | ⬜ 已開啟未解析 |
| `VTG` | 對地航跡角與速度 | ⬜ 已開啟未解析 |
| `GSV` | 可見衛星清單與 SNR | ⬜ 已開啟未解析 |
| `GST` | 偽距誤差統計（位置標準差） | ⬜ 已開啟未解析 |
| `KSXT` | 廠商專有句：位置＋航向＋速度＋解狀態＋標準差 | ⚠️ 已開啟未解析 |

### 已知限制

- **`KSXT` 已開啟輸出但尚未解析**，20 Hz × 約 130 bytes ≈ 26 kbps 白白浪費。刻意保留是為了能用 `--dump` 抓到實物語句，照著寫 parser；欄位定義必須對照官方手冊，猜不得。確定不用就該從 `MODULE_INIT_COMMANDS` 移除。
- **`ALT_HAE` 依賴 GGA 第 11 欄的大地水準面差距**，模組未輸出該欄時顯示 `--`（`ALT_MSL` 仍正常）。實測本模組有輸出，差值約 18.9 m。
- **雙天線 heading 需要收斂時間**，冷啟動或遮擋後重新收斂期間 THS 回 `V`。
- **`CONFIG HEADING FIXLENGTH` 的參數形式待確認** —— 本驅動照現有腳本不帶參數下達，實測可正常收斂。但手冊若定義了基線長度參數（如 `CONFIG HEADING FIXLENGTH <公尺>`），帶上實際長度應可再提升定向精度。**尚未對照官方手冊驗證。**
