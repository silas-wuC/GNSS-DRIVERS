# UM982 驅動

Unicore UM982 雙天線 RTK 模組：同時輸出定位與定向（yaw）。本目錄放這顆模組的全部東西：

| 檔案 | 內容 |
|---|---|
| `driver.py` | 序列埠傳輸、初始化時序、讀取迴圈（`UM982`、`InitTiming`） |
| `config.py` | TOML 設定載入、型別與範圍檢查、命令行覆蓋（`UM982Config`） |
| `__main__.py` | CLI 主程序，由根目錄 `run_um982.py` 或 `python -m gnss_drivers.um982` 啟動 |
| `um982.example.toml` | 設定範本，數值與代碼預設**完全一致**（有測試把關） |

NMEA 解析（`nmea.py`）、接收機狀態（`fix.py`）、埠工具（`serial_port.py`）是跨型號共用層，放在上一層 `gnss_drivers/`。

---

## 快速開始

在倉庫根目錄：

```bash
pip install -r requirements.txt
python run_um982.py                  # 列出可用序列埠
python run_um982.py --port COM29     # Windows；Linux／WSL 用 /dev/ttyUSB0
```

要固定參數，把 `src/gnss_drivers/um982/um982.example.toml` 複製成根目錄的 `um982.toml`，改 `port` 後直接 `python run_um982.py`。

裝過套件（`pip install -e .`）的話，`python -m gnss_drivers.um982` 等價，參數完全相同。

> `um982.toml` 已列入 `.gitignore`：每個台架的 COM 埠、基線長度都不同，提交上去只會互相覆蓋。要分享設定就改範本。

---

## 參數來源與優先順序

**`--` 命令行參數 ＞ config 檔 ＞ 代碼預設值**，逐項比較，不是整檔取代。

| 情境 | 結果 |
|---|---|
| 沒帶 `--config`，目前目錄**有** `um982.toml` | 讀它，啟動印 `Config: um982.toml` |
| 沒帶 `--config`，目前目錄**沒有** `um982.toml` | 全用預設值，啟動印 `Config: um982.toml not found, using defaults` |
| `--config path/x.toml`，檔案存在 | 讀它 |
| `--config path/x.toml`，檔案**不存在** | `Config error: ... file not found`，exit 1（不准靜默回落預設值） |

⚠️ 預設路徑是**相對於當前工作目錄**，不是相對於倉庫。從別的目錄啟動就讀不到 —— 所以每次啟動第一行都會印 `Config:`，先看這行再懷疑別的。

範圍檢查在**合併之後**執行一次，config 檔和 `--` 帶的值吃同一套規則。

---

## 參數全表

### `[serial]` 序列埠

| TOML key | `--` 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|---|
| `port` | `--port` | str | `""` | 序列埠名，如 `COM29`、`/dev/ttyUSB0`。**空值＝列出可用埠後退出**（exit 0）。Windows `COM10` 以上自動轉成 `\\.\COM10` |
| `baud` | `--baud` | int | `230400` | 必須 > 0。**出廠預設是 115200**，見下方「序列埠參數」 |
| `read_timeout_s` | `--read-timeout-s` | float | `1.0` | 單次 `readline()` 最多等幾秒，必須 > 0（0 在 pyserial 是非阻塞，會讀到半截語句）。也是 `empty_read_limit` 的計時單位 |

### `[run]` 執行行為

| TOML key | `--` 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|---|
| `dump` | `--dump` / `--no-dump` | bool | `false` | 每種「通過 checksum 但未解析」的語句印第一筆（前 80 字元），寫新 parser 前抓樣本用 |
| `init` | `--init` / `--no-init` | bool | `true` | 啟動時送初始化指令。設定已存 flash、只想讀資料時關掉 |
| `save_config` | `--save-config` / `--no-save-config` | bool | `false` | 初始化尾巴加 `SAVECONFIG` 寫入 flash。**`init = false` 時無效**（整段初始化跳過，會印警告） |
| `no_data_warn_after_s` | `--no-data-warn-after-s` | float | `5.0` | 連續這麼久收不到**有效** NMEA 就提示檢查 baud，只提示一次，不退出。必須 ≥ 0 |
| `empty_read_limit` | `--empty-read-limit` | int | `10` | 連續這麼多次讀取**一個位元組都沒有**就 `Read failed` 退出（預設 10 × 1.0 s ≈ 10 秒）。`0`＝永遠等，適合模組晚上電的台架。必須 ≥ 0 |

