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
| `drain_lines_max` | `--init-drain-lines-max` | int | `3` | 每條指令後最多讀幾行找回覆。模組同時在吐 NMEA，回覆可能被擠出窗口，此時顯示 `no response seen` |
| `drain_read_timeout_s` | `--init-drain-read-timeout-s` | float | `0.05` | 讀回覆時的單行逾時，必須 > 0 |
| `commands` | **僅 config** | list[str] | 見下表 | 啟動時依序送出的指令。不能為空、不能有空白項、**不能含 `SAVECONFIG`**（改用 `run.save_config`） |

`commands` 不開放命令行：每條指令都含空格，塞進命令行要逐條加引號，錯一個引號整條就拆散。

`commands` 會**整份取代**預設清單，不是追加。要加一條，從範本複製整份再改。第一條請保持 `UNLOGCOM`（原因見下表）。

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

兩根天線剛性裝在 1.5 m 的桿上時，在 `um982.toml` 的 `[init] commands` 中、`CONFIG HEADING FIXLENGTH` 下面加一行 `CONFIG HEADING LENGTH`：

```toml
[init]
commands = [
    "UNLOGCOM",
    "CONFIG MODE UAV",
    "CONFIG HEADING FIXLENGTH",
    "CONFIG HEADING LENGTH 150",   # ANT1-ANT2 phase-centre distance, cm
    "CONFIG NMEA GGA ONCHANGED 0.05",
    "CONFIG NMEA RMC ONCHANGED 0.05",
    "CONFIG NMEA THS ONCHANGED 0.05",
    "CONFIG NMEA VTG ONCHANGED 0.05",
    "CONFIG NMEA GSV ONCHANGED 1",
    "CONFIG NMEA GSA ONCHANGED 1",
    "CONFIG NMEA GST ONCHANGED 1",
    "KSXT 0.05",
]
```

然後跑一次 `--save-config` 寫進 flash。

| 項目 | 說明 |
|---|---|
| 指令格式 | Unicore N4 指令手冊：`CONFIG HEADING LENGTH [參數1] [參數2]`，參數 1＝固定基線長度、參數 2＝長度容差，單位 cm，兩者都是選填 |
| 填多少 | **ANT1 與 ANT2 相位中心的距離**，不是桿長。天線沒裝在桿的兩端就要實量中心到中心。兩根天線同型號、同朝向安裝（接頭朝同一邊），相位中心偏差才會互相抵消 |
| 容差（參數 2） | 先**不帶**。手冊 R1.15 改過這個參數的取值範圍，沒對照你韌體對應版本的手冊就亂填，模組會拒收 |
| 有沒有吃進去 | 看啟動的 `Init 3/12 CONFIG HEADING LENGTH 150 -> response: OK`。`no response seen` 不代表失敗（回覆可能被 NMEA 擠出窗口），可調大 `drain_lines_max` 再看；回 `OK` 以外的字串才是被拒 |
| 航向定義 | 真北順時針轉到 **ANT1→ANT2 連線** 的角度。桿子若橫裝（左右向），`YAW` 與車頭方向差 ±90°，需在下游自己補償 |
| 精度預期 | 角度誤差 ≈ 相位誤差 ÷ 基線長。廠規 0.1° @ 1 m 基線，1.5 m 理論約 0.07°；多路徑、桿子形變會吃掉一部分 |

⚠️ 本驅動目前在**沒接板**的環境下完成，`$command,...,response: OK` 回覆格式與 `LENGTH` 參數是依手冊撰寫，**第一次上台架要對照實際回覆確認**。

---

## 輸出說明

### 狀態行

一行原地刷新（`\r` 覆寫）：

```
UTC 06:21:33.000  LAT 25.062431  LON 121.581187  ALT_MSL 45.1 m  ALT_HAE 62.6 m  SATS 28  HDOP 0.7  VDOP 1.0  YAW 123.5
```

| 欄位 | 單位 | 來源 | 顯示 `--` 的原因 |
|---|---|---|---|
| `UTC` | HH:MM:SS.sss | GGA 第 1 欄 | 還沒收到 GGA |
| `LAT` / `LON` | 度（十進位，南緯／西經為負），6 位小數 | GGA 第 2–5 欄 | 解算品質 0（無定位），舊座標會被清掉 |
| `ALT_MSL` | m，海拔高 | GGA 第 9 欄 | 無定位 |
| `ALT_HAE` | m，WGS84 橢球高＝海拔高＋大地水準面差距 | GGA 第 9＋11 欄 | 無定位，或模組沒輸出第 11 欄 |
| `SATS` | 顆，解算使用的衛星數 | GGA 第 7 欄 | 還沒收到 GGA |
| `HDOP` | — | GGA 第 8 欄，GSA 到了會覆蓋 | 還沒收到 GGA／GSA |
| `VDOP` | — | GSA | 還沒收到 GSA（1 Hz，啟動後最多等 1 秒） |
| `YAW` | 度，真北順時針，ANT1→ANT2 | THS | THS 狀態 `V`：只接 ANT1、heading 未收斂或遮擋，**不是故障** |

無定位時 `UTC`、`SATS`、`HDOP` 照常更新：GGA 在沒定位時仍帶時間和衛星數。

### 其他訊息

