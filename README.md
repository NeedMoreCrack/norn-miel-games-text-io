# Norn/Miel/Cybele 遊戲文本提取、翻譯與音效修補工具

本工具包含三支程式，分別處理文本提取／回填、Ollama 翻譯與 XP3 音效修補：

| 程式 | 功能 |
| --- | --- |
| `nornmiel_text_io.py` | 從 `scenario.ks` 提取 TSV，或將 TSV 譯文替換回腳本 |
| `translate_tsv.py` | 呼叫 Ollama 批次翻譯 TSV，支援繁體轉換、續跑、定時休息與存檔重試 |
| `nornmiel_audio_xp3_patcher.py` | 自動解包 XP3、修改指定音效與回想音訊控制、重新封包；缺少打包器時自動下載 |

## 選擇要執行的流程

- **文字翻譯**：準備解包後的 `scenario.ks` → 提取 TSV → Ollama 翻譯 → 回填腳本。回填工具不會自動將腳本打包回 XP3。
- **音效修補**：執行 `nornmiel_audio_xp3_patcher.py`，由程式自動解包、修改與重新封包。不需要 TSV、Ollama 或 OpenCC，操作詳見下方「XP3 音效自動修補」。

兩種流程可分別執行。請使用與該遊戲版本相符的原始腳本及封包；音效修補器會檢查目標腳本結構，不能保證適用於所有 Norn/Miel/Cybele 遊戲。

## 文字翻譯流程：解包、提取與回填