`no_data_warn_after_s` 和 `empty_read_limit` 抓的是兩種不同故障：baud 錯時模組仍在吐位元組（只是亂碼、checksum 不過），只會觸發前者；線拔了／沒上電才是零位元組，觸發後者。

### `[init]` 初始化時序與指令

| TOML key | `--` 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|---|
| `cmd_delay_s` | `--init-cmd-delay-s` | float | `0.08` | 每條指令送出並讀回覆後的停頓。調太小，回覆會擠進下一條的讀取窗口 |
| `saveconfig_settle_s` | `--init-saveconfig-settle-s` | float | `0.35` | `SAVECONFIG` 後的停頓，寫 flash 比一般指令慢 |
| `reply_timeout_s` | `--init-reply-timeout-s` | float | `5.0` | 每條指令最多等幾秒回覆，必須 > 0。回覆排在模組**已緩衝的輸出後面**，輸出清單超過埠容量時可能積壓好幾秒，所以按時間等、不按行數。逾時或回覆不是 `response: OK` 都會 `Init failed` 並 exit 1 |
| `drain_read_timeout_s` | `--init-drain-read-timeout-s` | float | `0.05` | 等回覆期間的單行逾時，必須 > 0 |
| `commands` | **僅 config** | list[str] | 見下表 | 啟動時依序送出的指令。不能為空、不能有空白項、**不能含 `SAVECONFIG`**（改用 `run.save_config`） |

`commands` 不開放命令行：每條指令都含空格，塞進命令行要逐條加引號，錯一個引號整條就拆散。

`commands` 會**整份取代**預設清單，不是追加。要加一條，從範本複製整份再改。第一條請保持 `UNLOG`（原因見下表）。

⚠️ 舊版範本裡的 `drain_lines_max` 已移除，台架上沿用舊 `um982.toml` 會報 `init.drain_lines_max: unknown key`。這是故意的：舊範本的指令清單整份都是模組不認的寫法（見「排障」），必須從新範本重新複製。

---

## 設定範例

完整範本：[`um982.example.toml`](um982.example.toml)。

**新模組第一次連線（出廠 115200）**：

```toml
[serial]
port = "COM29"
baud = 115200
```

**設定已存 flash，只讀資料**：

```bash
python run_um982.py --no-init
```

**改完 `commands` 後存一次 flash，之後不再存**：

```bash
python run_um982.py --save-config   # 只跑這一次
```

**config 開了 dump，這次不想要**：

```bash
python run_um982.py --no-dump
```

---

## 固定基線配置（1.5 m 長棍）

兩根天線剛性裝在 1.5 m 的桿上時，在 `um982.toml` 的 `[init] commands` 中把範本裡註解掉的 `CONFIG HEADING LENGTH` 打開：

```toml
[init]
commands = [
    "UNLOG",
    "MODE ROVER UAV",
    "CONFIG HEADING FIXLENGTH",
    "CONFIG HEADING LENGTH 150 3",   # baseline 150 cm, tolerance 3 cm
    "CONFIG SMOOTH HEADING 0",
    "GPGGA 0.05",
    "GPRMC 0.05",
    "GPTHS 0.05",
    "GPVTG 0.05",
    "GPGSV 1",
    "GPGSA 1",
    "GPGST 1",
    "KSXT 0.05",
]
```

然後跑一次 `--save-config` 寫進 flash。