| 訊息 | 意義 |
|---|---|
| `Config: <path>` | 實際載入的設定檔（或 `not found, using defaults`） |
| `Config error: <path>: serial.buad: unknown key` | 設定錯誤，冒號後指出哪個 key；exit 1 |
| `Warning: save_config ignored because init is off.` | `save_config` 和 `--no-init` 同時出現 |
| `Failed to open COM29: ...` | 埠不存在、被佔用或權限不足；exit 1 |
| `Init 3/11 CONFIG HEADING FIXLENGTH -> response: OK` | 第 3／共 11 條指令與模組回覆；`no response seen`＝讀取窗口內沒看到回覆 |
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
| `apply_init_commands(save_to_flash=False, init_commands=None)` | **generator**，每送一條 yield 一行進度。**不迭代就一條都不會送**。`init_commands=None` 用 `MODULE_INIT_COMMANDS`；`save_to_flash=True` 在尾巴加 `SAVECONFIG` |
| `read_sentence()` | 讀一行，逾時回 `None` |
| `read_fixes()` | 無限迴圈，每次 GGA／GSA／THS 更新後 yield。**每次 yield 的是同一個 `GnssFix` 物件**（它代表接收機當前狀態），要保存快照用 `dataclasses.replace(fix)` |
| `fix` | 目前的 `GnssFix` |

`UM982ReadError`：埠未開就讀，或 `read_fixes()` 連續空讀達上限。

### `InitTiming(cmd_delay_s=0.08, saveconfig_settle_s=0.35, drain_lines_max=3, drain_read_timeout_s=0.05)`

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

### 模組常數（`driver.py`，即上述參數的預設值）

| 常數 | 值 | 對應參數 |
|---|---|---|
| `DEFAULT_BAUD_RATE` | 230400 | `serial.baud` |
| `DEFAULT_READ_TIMEOUT_S` | 1.0 | `serial.read_timeout_s` |
| `EMPTY_READ_LIMIT` | 10 | `run.empty_read_limit` |
| `INIT_CMD_DELAY_S` | 0.08 | `init.cmd_delay_s` |
| `INIT_SAVECONFIG_SETTLE_S` | 0.35 | `init.saveconfig_settle_s` |
| `INIT_DRAIN_LINES_MAX` | 3 | `init.drain_lines_max` |
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

| 指令 | 參數意義 | 作用 | 不下的後果 |
|---|---|---|---|
| `UNLOGCOM` | — | 清掉當前埠既有的週期輸出 | 新舊設定疊加而非取代，頻寬爆掉且每次上電行為不同 |
| `CONFIG MODE UAV` | 動態模型 | 設為無人機 | 快速運動時濾波器把真實運動當雜訊壓掉，位置／航向滯後 |
| `CONFIG HEADING FIXLENGTH` | 基線模式 | 宣告雙天線基線長度固定 | 模糊度搜索空間變大，heading 收斂慢，THS 長時間回 `V` |
| `CONFIG NMEA GGA/RMC/THS/VTG ONCHANGED 0.05` | 輸出週期 0.05 s＝**20 Hz** | 主資料流 | 控制迴路吃不到足夠更新率 |
| `CONFIG NMEA GSV/GSA/GST ONCHANGED 1` | 輸出週期 1 s＝**1 Hz** | 診斷流 | 全開 20 Hz 約吃掉 70% 埠容量，buffer 滿會吐截斷語句 |
| `KSXT 0.05` | 輸出週期 0.05 s＝20 Hz | 廠商專有句 | 目前未解析，見「已知限制」 |
| `SAVECONFIG` | — | 寫入 flash | 不在清單內，只由 `save_config` 附加；見下方說明 |

- **`UNLOGCOM` 為什麼必須第一條**：設定存在 flash，上電會自動恢復上次的輸出清單。不先清空就下 `CONFIG NMEA`，等於在舊清單上疊加 —— 你以為只開了 7 種語句，實際可能吐十幾種。症狀是 checksum 偶發失敗、資料跳拍，而且**每次上電表現不一樣**，除錯毫無再現性。
- **為什麼診斷語句降到 1 Hz**：230400 baud ÷ 10 bit/byte ≈ 23 KB/s。若全部 20 Hz，約 20 × 800 bytes ≈ 16 KB/s，逼近容量 70%。GSV 尤其肥（11 顆可見衛星要 3 句），20 Hz 純屬浪費。DOP 與衛星清單是給人看的，1 Hz 綽綽有餘。
- **`SAVECONFIG` 為什麼預設關閉、且禁止寫進 `commands`**：NOR flash 寫入壽命典型 10K–100K 次。設定下過一次就存住了，日常跑腳本只需要 `UNLOGCOM` + `CONFIG NMEA`（揮發性設定本來就要重下）。每次都寫、而且寫的內容一模一樣，純粹消耗壽命。寫爛的症狀是 `SAVECONFIG` 靜默失敗或上電設定丟失 —— 屆時你不會聯想到 flash 壽命。

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

- **`KSXT` 已開啟輸出但尚未解析**，20 Hz × 約 130 bytes ≈ 26 kbps 白白浪費。刻意保留是為了能用 `dump` 抓到實物語句，照著寫 parser；欄位定義必須對照官方手冊，猜不得。確定不用就從 `commands` 移除。
- **`ALT_HAE` 依賴 GGA 第 11 欄的大地水準面差距**，模組未輸出該欄時顯示 `--`（`ALT_MSL` 仍正常）。實測本模組有輸出，差值約 18.9 m。
- **雙天線 heading 需要收斂時間**，冷啟動或遮擋後重新收斂期間 THS 回 `V`。
- **基線長度**：`FIXLENGTH` 只宣告「長度固定」，不帶長度值。手冊另有 `CONFIG HEADING LENGTH` 設定實際長度與容差，預設清單**不含**這條（基線是台架屬性，不是模組屬性），各台架在自己的 `um982.toml` 加，見「固定基線配置」。
- **指令回覆格式待台架確認**：`-> response: OK` 依 Unicore N4 的 `$command,<指令>,response: OK*xx` 格式匹配，尚未對實機驗證。