文字提取／回填工具須先準備解包後的腳本。可參考：[xp3-pack-unpack 解包工具](https://github.com/lxl66566/xp3-pack-unpack)。

解包後，將 `data\scenario\scenario.ks` 放到 `nornmiel_text_io.py` 與 `translate_tsv.py` 的相同目錄，並另外保留一份未修改的原始腳本備份。實際路徑依解包輸出而定；解包工具的操作方式請參閱該專案說明。自動下載打包器目前屬於音效修補器的功能，不是這兩支文本程式的功能。

### A. 提取原文

在工具目錄執行：

```powershell
python .\nornmiel_text_io.py
```

選擇 `1`。程式會擷取 `@name` 指令下一行的文字，在 `scenario.ks` 同目錄產生 `Translation-001.tsv`、`Translation-002.tsv` 等檔案，每份最多 50 筆。

首次提取完成後，建立 `original` 資料夾並移入根目錄下剛產生的原文 TSV：

```powershell
New-Item -ItemType Directory -Path .\original -Force | Out-Null
Get-ChildItem -LiteralPath . -Filter "Translation-*.tsv" -File |
    Move-Item -Destination .\original
```

這段搬移指令只在首次整理時執行。若 `original` 已有同名檔，先確認版本；不要重新提取或覆蓋既有原文來處理翻譯錯誤。

### B. 批次翻譯

依照下方教學，以 `original` 為輸入、`translated` 為輸出。原始 TSV 保留於 `original`，程式逐筆保存翻譯進度。

### C. 回填腳本

先停止翻譯程式並校對輸出。回填工具只讀取 `scenario.ks` 同目錄下的 `Translation-*.tsv`，不會自動搜尋 `translated`。

確認根目錄沒有其他批次殘留的 TSV，再將這批翻譯結果複製回去：

```powershell
Get-ChildItem -LiteralPath .\translated -Filter "Translation-*.tsv" -File |
    Copy-Item -Destination . -Force
python .\nornmiel_text_io.py
```

選擇 `2`，依提示確認備份。此範例使用平面資料夾；若翻譯輸出放在多個子目錄，需自行整理要回填的那一批檔案，避免同名檔互相覆蓋。

回填行為：

- 譯文空白時跳過，保留該行日文。
- 原文、行號、角色、雜湊等驗證失敗時，取消整批寫入。
- 目前寬鬆版遇到方括號標記不一致時，顯示缺少／新增標記的警告，仍寫入該筆譯文，不會自動補回標記。
- 若在備份提示回答 `n`，程式會自動建立 `scenario.ks.bak`；同名檔存在時使用帶時間戳的名稱。回答 `y` 則表示自行完成備份，不另外建立。
- 成功後將 `scenario.ks` 寫為 UTF-16 LE BOM，保留各行原有換行形式。

標記警告不阻擋回填，但缺少或改動遊戲指令仍可能影響執行。回填後請進行遊戲內測試；重新回填另一批譯文前，先使用對應的原始 `scenario.ks` 副本，避免因腳本已變成中文而無法通過原文比對。

回填只會修改這份 `scenario.ks`。要在遊戲中使用譯文，還需要將它放回正確的解包資料路徑，再依遊戲的資源載入方式使用，或自行重新封包；本工具沒有「將 TSV 翻譯自動打包回 XP3」功能。音效修補器也不會讀取外部 TSV 或這份獨立腳本來合併譯文。

## Ollama TSV 日文翻譯工具使用教學

使用 `translate_tsv.py` 將資料夾內的日文 TSV 批次翻譯為台灣繁體中文。Python 負責讀檔、呼叫本機 Ollama、檢查回傳格式與儲存進度；Qwen 負責翻譯；OpenCC 負責轉換繁體字形。

本教學對應含有 `--normalize-only`、`--retry-japanese`、`--pause-every`、`--pause-seconds`、`--save-retries`、`--save-retry-delay` 的翻譯程式，以及方括號標記不一致時只警告的回填程式。指令以 Windows PowerShell 為例，模型名稱使用 `qwen3:14b`。

## 1. 快速開始

準備好 Python、Ollama 和已下載的模型，將程式與 `original` 資料夾放在同一層。把待翻譯的 TSV 放進 `original`。

開啟 PowerShell，切換到程式所在資料夾：

```powershell
cd "D:\翻譯工具"
```

安裝文字轉換套件：

```powershell
python -m pip install opencc-python-reimplemented
```

確認模型的完整名稱：

```powershell
ollama list
```

先試翻 3 筆：

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --limit 3
```

確認 `translated` 內的譯文後，開始全部翻譯，並設定每成功翻譯 50 筆休息 60 秒：

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --pause-every 50 --pause-seconds 60
```

已經翻好的 3 筆會跳過，不會重複翻譯。

## 2. 執行環境

| 項目 | 需求或用途 |
| --- | --- |
| Python | 3.9 以上 |
| Windows x64 | 音效修補器的自動下載固定使用 Windows x64 MSVC 版本打包器 |
| Ollama | 已安裝且服務正在執行 |
| 模型 | 已存在於本機，名稱須與 `ollama list` 一致 |
| OpenCC | 安裝 `opencc-python-reimplemented` |
| 文件編碼 | UTF-8，可有或沒有 BOM |
| 文件格式 | 符合指定六欄格式的 TSV |

檢查 Python 與 OpenCC：

```powershell
python --version
python -c "from opencc import OpenCC; print(OpenCC('s2tw').convert('这里是测试'))"
```

第二條指令應輸出：

```text
這裡是測試
```

若在 PyCharm 使用虛擬環境，請在同一個環境的終端機執行安裝與翻譯，避免套件裝在另一個 Python 裡。

本教學的命令使用本機模型與 `http://localhost:11434`。程式會將待譯文字及同檔前後文送到此位址；若改用 `--url` 指向另一台主機，內容就會送到該主機。

## 3. 資料夾配置

| 路徑 | 內容 |
| --- | --- |
| `D:\翻譯工具\nornmiel_text_io.py` | 提取／回填程式 |
| `D:\翻譯工具\translate_tsv.py` | Ollama 翻譯程式 |
| `D:\翻譯工具\nornmiel_audio_xp3_patcher.py` | XP3 音效修補程式；操作目錄另見音效教學 |
| `D:\翻譯工具\scenario.ks` | 待提取／回填的遊戲腳本 |
| `D:\翻譯工具\original\Translation-001.tsv` | 第 1 份原文 |
| `D:\翻譯工具\original\Translation-002.tsv` | 第 2 份原文 |
| `D:\翻譯工具\translated\Translation-001.tsv` | 對應輸出，由程式產生 |
| `D:\翻譯工具\translated\Translation-002.tsv` | 對應輸出，由程式產生 |

程式會遞迴掃描 `original` 的子資料夾，並在輸出目錄保留相同的相對路徑與檔名。

注意以下限制：

- `--input` 接受資料夾，不接受單一 TSV 檔案路徑。只測一份時，將那份檔案放進獨立的測試資料夾。
- 輸入與輸出必須是不同資料夾，且不能互相包含。使用同一層的 `original` 與 `translated` 即可。
- 不要同時啟動兩支程式寫入同一個輸出資料夾。
- 翻譯期間先避免用其他程式編輯輸出檔。

## 4. TSV 格式與欄位

第一列欄位名稱與順序必須完全一致：

```tsv
id	line_no	speaker	source_text	translated_text	source_hash
T000001	21	地	　この世界には魔王がいた。		範例雜湊值
T000002	25	シーリア	「勇者様、ありがとうございます」		另一筆範例雜湊值
```

TSV 使用真正的 Tab 分隔欄位，不是用數個空白代替。上面的雜湊值是格式示意，不能直接拿來回填。翻譯程式不驗算雜湊；提取／回填工具則會以行號、說話者與原文計算 SHA-256 並核對，因此不可自行改動這些原文欄位。

| 欄位 | 用途 | 是否修改 |
| --- | --- | --- |
| `id` | 同一檔案內唯一的資料編號 | 保留 |
| `line_no` | 原始行號 | 保留 |
| `speaker` | 說話者；提示詞將「地」視為旁白 | 保留，提供模型參考 |
| `source_text` | 日文原文 | 保留，交給模型翻譯 |
| `translated_text` | 繁體中文譯文 | 填入或轉換字形 |
| `source_hash` | 原文雜湊或識別資訊 | 保留，不重新計算 |

每筆必須有六欄，不接受額外空白列；同一份檔案內的 `id` 不可重複。翻譯程式會跳過空白原文，以及已有譯文的資料；加上 `--retry-japanese` 時則另處理符合條件的可疑譯文。回填工具還會檢查整批 TSV 的 `id` 與行號有沒有重複。

輸出保留非譯文欄位的內容，但會透過 TSV 寫入器重新序列化，必要時產生引號跳脫。因此不保證輸出檔與原檔的位元組或引號形式完全相同。回填遊戲前，應用自己的匯入工具試讀。

## 5. 常用操作

### 5.1 試翻少量內容

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --limit 3
```

`--limit 3` 代表本次成功完成並儲存 3 筆譯文後停止，包含指定的重翻，不是翻譯 3 個檔案，也不是固定處理檔案前三行。跳過的已有譯文、空白原文與翻譯失敗資料不計入上限。

如果失敗很多，程式可能嘗試超過 3 筆資料，仍未達到 3 筆成功新增。

### 5.2 翻譯所有未完成內容

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b"
```

省略 `--limit`，或指定 `--limit 0`，都代表沒有本次成功完成筆數上限。程式會處理輸入資料夾與子資料夾的所有 TSV。

檔案按路徑排序，檔內按原本資料列順序翻譯。建議以 `Translation-001.tsv`、`Translation-002.tsv` 等補零檔名維持章節順序。

### 5.3 每翻譯 50 筆休息 60 秒

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --pause-every 50 --pause-seconds 60
```

計數規則：

- 計算本次成功新增或重翻並儲存的譯文，跨檔案累計。
- 達到 50 筆後，在下一筆待翻譯資料開始前暫停 60 秒。
- 不計已有譯文、空白原文、失敗資料，也不計 OpenCC 字形轉換。
- 若全部完成，或已達 `--limit`，就直接結束，不額外休息一次。
- 每次重新啟動程式，休息計數會從零開始；已儲存的翻譯進度仍會保留。

例如改為每 100 筆休息 30 秒：

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --pause-every 100 --pause-seconds 30
```

省略 `--pause-every`、指定 `--pause-every 0`，或指定 `--pause-seconds 0`，都不會定期暫停。

暫停只代表這支程式不再送出新的模型請求；它不會強制卸載模型或停止其他應用程式使用 GPU。模型仍可能占用顯存。休息期間也能按 `Ctrl+C` 結束。

### 5.4 只修正已有譯文的簡繁字形

```powershell
python .\translate_tsv.py --input .\original --output .\translated --normalize-only
```

此模式使用 OpenCC 的 `s2tw` 轉換：

- 不呼叫 Ollama，不補翻空白欄位。
- 只處理已存在的譯文，不修改 `speaker` 或 `source_text`。
- 原文資料夾仍然必須存在，供程式比對欄位與資料一致性。
- 處理整批既有譯文，不受 `--limit` 限制，也不觸發定期休息。
- 對需要修改的既有輸出，首次轉換前建立 `.before_normalize.bak` 備份；同名備份已存在時不覆蓋。

一般翻譯模式也會先轉換既有譯文，並將新產生的譯文轉換後才寫入，不一定需要另外執行此模式。

OpenCC 是字形轉換，不會重新理解日文原文，因此不能修正錯譯、漏譯或人名不一致。保留在譯文中的日文漢字姓名也可能被轉換，需另外校對。

### 5.5 中斷與接續

按 `Ctrl+C` 停止。之後再執行相同指令：

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --pause-every 50 --pause-seconds 60
```

程式會比對原文與舊輸出，讀回已有譯文，再處理空白欄位。無須另外建立進度檔；輸出 TSV 就是進度依據。

每成功一筆就儲存整份對應輸出，使用暫存檔與替換方式降低半份檔案的風險。正在生成但尚未成功儲存的那一筆，之後會重新處理。

存檔與 GPU 休息計數無關，不需要等到第 50 筆或休息時才儲存。若在存檔重試期間中斷，完整暫存副本會保留並顯示位置，但不會在下次自動載入；請參閱 5.8 的恢復步驟。

### 5.6 重新翻譯

目前沒有 `--overwrite` 或 `--retranslate` 參數。`--retry-japanese` 只會選擇性重翻疑似殘留日文的資料，不是強制重翻全部。

若想比較另一個模型的翻譯，使用新的輸出資料夾：

```powershell
python .\translate_tsv.py --input .\original --output .\translated_new --model "qwen3:14b" --pause-every 50 --pause-seconds 60
```

只更換模型名稱、繼續使用舊輸出資料夾，不會重翻已有譯文。新的輸出資料夾也仍會跳過原始輸入中已填好的 `translated_text`。

若只想重翻少數幾筆，可先備份輸出 TSV，在程式停止時清空那些資料列的 `translated_text`，再執行原本指令。此方式適用於原始輸入的對應譯文原本為空白；其他欄位請保持一致。

### 5.7 重新處理疑似殘留日文的譯文

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --retry-japanese --pause-every 50 --pause-seconds 60
```

程式會繼續翻譯空白欄位，並額外重翻已有譯文中疑似殘留連續平假名的資料。其他已有譯文會跳過。

- 新產生的譯文一律執行平假名檢查；偵測到可疑片段時，補充提示並依 `--retries` 重新翻譯。
- 判斷條件是至少兩個連續平假名字元，後續可含長音符。比對前會排除同檔 `speaker` 的名稱，以及部分大括號、尖括號區段。
- 可疑的前文譯文不會作為模型的中文參考答案；其原文仍會提供。
- 成功替換已有譯文前，首次建立 `.before_retry_japanese.bak`；已有同名備份不覆蓋。
- 重翻失敗時保留舊譯文；原本空白的資料仍留空。下次以相同參數執行可再次處理。
- 成功重翻的筆數計入 `--limit` 與定期休息計數。
- 不可與 `--normalize-only` 同時使用。

這是啟發式檢查，不是完整的翻譯品質判斷。片假名、單個平假名、純漢字的未譯內容可能漏檢；未列於 `speaker` 的平假名專名也可能誤判。若持續誤判，請人工校對，避免反覆重跑整批。

### 5.8 存檔自動重試與暫存檔恢復

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --pause-every 50 --pause-seconds 60 --save-retries 10 --save-retry-delay 2
```

這兩個存檔參數的預設值就是 10 次與 2 秒，省略也會啟用。

程式會先完整寫好一份 `.tmp`，再嘗試替換正式 TSV。若替換遇到權限拒絕或 Windows 檔案占用錯誤，就重試相同暫存檔；不會為了存檔再次呼叫模型，也不會先刪除正式檔來繞過鎖定。

| 情況 | 行為 |
| --- | --- |
| 短暫占用 | 等待設定秒數，再次嘗試替換 |
| 重試成功 | 正式 TSV 更新，繼續下一筆 |
| 次數用完 | 停止程式，保留原正式檔與已完成的暫存副本 |
| 等待時按 `Ctrl+C` | 中斷程式，保留已完成的暫存副本 |
| 磁碟空間不足等其他錯誤 | 直接回報，不反覆重試；是否有完整副本取決於暫存寫入是否已完成 |

`--save-retries 10` 包含首次嘗試，最多等待 9 個間隔。存檔重試與模型請求的 `--retries` 分開計算。這項重試針對替換正式檔的步驟；建立暫存檔、寫入資料或建立備份時若失敗，不保證能進入替換重試。

若完整暫存檔被保留，程式會印出類似 `Translation-021.tsv隨機字串.tmp` 的完整路徑。它是完整 TSV 快照，不只是失敗那一行，但不會自動載入。

手動恢復步驟：

1. 確認翻譯程式已停止，關閉占用該 TSV 的其他程式。
2. 備份目前正式 TSV；如果有多個暫存檔，先比較內容並選擇正確版本。
3. 將所選暫存檔複製為原正式檔名，不要更動原始 `original` 資料夾。
4. 重新執行原本指令，程式會比對原文並從正式 TSV 接續。

以下是恢復範例；必須將 `$snapshot` 換成錯誤訊息顯示的實際暫存檔路徑：

```powershell
$target = ".\translated\Translation-021.tsv"
$snapshot = ".\translated\Translation-021.tsv實際隨機字串.tmp"
$stamp = Get-Date -Format "yyyyMMdd-HHmmssfff"
Copy-Item -LiteralPath $target -Destination "$target.before_recover.$stamp.bak"
Copy-Item -LiteralPath $snapshot -Destination $target -Force
```

若正式檔尚未建立，略過第一個 `Copy-Item` 備份步驟。確認恢復成功後再自行清理暫存檔。

## 6. 全部命令列參數

| 參數 | 預設值 | 說明 |
| --- | --- | --- |
| `--input` | 必填 | 原始 TSV 資料夾，包含子目錄 |
| `--output` | 必填 | 獨立輸出資料夾 |
| `--model` | `qwen:14b` | 模型完整名稱；請明確填入實際安裝名稱，例如 `qwen3:14b` |
| `--url` | `http://localhost:11434` | Ollama 基礎位址，程式自行附加 `/api/generate` |
| `--limit` | `0` | 本次成功完成譯文上限，包含重翻；0 為不限，不能為負數 |
| `--timeout` | `300` | 每次模型請求的逾時設定，單位秒，必須大於 0 |
| `--retries` | `3` | 每筆請求最多嘗試次數，包含第一次；必須大於 0 |
| `--save-retries` | `10` | 替換正式 TSV 遭拒時最多嘗試次數，包含第一次；必須大於 0 |
| `--save-retry-delay` | `2` | 存檔重試間隔秒數，非負整數；0 表示立即重試 |
| `--pause-every` | `0` | 每成功完成幾筆後暫停，包含重翻；0 關閉，不能為負數 |
| `--pause-seconds` | `60` | 暫停秒數，接受非負整數；0 關閉 |
| `--normalize-only` | 關閉 | 只轉換已有譯文，不呼叫模型 |
| `--retry-japanese` | 關閉 | 額外重翻已有譯文中疑似殘留連續平假名的資料 |
| `-h` / `--help` | — | 顯示說明後離開 |

查看程式內建說明：

```powershell
python .\translate_tsv.py --help
```

例如模型回應較慢，可將逾時調整為 600 秒：

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --timeout 600 --retries 3 --pause-every 50 --pause-seconds 60
```

## 7. 程式如何翻譯與檢查

### 前後文與翻譯提示

每次只翻譯一筆，請求帶入同一檔案的以下資料：

| 資料 | 提供內容 |
| --- | --- |
| 前 3 筆 | 說話者、日文原文、已有譯文 |
| 目前這筆 | 說話者、待譯原文 |
| 後 2 筆 | 說話者、日文原文 |

不足的前後文就少提供幾筆，不會跨檔案取用。

前文若被判斷為疑似殘留日文，其 `translated_text` 會以空字串提供，降低後續模仿未翻譯內容的機會。

提示詞要求使用自然的台灣繁體中文、忠於原意、不摘要、不增加情節；將「地」當旁白；參考前文的人名術語，未知人名保留原文。模型回傳 `{"translation":"譯文"}`，由程式取出譯文欄位。

### 輸出檢查

新增譯文必須為非空白字串，不可包含實際 Tab 或換行。程式會比對部分常見佔位符的種類與出現次數，例如 `{0}`、`%s`，以及字面上的 `\n`、`\r`、`\t`。原文開頭的半形與全形空白會補回譯文。

OpenCC 轉換時會避開部分控制碼、大括號內容與尖括號標籤；但這不代表翻譯階段已完整驗證所有遊戲標籤。遊戲自訂語法仍需額外檢查。

既有譯文的轉換模式不會重新執行模型輸出驗證。這些檢查也無法判斷文意是否正確、是否漏譯或人物稱呼是否一致。

新版另有連續平假名的啟發式檢查，詳細規則與限制見 5.7。沒有偵測到平假名，不代表文意或整句翻譯已完整驗證。

翻譯程式目前沒有完整驗證方括號標記。回填工具則會比對 `[...]` 完整字串及出現次數；目前寬鬆版只警告、不阻擋替換，也不檢查標記順序或自動補齊。請自行校對遊戲控制碼。

### 固定的模型設定

以下設定寫在 `translate()` 的 `payload` 中，目前不是命令列參數：

| 設定 | 值 | 用途 |
| --- | --- | --- |
| `temperature` | `0.2` | 降低生成的隨機變化 |
| `num_ctx` | `8192` | 請求的上下文容量，單位 token |
| `num_predict` | `2048` | 每次最大生成 token 數 |
| `format` | `json` | 要求 JSON 輸出 |
| `stream` | `False` | 等生成完成後接收結果 |
| `keep_alive` | `10m` | 請求模型暫時保持載入 |

程式逐筆循序處理，不並行呼叫多筆。若模型用大量 token 思考，可能在回傳完整譯文前就達到生成上限；此時應查看錯誤並考慮調整程式中的生成設定，而非只增加逾時秒數。

## 8. 常見問題排除

### 「原始資料夾不存在」

檢查目前工作目錄與路徑：

```powershell
Get-Location
Test-Path .\original
```

以下用法錯誤，因為傳入單一檔案：

```powershell
python .\translate_tsv.py --input .\Translation-001.tsv --output .\translated
```

請將檔案放進 `original`，再使用 `--input .\original`。路徑含空白時要加雙引號。

### HTTP 404 或 model not found

先查看實際模型名稱：

```powershell
ollama list
```

`qwen:14b`、`qwen2.5:14b`、`qwen3:14b` 是不同名稱。請把 `--model` 改為 `NAME` 欄顯示的完整名稱。

新版會顯示 HTTP 錯誤回應的詳細內容。HTTP 4xx 對該筆不重試，保留原有譯文或空白後繼續下一筆；若是模型名稱錯誤，請先停止並修正，避免整批都失敗。

### 無法連線到 Ollama

確認 Ollama 已啟動，並測試本機 API：

```powershell
Invoke-RestMethod -Uri "http://localhost:11434/api/tags"
```

若使用不同位址或連接埠，透過 `--url` 指定基礎位址，不要自行加上 `/api/generate`。

### 找不到 OpenCC

在執行翻譯的同一個 Python 環境安裝：

```powershell
python -m pip install opencc-python-reimplemented
```

即使使用 `--normalize-only`，也需要此套件。

### unrecognized arguments: --pause-every／--retry-japanese／--save-retries

表示目前執行的程式版本沒有這個參數。先停止翻譯，替換新版 `translate_tsv.py`，再執行 `--help` 確認。也請確認終端機所在資料夾正確，沒有執行另一份同名程式。

### 欄位錯誤、UnicodeDecodeError、id 重複

檢查檔案是否為 UTF-8、第一列是否為指定六個欄位、分隔符是否為 Tab，以及是否有額外空白列或重複編號。不要直接把整份文件改成逗號分隔格式。

### 原文與輸出筆數不同，或原文欄位已變動

程式會先驗證所有輸入與已有輸出，再開始請求模型。若原文已更新，請保留舊結果，改用新的輸出資料夾；不要只修改 `source_hash` 試圖繞過比對。

### 譯文遺漏控制碼、JSON 格式錯誤、輸出未完成或逾時

一般請求與驗證失敗會依 `--retries` 重試；預設最多嘗試 3 次，前兩次失敗分別等待 2、4 秒。最後仍失敗則保留原有譯文或空白，繼續下一筆。

可以重新執行相同指令處理失敗筆數；如果同一筆一直失敗，應檢查原文的特殊語法、回傳格式或生成長度，而非一直增加重試次數。

### PermissionError 或無法替換輸出檔

關閉可能鎖住 TSV 的編輯器、試算表程式或另一支翻譯程序，確認輸出資料夾可寫入，再重新執行。已完成的輸出可作為續跑進度。

新版會針對替換時的權限／占用錯誤自動重試，預設最多 10 次、每次間隔 2 秒。若一直被占用，重試仍會失敗。完整暫存檔的恢復方式見 5.8。

### 譯文非空白，但還含日文

已有內容預設會被跳過；可加上 `--retry-japanese` 選擇性重翻。此功能只抓部分平假名情況，不能處理所有片假名、漢字或語意漏譯，仍需人工校對。

### 回填時出現「方括號標記不一致」

目前寬鬆版會印出缺少／新增的標記，仍將該筆譯文寫入。如果程式仍顯示驗證失敗並取消整批，請確認已替換為寬鬆版 `nornmiel_text_io.py`。其他驗證錯誤仍會阻擋回填，不應直接忽略。

### 回填時顯示原文不符，或找不到翻譯

確認 `scenario.ks` 是當初提取時的原始版本，而且要回填的 `Translation-*.tsv` 已複製到它的同一目錄。回填工具不會自動搜尋 `translated`；先前已回填為中文的腳本也不再符合原文比對。

## 9. 完成後如何確認

全部處理後，終端機會顯示類似：

```text
完成：本次新增 47 筆，重翻 1 筆，失敗 0 次，尚未翻譯 0 筆，疑似殘留日文 0 筆。
```

「本次新增」不包含先前完成的譯文；「尚未翻譯」計算的是原文非空白、譯文仍空白的資料。只有空白原文的資料不會被當成未完成。

「重翻」表示本次成功替換的既有可疑譯文；「疑似殘留日文」會檢查目前所有非空白譯文，不限本次產生的資料。畫面上的 `[檔名] 10/50 Txxxxxx` 表示開始處理該筆，不代表該筆已成功存檔。

Windows PowerShell 可查看程式結束代碼：

```powershell
$LASTEXITCODE
```

| 代碼 | 常見意義 |
| --- | --- |
| `0` | 正常完成；也可能只是達到 `--limit` 或完成字形轉換，不一定代表全批翻完 |
| `1` | 仍有未翻譯資料、發生處理／存檔錯誤、達到 limit 前有失敗資料，或啟用重翻模式後仍有可疑日文 |
| `2` | 命令列參數或前置檢查錯誤 |
| `130` | 使用者以 `Ctrl+C` 中斷 |

正式回填前，抽查旁白、對話、人物稱呼、專有名詞、佔位符與遊戲標籤。確認匯入工具能正確讀取輸出的 TSV，再進行遊戲內測試。

## 10. 目前功能邊界

以下限制主要針對文本翻譯流程；音效修補器的流程與備份規則另列於下一節。

- 沒有跨檔案的人名表、術語表或長期記憶；每檔只參考附近幾筆內容。
- OpenCC 改善簡繁字形，無法保證語意、台灣用語或姓名正確。
- `source_hash` 只保留並參與續跑比對，不驗算 SHA-256。
- 不會翻譯 `speaker`，也不會自動將結果回填到遊戲原始腳本。
- 休息計數不持久化；重新執行會從零累計。
- 不會監測 GPU 溫度，也不會根據溫度自動調整負載。定期休息是時間排程。
- 使用新輸出資料夾可保留舊版結果；字形轉換的 `.bak` 不是每次翻譯都建立的版本備份。
- 上述雜湊與回填限制指 `translate_tsv.py`；`nornmiel_text_io.py` 會驗算雜湊並可執行回填。
- 日文殘留檢查只是啟發式判斷，可能漏檢或誤判。
- 存檔重試不會解除永久占用或修正檔案權限；保留的 `.tmp` 也不會自動恢復。
- 回填時的方括號警告不代表標記差異一定無害，寬鬆模式也不會修正標記。

日常使用可保留這條指令，並將模型名稱換成你實際安裝的名稱：

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --pause-every 50 --pause-seconds 60 --save-retries 10 --save-retry-delay 2
```

## XP3 音效自動修補

### 1. 功能與必要環境

執行檔案：`nornmiel_audio_xp3_patcher.py`。這是互動式程式，目前沒有命令列參數；依終端機提示操作即可。

| 項目 | 行為 |
| --- | --- |
| 指定音效循環 | 將 `scenario.ks` 中 `se904`、`se905` 的有效 `@SE`／`@playse` 或對應行首標籤設為 `loop=true` |
| SE 巨集 | 將 `macro.ks` 中 SE 巨集的 `@playse` 設為 `loop=%loop\|false`，未指定時預設不循環 |
| 換句停止舊語音 | 在 `name` 巨集中加入／更新 buf 0 的條件停止指令，依 `tf.isPlayVoice` 判斷 |
| 回想設定介面 | 開啟設定時保存並暫停 buf 0、1、2 的音效狀態，返回時恢復；限回想模式 |
| 離開回想 | 在 `scenemode.ks` 的 `*return` 區段補入停止 buf 0、1、2 與重設語音旗標的指令 |
| 封包處理 | 解包 → 修補腳本 → 驗證修補結果 → 重新封包 → 可選擇重新解包驗證 → 備份並替換原 XP3 |

需要 Python 3.9 以上、可寫入的遊戲目錄，以及對應遊戲的 XP3。此程式使用 Python 標準函式庫，不需安裝 OpenCC 或啟動 Ollama。自動下載的打包器是 Windows x64 版本。

程式必須在解包結果中唯一找到同一資料夾下的 `scenario.ks`、`macro.ks`、`scenemode.ks`、`sub.ks`。若找不到目標音效、巨集或必要標籤，會停止，不會直接套用到不符結構的遊戲。

### 2. 執行方式

先關閉遊戲，將修補程式放在含有 XP3 的遊戲目錄。例如：

| 路徑 | 內容 |
| --- | --- |
| `D:\遊戲\nornmiel_audio_xp3_patcher.py` | 音效修補程式 |
| `D:\遊戲\data.xp3` | 要修補的封包 |
| `D:\遊戲\xp3-pack-unpack.exe` | 可選；缺少時自動下載 |

在 PowerShell 執行：

```powershell
Set-Location -LiteralPath "D:\遊戲"
python .\nornmiel_audio_xp3_patcher.py
```

也可將程式留在工具目錄，以完整路徑執行：

```powershell
Set-Location -LiteralPath "D:\遊戲"
python "D:\翻譯工具\nornmiel_audio_xp3_patcher.py"
```

`-LiteralPath` 適合包含 `[`、`]` 等字元的目錄，避免 PowerShell 將它們當成萬用字元。

### 3. 目錄與封包選擇

1. 優先檢查目前工作目錄是否有 `.xp3`，再檢查腳本所在目錄。
2. 都找不到時，提示輸入遊戲目錄的完整路徑；直接 Enter 取消。
3. 所選目錄有 `data.xp3` 時優先使用它。
4. 沒有 `data.xp3` 但只有一個 XP3 時，自動選擇該檔。
5. 有多個候選時，依畫面列出的編號選擇。

程式會先尋找／下載打包器，再選擇封包，因此缺少打包器時，下載可能在「是否開始修補」的確認提示之前發生。

### 4. 打包器自動下載與清理

程式依序在遊戲目錄、目前工作目錄、腳本目錄尋找：

```text
xp3-pack-unpack.exe
pack-unpack.exe
```

找到就直接使用，不檢查更新。都找不到時，才自動處理以下附件：

- 專案：[lxl66566/xp3-pack-unpack](https://github.com/lxl66566/xp3-pack-unpack/releases)
- 附件名稱：`xp3-pack-unpack-x86_64-pc-windows-msvc.zip`

自動流程：

1. 透過 GitHub API 查詢 Latest 正式 Release。
2. 若 Latest 沒有指定附件，繼續依 Release 清單順序尋找第一個符合名稱的正式版本；排除草稿與預發行版本，不以版本號大小排序。
3. 下載到目前工作目錄，確認檔案大小，再解壓縮到該目錄，保留 ZIP 內的相對路徑。
4. 確認解壓縮成功且能唯一找到打包器後，刪除剛下載的 ZIP。
5. 使用該 EXE 接續修補流程。

「目前工作目錄」是執行 Python 指令時所在的位置，不一定等於腳本目錄或提示中指定的遊戲目錄。使用上一節先切換到遊戲目錄的指令，就會下載到遊戲目錄。

| 情況 | 處理方式 |
| --- | --- |
| 已有可用名稱的 EXE | 直接使用，不下載；不會自動清理原本就有的 ZIP |
| 目前目錄已有同名 ZIP | 停止下載，請先檢查並移走或改名；不覆蓋、不自動刪除 |
| ZIP 損壞或解壓縮失敗 | 停止；已完成下載的 ZIP 保留供檢查 |
| ZIP 內檔案與現有檔案內容不同 | 停止，不覆蓋既有檔案；內容完全相同的既有檔案可保留 |
| GitHub 連線或 API 失敗 | 顯示錯誤後停止，沒有自動網路重試或登入流程 |
| 正常下載與解壓縮完成 | EXE 與其他解壓內容留下，下載的 ZIP 刪除 |

若無法連線 GitHub，可自行從 Release 下載並解壓縮，將 EXE 放到上述三個搜尋目錄之一，再重新執行。保留 ZIP 以供檢查的規則不代表所有下載失敗都會留下完整 ZIP；未完成的下載暫存檔會被清理。

### 5. 確認、驗證與備份

程式會顯示遊戲目錄、打包器、目標 XP3、檔案大小與可用空間。

| 提示 | 預設／行為 |
| --- | --- |
| 是否開始自動解包、修改及重新封包？ | 預設否；輸入 `y` 開始，直接 Enter 取消 |
| 是否重新解開新封包進行完整驗證？ | 預設是；直接 Enter 會驗證，輸入 `n` 可略過這次重新解包 |
| 磁碟空間少於 XP3 的三倍 | 只警告，不強制停止；實際所需空間依解包大小及驗證流程而定 |

即使略過重新解包，重新封包前的腳本修補驗證仍會執行。「完整驗證」是重新解包後核對修補腳本，不代表已啟動遊戲或驗證遊戲的所有資源。

替換原始 XP3 前會自動備份，無須另外確認備份選項。例如目標是 `data.xp3`：

```text
data.xp3.bak
```

若同名備份已存在，會改用帶時間戳與必要編號的檔名。備份大小確認一致後，才以新 XP3 替換原檔。實際備份名稱與位置會顯示在終端機。

修補用的解包／驗證資料放在遊戲目錄的臨時工作資料夾，結束時會嘗試清理，包含失敗時。因此失敗後不能假設解包內容仍保留供續跑。此程式沒有 TSV 翻譯那套逐筆續跑、存檔重試或定時休息參數。

### 6. 還原原始 XP3

先關閉遊戲並確認修補程式已結束。備份目前修補版，再將指定的 `.bak` 複製回原檔。請依終端機顯示的實際檔名調整：

```powershell
$archive = ".\data.xp3"
$backup = ".\data.xp3.bak"
$stamp = Get-Date -Format "yyyyMMdd-HHmmssfff"
Copy-Item -LiteralPath $archive -Destination "$archive.patched.$stamp.bak"
Copy-Item -LiteralPath $backup -Destination $archive -Force
```

若做過多次修補，請選對備份版本；最新一次修補前的備份不一定是最初的未修改封包。

### 7. 常見問題

| 問題 | 檢查方式 |
| --- | --- |
| 找不到 XP3 | 確認目前工作目錄或輸入的遊戲目錄包含正確封包；不會遞迴搜尋整個遊戲目錄 |
| 同名 ZIP 已存在 | 檢查是否為上次保留的下載；移走或改名後重跑，或手動解壓縮並放好 EXE |
| 解壓縮會覆蓋既有檔案 | 檢查畫面列出的衝突路徑，將衝突檔先移到其他位置後重試 |
| 找不到 `scenario.ks` 等四份腳本 | 所選 XP3 可能不是腳本封包，或遊戲結構不符合這支修補器 |
| 找不到目標音效或巨集／標籤不唯一 | 該遊戲或版本可能不適用，需先檢查程式預期的腳本結構 |
| 打包器結束代碼不是 0 | 查看打包器輸出；下載成功不代表工具一定支援該 XP3 的格式或加密方式 |
| 封包替換時存取被拒 | 關閉遊戲及可能占用封包的其他程式，確認目錄可寫入；音效修補器沒有自動存檔重試 |
| 不知道修補有沒有生效 | 查看完成與備份訊息，再進入遊戲測試指定音效、換句語音與回想設定操作 |

## 免責聲明

1. 本工具僅供個人學習、技術研究與交流使用，請勿用於任何商業用途。
2. 本工具不包含任何遊戲本體、資源或腳本內容。使用者須自行持有合法取得的遊戲正版副本。
3. 遊戲文本、劇情、角色及相關素材的著作權，均屬原開發商與發行商所有。請勿將提取出的文本或翻譯成果公開散布、上傳或用於營利。
4. 本工具與 Norn、Miel、Cybele 及其相關公司無任何關聯，亦未獲其授權或背書。
5. 本工具依「現狀」提供，不附帶任何明示或默示的保證。使用本工具所造成的任何損失或法律責任，由使用者自行承擔，作者概不負責。
6. 使用本工具即表示你已閱讀並同意以上條款。若不同意，請勿使用。