| 項目 | 說明 |
|---|---|
| 指令格式 | `CONFIG HEADING LENGTH <基線> <容差>`，單位 cm（手冊 R1.15 §4.18 Table 4-21）。**R4.10Build13495 實測必須兩個參數都帶**，只帶一個會回 `PARSING FAILED GRAMMAR ERROR,This cmd need two paras,and the second para > 0!` |
| 填多少 | **ANT1 與 ANT2 相位中心的距離**，不是桿長。最可靠的來源是模組自己解出的基線：室外航向鎖定後讀一次 `UNIHEADINGA`，裡面有基線長度欄。兩根天線同型號、同朝向安裝（接頭朝同一邊），相位中心偏差才會互相抵消 |
| 容差 | 必須 > 0，手冊範例是 3（cm）。基線填錯或容差太緊，航向可能一直鎖不上，比沒設更糟，所以先拿 `UNIHEADINGA` 的實測值再寫 |
| 有沒有吃進去 | 啟動時印 `Init 4/13 CONFIG HEADING LENGTH 150 3 -> response: OK`；被拒會直接 `Init failed: ...` 並 exit 1，附模組原話 |
| 航向定義 | 真北順時針轉到 **ANT1→ANT2 連線** 的角度。桿子若橫裝（左右向），`YAW` 與車頭方向差 ±90°，需在下游自己補償 |
| 精度預期 | 角度誤差 ≈ 相位誤差 ÷ 基線長。廠規 0.1° @ 1 m 基線，1.5 m 理論約 0.07°；多路徑、桿子形變會吃掉一部分 |

---

## 輸出說明

### 狀態行

一行原地刷新（`\r` 覆寫，補空白到目前最長那一行的長度，蓋掉上一行的殘留）：

```
UTC 06:21:33.000  RTK FIXED  LAT 25.062431  LON 121.581187  ALT_MSL 45.1 m  ALT_HAE 62.6 m  SATS 28  HDOP 0.7  VDOP 1.0  YAW 123.5  HDG FIXED  ANT2 21
```

一行約 145 字元。終端比這窄會折行，折行後 `\r` 只回到最後一行開頭，畫面變成一行行往下刷 —— 把終端拉寬即可。

| 欄位 | 單位 | 來源 | 顯示 `--` 的原因 |
|---|---|---|---|
| `UTC` | HH:MM:SS.sss | GGA 第 1 欄 | 還沒收到 GGA |
| `RTK` | **ANT1 相對基站**的解算品質：`NONE`／`SINGLE`／`DGPS`／`PPS`／`FIXED`／`FLOAT`／`DR`／`MANUAL`／`SIM` | GGA 第 6 欄（手冊表 7-4：4＝固定、5＝浮點） | 還沒收到 GGA |
| `LAT` / `LON` | 度（十進位，南緯／西經為負），6 位小數 | GGA 第 2–5 欄 | 解算品質 0（無定位），舊座標會被清掉 |
| `ALT_MSL` | m，海拔高 | GGA 第 9 欄 | 無定位 |
| `ALT_HAE` | m，WGS84 橢球高＝海拔高＋大地水準面差距 | GGA 第 9＋11 欄 | 無定位，或模組沒輸出第 11 欄 |
| `SATS` | 顆，解算使用的衛星數 | GGA 第 7 欄 | 還沒收到 GGA |
| `HDOP` | — | GGA 第 8 欄，GSA 到了會覆蓋 | 還沒收到 GGA／GSA |
| `VDOP` | — | GSA | 還沒收到 GSA（1 Hz，啟動後最多等 1 秒） |
| `YAW` | 度，真北順時針，ANT1→ANT2 | THS | THS 狀態 `V`：只接 ANT1、heading 未收斂或遮擋，**不是故障**；看 `HDG`、`ANT2` 判斷是哪一種 |
| `HDG` | **ANT1 相對 ANT2** 的航向解算品質：`NONE`／`SINGLE`／`FLOAT`／`FIXED` | KSXT 第 11 欄（手冊表 7-107 的 ID 12：3＝固定、2＝浮點，**跟 GGA 編號不同**） | 還沒收到 KSXT；`commands` 拿掉 `KSXT` 就一直是 `--` |
| `ANT2` | 顆，從天線參與解算的衛星數 | KSXT 第 12 欄（手冊 ID 13） | 同 `HDG` |

表裡沒列的品質碼（新固件可能新增）原樣顯示成 `Q<數字>`，不猜名字。

無定位時 `UTC`、`SATS`、`HDOP` 照常更新：GGA 在沒定位時仍帶時間和衛星數。

### `RTK` 與 `HDG` 是兩套獨立的差分

| | `RTK` | `HDG` |
|---|---|---|
| 差分的兩端 | ANT1 ↔ **基站**（RTCM 改正數） | ANT1 ↔ **ANT2**（模組內部，移動基線） |
| 需要什麼 | 外部基站或 NTRIP 的 RTCM 改正數送進模組 | 兩根天線都看得到星，不需要基站 |
| 決定什麼 | 位置精度（單點約米級，固定解約厘米級） | 航向能不能出、準不準 |
| 本驅動 | **不轉發 RTCM**，沒有外部改正數時 `RTK` 停在 `SINGLE`（或 SBAS 的 `DGPS`），正常 | 開機即可解算 |

兩者互不依賴：手冊表 7-107 的 KSXT 範例就是位置品質 1（單點）、航向品質 3（固定）。所以 `RTK SINGLE` 但 `HDG FIXED` 是常態，航向照樣可用。

| 看到 | 意思 |
|---|---|
| `YAW --  HDG NONE  ANT2 0` | ANT2 一顆星都沒解到：天線線材、接頭或遮擋，先查 ANT2 |
| `YAW --  HDG NONE  ANT2 >0` | ANT2 有星但航向還沒解出來：剛開機或剛遮擋後在收斂 |
| `YAW 123.4  HDG FLOAT` | 航向有值但模糊度沒固定，精度明顯差於 `FIXED`，別拿來當真值 |
| `YAW 123.4  HDG FIXED` | 航向固定解，可用 |

### 其他訊息

| 訊息 | 意義 |
|---|---|
| `Config: <path>` | 實際載入的設定檔（或 `not found, using defaults`） |
| `Config error: <path>: serial.buad: unknown key` | 設定錯誤，冒號後指出哪個 key；exit 1 |
| `Warning: save_config ignored because init is off.` | `save_config` 和 `--no-init` 同時出現 |
| `Failed to open COM29: ...` | 埠不存在、被佔用或權限不足；exit 1 |
| `Init 3/12 CONFIG HEADING FIXLENGTH -> response: OK` | 第 3／共 12 條指令被模組接受 |
| `Init failed: CONFIG MODE UAV: response: PARSING FAILED MISSING FIELD,` | 模組拒收這條指令，冒號後是模組原話；後面的指令不再送，exit 1。之前的指令已生效 |
| `Init failed: UNLOG: no reply within 5.0 s; check the baud rate` | 等滿 `reply_timeout_s` 沒有回覆，九成是波特率不對；exit 1 |
| `No valid NMEA yet; check the baud rate (module default is 115200).` | 連續 `no_data_warn_after_s` 秒沒有有效語句 |
| `DUMP KSXT: $KSXT,...` | `dump` 開啟時，每種未解析語句印一次 |
| `Read failed: no data after 10 reads; check the cable` | 連續 `empty_read_limit` 次零位元組；exit 1 |
| `Stopped.` | Ctrl+C；exit 0 |

---

## Python API

```python
from gnss_drivers.um982 import UM982

with UM982("COM29") as receiver:
    for progress_text in receiver.apply_init_commands():
        print(progress_text)
    for fix in receiver.read_fixes():
        print(fix.lat_deg, fix.lon_deg, fix.yaw_deg)
```

### `UM982(port_name, baud_rate=230400, read_timeout_s=1.0, empty_read_limit=10, init_timing=None)`

| 參數 | 說明 |
|---|---|
| `port_name` | 序列埠名，Windows `COM10+` 自動轉路徑 |
| `baud_rate` | 鮑率，8N1、無流控固定 |
| `read_timeout_s` | 單次讀取逾時 |
| `empty_read_limit` | `read_fixes()` 連續空讀上限，`0`＝不限 |
| `init_timing` | `InitTiming`；`None`＝用預設時序 |

建構時**不開埠**，`open()` 或 `with` 才開：開埠失敗不會留下一個關不掉的半成品物件。

| 方法 | 說明 |
|---|---|
| `open()` / `close()` / `with` | 開關序列埠，`close()` 可重複呼叫 |
| `send_command(command_text)` | 送一條指令，自動補 `\r\n` |
| `apply_init_commands(save_to_flash=False, init_commands=None)` | **generator**，每送一條 yield 一行進度。**不迭代就一條都不會送**。`init_commands=None` 用 `MODULE_INIT_COMMANDS`；`save_to_flash=True` 在尾巴加 `SAVECONFIG`。任一條被拒或逾時沒回覆就拋 `UM982InitError`，後面的不再送，所以前面失敗時 `SAVECONFIG` 不會寫入 |
| `read_sentence()` | 讀一行，逾時回 `None` |
| `read_fixes()` | 無限迴圈，每次 GGA／GSA／THS／KSXT 更新後 yield。**每次 yield 的是同一個 `GnssFix` 物件**（它代表接收機當前狀態），要保存快照用 `dataclasses.replace(fix)` |
| `fix` | 目前的 `GnssFix` |

`UM982ReadError`：埠未開就讀，或 `read_fixes()` 連續空讀達上限。

`UM982InitError`：初始化指令被模組拒收（訊息帶模組原話），或 `reply_timeout_s` 內沒有回覆。

### `InitTiming(cmd_delay_s=0.08, saveconfig_settle_s=0.35, reply_timeout_s=5.0, drain_read_timeout_s=0.05)`

欄位意義同 `[init]` 段同名 key。

### 在自己的腳本重用 config

```python
from gnss_drivers.um982 import UM982
from gnss_drivers.um982.config import load_config_file, validate_config

config, config_note = load_config_file("um982.toml")
validate_config(config)
receiver = UM982(
    config.port,
    baud_rate=config.baud,
    read_timeout_s=config.read_timeout_s,
    empty_read_limit=config.empty_read_limit,
    init_timing=config.init_timing(),
)
```

`load_config_file(None)` 走預設路徑規則；`UM982Config` 欄位名與 `--` 參數同名（去掉 `--`、`-` 換 `_`），`[init]` 段的欄位加 `init_` 前綴。

### `GnssFix` 欄位

| 欄位 | 型別 | 單位 | 來源 |
|---|---|---|---|
| `utc_text` | `Optional[str]` | `HH:MM:SS.sss` | GGA |
| `lat_deg` / `lon_deg` | `Optional[float]` | 度，南／西為負 | GGA，無定位時 `None` |
| `alt_msl_m` | `Optional[float]` | m | GGA，無定位時 `None` |
| `alt_hae_m` | `Optional[float]` | m | GGA 第 9＋11 欄，任一缺就 `None` |
| `sats_used` | `Optional[int]` | 顆 | GGA |
| `hdop` / `vdop` | `Optional[float]` | — | GGA／GSA |
| `yaw_deg` | `Optional[float]` | 度 | THS，狀態 `V` 時 `None` |
| `position_quality` | `Optional[int]` | GGA 品質碼 | GGA 第 6 欄，原始數字；名稱見 `fix.POSITION_QUALITY_NAMES` |
| `heading_quality` | `Optional[int]` | KSXT 航向品質碼 | KSXT 第 11 欄，原始數字；名稱見 `fix.HEADING_QUALITY_NAMES`。**編號跟 `position_quality` 不同，不能互相比較** |
| `ant2_sats_used` | `Optional[int]` | 顆 | KSXT 第 12 欄 |

### 模組常數（`driver.py`，即上述參數的預設值）

| 常數 | 值 | 對應參數 |
|---|---|---|
| `DEFAULT_BAUD_RATE` | 230400 | `serial.baud` |
| `DEFAULT_READ_TIMEOUT_S` | 1.0 | `serial.read_timeout_s` |
| `EMPTY_READ_LIMIT` | 10 | `run.empty_read_limit` |
| `INIT_CMD_DELAY_S` | 0.08 | `init.cmd_delay_s` |
| `INIT_SAVECONFIG_SETTLE_S` | 0.35 | `init.saveconfig_settle_s` |
| `INIT_REPLY_TIMEOUT_S` | 5.0 | `init.reply_timeout_s` |
| `INIT_DRAIN_READ_TIMEOUT_S` | 0.05 | `init.drain_read_timeout_s` |
| `MODULE_INIT_COMMANDS` | 見下表 | `init.commands` |

`config.py` 另有 `NO_DATA_WARN_AFTER_S = 5.0`（`run.no_data_warn_after_s`）與 `DEFAULT_CONFIG_PATH = "um982.toml"`。

---

## 裝置說明

### 接線

- **ANT1＝主天線**，決定位置解；**ANT2＝從天線**，與 ANT1 共同決定航向。
- 兩根天線必須**剛性固連**，基線長度不可變動 —— 這是 `CONFIG HEADING FIXLENGTH` 能成立的前提。
- 基線越長角精度越高（角度誤差 ≈ 相位誤差 ÷ 基線長），但太長不利安裝，實務上取捨。
- 只接 ANT1 時 THS 會回報 `V`（無效），`YAW` 顯示 `--`，**這是正確行為不是故障**。

### 序列埠參數

`230400 8N1`，無流控。

> ⚠️ **模組出廠預設是 115200**。沒改過的新模組要先用 `baud = 115200` 連上，用序列埠終端下 `CONFIG COM1 230400` 改速率後才能用預設參數連（本 CLI 不提供任意指令送出）。腳本在連續 `no_data_warn_after_s` 秒收不到有效 NMEA 時會提示這件事。

### 預設初始化指令（`MODULE_INIT_COMMANDS`）

寫法依 Unicore《Reference Commands Manual for N4 High Precision Products》R1.15，並在 UM982 R4.10Build13495 上逐條實測回 `response: OK`。

| 指令 | 參數意義 | 作用 | 不下的後果 | 手冊 |
|---|---|---|---|---|
| `UNLOG` | — | 停掉收到指令那個埠的全部週期輸出 | 新舊清單疊加而非取代，頻寬爆掉且每次上電行為不同 | §8.4 |
| `MODE ROVER UAV` | 動態模型 | 無人機動態（UM982 出廠預設就是它） | flash 裡存了別的模式（如 `SURVEY`）的模組，上電行為跟別台不一樣 | §3.4 |
| `CONFIG HEADING FIXLENGTH` | 航向模式 | 宣告雙天線基線長度固定（出廠預設） | 被改成 `STATIC`／`LOWDYNAMIC`／`TRACTOR` 等其他場景的模式；論壇反映 `TRACTOR` 對航向平均很重 | §4.18 |
| `CONFIG SMOOTH HEADING 0` | 平滑歷元數，0＝關 | 關閉航向平滑（出廠預設關） | 有些廠家／網上流傳的配置存了 `SMOOTH HEADING 10`，AgOpenGPS 論壇有人因此航向滯後約 1 s | §4.49 |
| `GPGGA`／`GPRMC`／`GPTHS`／`GPVTG 0.05` | 輸出週期 0.05 s＝**20 Hz** | 主資料流 | 控制迴路吃不到足夠更新率 | §7 |
| `GPGSV`／`GPGSA`／`GPGST 1` | 輸出週期 1 s＝**1 Hz** | 診斷流 | 見下方「頻寬」 | §7 |
| `KSXT 0.05` | 輸出週期 0.05 s＝20 Hz | 廠商專有句 | 目前未解析，見「已知限制」 | §7.5.49 |
| `SAVECONFIG` | — | 寫入 flash | 不在清單內，只由 `save_config` 附加；見下方說明 | §8.3 |

- **日誌請求的寫法**：`GPxxx <週期>`。手冊規定**只能用 GP 前綴**，不能寫 `GN`／`GB`／`GL`／`GA`，但輸出照樣帶各星座的 talker（`$GNGGA`、`$GBGSV`…）。`GPGSV 1` 在 `UNILOGLIST` 裡顯示成 `GNGSV COM1 1`，五個星座（GP／GB／GA／GL／GQ）都會吐。不帶埠號＝輸出到收到指令的那個埠，換接 COM2 不用改指令。數字是週期（秒），不是頻率；`ONCHANGED` 只適用部分 Unicore 格式日誌，NMEA 語句不能用。
- **`UNLOG` 為什麼必須第一條**：設定存在 flash，上電會自動恢復上次的輸出清單。不先清空就下日誌請求，等於在舊清單上疊加 —— 你以為只開了 8 種語句，實際可能吐十幾種。症狀是 checksum 偶發失敗、資料跳拍，而且**每次上電表現不一樣**，除錯毫無再現性。
- **頻寬：為什麼診斷語句必須 1 Hz**：230400 baud 8N1 ≈ 23 KB/s。NMEA 4.10 的 GSV 是「**每星座 × 每頻點**」各一組（室內只看到 1 顆 GPS 星也要 3 句 GPGSV），開闊天空下每輪估計 30–40 句、約 2.5 KB，10 Hz 光 GSV 就約 25 KB/s。

  | 輸出清單 | 吞吐 | 佔 230400 |
  |---|---|---|
  | 舊 flash 清單（GSV 等 10 Hz、KSXT／HPR 20 Hz），室內 3 顆星 | 實測 8.1 KB/s | 35% |
  | 同上，開闊天空 | 估算 ~30 KB/s | **~130%，超載** |
  | 本預設清單，室內 | 實測 7.9 KB/s | 34% |
  | 本預設清單，開闊天空 | 估算 ~11.5 KB/s | ~50% |

  超載時模組不報錯，輸出在發送緩衝裡排隊，表現為**所有語句一起固定滯後好幾秒**，最先被察覺的通常是轉動後的航向。DOP 與衛星清單是給人看的，1 Hz 綽綽有餘。
- **`SAVECONFIG` 為什麼預設關閉、且禁止寫進 `commands`**：NOR flash 寫入壽命典型 10K–100K 次。設定下過一次就存住了，日常跑腳本只需要 `UNLOG` + 日誌請求（揮發性設定本來就要重下）。每次都寫、而且寫的內容一模一樣，純粹消耗壽命。寫爛的症狀是 `SAVECONFIG` 靜默失敗或上電設定丟失 —— 屆時你不會聯想到 flash 壽命。`SAVECONFIG` 排在最後，前面任何一條被拒都會中止，不會把半套配置寫進 flash。

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
| `KSXT` | 廠商專有句：位置＋航向＋速度＋位置／航向解算品質＋兩根天線的衛星數 | ✅ 部分解析（只取航向品質、ANT2 衛星數；航向和位置仍以 THS、GGA 為準） |

### 已知限制

- **`KSXT` 只解析了航向品質和 ANT2 衛星數**（欄位定義照手冊 R1.15 表 7-107，測試用的是實機抓的語句）。它的航向、位置、速度沒用，因為 THS、GGA 已經給了，兩句搶同一個欄位只會互相覆蓋。從 `commands` 拿掉 `KSXT` 可省約 26 kbps，代價是 `HDG`、`ANT2` 變成 `--`。
- **`ALT_HAE` 依賴 GGA 第 11 欄的大地水準面差距**，模組未輸出該欄時顯示 `--`（`ALT_MSL` 仍正常）。實測本模組有輸出，差值約 18.9 m。
- **雙天線 heading 需要收斂時間**，冷啟動或遮擋後重新收斂期間 THS 回 `V`。
- **基線長度**：`FIXLENGTH` 只宣告「長度固定」，不帶長度值。手冊另有 `CONFIG HEADING LENGTH <基線> <容差>`，預設清單**不含**這條（基線是台架屬性，不是模組屬性），各台架在自己的 `um982.toml` 加，見「固定基線配置」。
- **航向延遲修正尚未在開闊天空下驗收**：見下方「排障」的案例，修正後的室外負載是估算值。

---

## 排障

### 查模組 flash 裡實際存了什麼

`commands` 寫了什麼不代表模組在跑什麼。以下指令只讀、不改配置：

| 指令 | 看什麼 |
|---|---|
| `UNILOGLIST` | 每個埠實際在跑的日誌與週期。跟 `commands` 對不上，就是有指令沒生效 |
| `CONFIG` | 全部配置。找 `$CONFIG,SMOOTH`（航向平滑）、`$CONFIG,HEADING`（航向模式）、`$CONFIG,COM1`（波特率） |
| `MODE` | 動態模型，例：`MODE ROVER UAV` |
| `VERSIONA` | 固件版本，例：`R4.10Build13495` |

本 CLI 不提供任意指令送出。回覆夾在 NMEA 串流裡，認 `$command,`、`$CONFIG,`、`#`、`<` 開頭的行：

```bash
python3 -c "import serial,time; p=serial.Serial('/dev/ttyGNSS',230400,timeout=1); p.write(b'UNILOGLIST\r\n'); time.sleep(1.5); print(p.read(p.in_waiting).decode(errors='ignore'))" | grep -E '^(\$command|\$CONFIG|#|<)'
```

指令回覆格式（R4.10Build13495 實測）：

| 情況 | 回覆 |
|---|---|
| 接受 | `$command,UNLOG,response: OK*01` |
| 指令不存在 | `$command,UNLOGCOM,response: PARSING FAILED NO MATCHING FUNC  UNLOGCOM*05` |
| 參數不對 | `$command,CONFIG MODE UAV,response: PARSING FAILED MISSING FIELD,*48` |

### 案例：轉動後航向滯後約 3 秒（2026-10）

| 項目 | 內容 |
|---|---|
| 現象 | 1.5 m 基線，轉動天線桿後 `YAW` 約 3 s 才跟上 |
| 查到 | 舊預設 `commands` 裡的 `UNLOGCOM`、`CONFIG MODE UAV`、`CONFIG NMEA ... ONCHANGED` 全被模組拒收（`PARSING FAILED`），而舊驅動每條只讀 3 行找回覆，拒收的回覆前面隔了 20–30 行 NMEA，一條都沒撈到。模組一直跑 flash 舊清單：GGA／GSA／GST／GSV／RMC／VTG／THS 10 Hz，KSXT／HPR 20 Hz |
| 判斷 | 開闊天空下 GSV 10 Hz 讓輸出超過 230400 容量（見「頻寬」），發送緩衝排隊，所有語句一起滯後。3 s 對應約 64 KB 緩衝，手冊沒寫緩衝大小，這一環是推斷；當時天線在室內，未在室外復現 |
| 已排除 | 航向平滑（`CONFIG` 回讀沒有 `SMOOTH` 行）、動態模型（`MODE ROVER UAV`）、航向模式（`FIXLENGTH`）、主機端讀取太慢（主機跟不上的特徵是延遲一直漲，不是固定 3 s） |
| 修正 | 指令改用手冊寫法；初始化改成按時間等回覆，被拒或沒回覆就 `Init failed` 退出；跑一次 `--save-config` 把 flash 舊清單換掉 |
| 對照 | ArduPilot 對 UM982 硬編碼的延遲是 0.14 s（飛行日誌實測） |

### 量串口負載與延遲

拿 GGA 裡的 UTC 對主機收到的時刻，同時算吞吐。只讀，不送任何指令：

```python
import datetime
import sys
import time

import serial

port_name = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyGNSS"
measure_window_s = 5.0
port = serial.Serial(port_name, 230400, timeout=0.1)
port.reset_input_buffer()
started_at_s = time.monotonic()
total_bytes = 0
pending_bytes = b""
gga_age_ms = []
while time.monotonic() - started_at_s < measure_window_s:
    received_bytes = port.read(4096)
    arrived_utc = datetime.datetime.now(datetime.timezone.utc)
    total_bytes += len(received_bytes)
    pending_bytes += received_bytes
    *complete_lines, pending_bytes = pending_bytes.split(b"\n")
    for raw_line in complete_lines:
        fields = raw_line.decode("ascii", "replace").split(",")
        if fields[0] != "$GNGGA" or len(fields[1]) < 6:
            continue
        utc_text = fields[1]
        sentence_utc = arrived_utc.replace(
            hour=int(utc_text[0:2]),
            minute=int(utc_text[2:4]),
            second=int(utc_text[4:6]),
            microsecond=int(float("0" + utc_text[6:]) * 1e6),
        )
        age_s = (arrived_utc - sentence_utc).total_seconds()
        gga_age_ms.append(age_s * 1000.0)
port.close()
bytes_per_s = total_bytes / measure_window_s
print(f"{bytes_per_s:.0f} B/s, {bytes_per_s / 23040 * 100:.0f}% of 230400")
gga_age_ms.sort()
if gga_age_ms:
    print(f"GGA age median {gga_age_ms[len(gga_age_ms) // 2]:.0f} ms")
```

- **主機時鐘不可全信**：WSL 台架實測主機比 NTP 快約 100 ms，timesyncd 還修過 -484 ms 的漂移。所以 GGA 年齡只拿來**相對比較**：本台架室內約 460 ms；超載排隊時應漲到秒級，正常時回到這個基線附近。
- **吞吐**：開闊天空下超過 ~90% 就是快超載了，應該先砍輸出清單，而不是先加波特率。
- **模組自報延遲**：Unicore 格式日誌（`#` 開頭，如 `UNIHEADINGA`）的表頭最後一欄是「輸出時刻 − 信號接收時刻」，單位 ms（手冊 §7.5.1）。它能把模組內部延遲跟串口排隊分開。
