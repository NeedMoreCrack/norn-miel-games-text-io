# Norn/Miel/Cybele 遊戲文本提取器

須先解包xp3

[解包工具](https://github.com/lxl66566/xp3-pack-unpack)

解包後將 `data\scenario\scenario.ks` 放到此工具相同目錄

# Ollama TSV 日文翻譯工具使用教學

使用 `translate_tsv.py` 將資料夾內的日文 TSV 批次翻譯為台灣繁體中文。Python 負責讀檔、呼叫本機 Ollama、檢查回傳格式與儲存進度；Qwen 負責翻譯；OpenCC 負責轉換繁體字形。

本教學對應含有 `--normalize-only`、`--pause-every`、`--pause-seconds` 的程式版本。指令以 Windows PowerShell 為例，模型名稱使用 `qwen3:14b`。

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
| `D:\翻譯工具\translate_tsv.py` | Python 程式 |
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

TSV 使用真正的 Tab 分隔欄位，不是用數個空白代替。上面的雜湊值是格式示意；程式不會驗算雜湊內容。

| 欄位 | 用途 | 是否修改 |
| --- | --- | --- |
| `id` | 同一檔案內唯一的資料編號 | 保留 |
| `line_no` | 原始行號 | 保留 |
| `speaker` | 說話者；提示詞將「地」視為旁白 | 保留，提供模型參考 |
| `source_text` | 日文原文 | 保留，交給模型翻譯 |
| `translated_text` | 繁體中文譯文 | 填入或轉換字形 |
| `source_hash` | 原文雜湊或識別資訊 | 保留，不重新計算 |

每筆必須有六欄，不接受額外空白列；同一份檔案內的 `id` 不可重複。只有空白的 `source_text` 會跳過。

輸出保留非譯文欄位的內容，但會透過 TSV 寫入器重新序列化，必要時產生引號跳脫。因此不保證輸出檔與原檔的位元組或引號形式完全相同。回填遊戲前，應用自己的匯入工具試讀。

## 5. 常用操作

### 5.1 試翻少量內容

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --limit 3
```

`--limit 3` 代表本次成功新增 3 筆譯文後停止，不是翻譯 3 個檔案，也不是固定處理檔案前三行。已有譯文、空白原文與翻譯失敗的資料不計入上限。

如果失敗很多，程式可能嘗試超過 3 筆資料，仍未達到 3 筆成功新增。

### 5.2 翻譯所有未完成內容

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b"
```

省略 `--limit`，或指定 `--limit 0`，都代表沒有本次新增筆數上限。程式會處理輸入資料夾與子資料夾的所有 TSV。

檔案按路徑排序，檔內按原本資料列順序翻譯。建議以 `Translation-001.tsv`、`Translation-002.tsv` 等補零檔名維持章節順序。

### 5.3 每翻譯 50 筆休息 60 秒

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --pause-every 50 --pause-seconds 60
```

計數規則：

- 只計本次成功新增並儲存的譯文，跨檔案累計。
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

### 5.6 重新翻譯

目前沒有 `--overwrite` 或 `--retranslate` 參數。

若想比較另一個模型的翻譯，使用新的輸出資料夾：

```powershell
python .\translate_tsv.py --input .\original --output .\translated_new --model "qwen3:14b" --pause-every 50 --pause-seconds 60
```

只更換模型名稱、繼續使用舊輸出資料夾，不會重翻已有譯文。新的輸出資料夾也仍會跳過原始輸入中已填好的 `translated_text`。

若只想重翻少數幾筆，可先備份輸出 TSV，在程式停止時清空那些資料列的 `translated_text`，再執行原本指令。此方式適用於原始輸入的對應譯文原本為空白；其他欄位請保持一致。

## 6. 全部命令列參數

| 參數 | 預設值 | 說明 |
| --- | --- | --- |
| `--input` | 必填 | 原始 TSV 資料夾，包含子目錄 |
| `--output` | 必填 | 獨立輸出資料夾 |
| `--model` | `qwen:14b` | 模型完整名稱；請明確填入實際安裝名稱，例如 `qwen3:14b` |
| `--url` | `http://localhost:11434` | Ollama 基礎位址，程式自行附加 `/api/generate` |
| `--limit` | `0` | 本次成功新增譯文上限；0 為不限，不能為負數 |
| `--timeout` | `300` | 每次模型請求的逾時設定，單位秒，必須大於 0 |
| `--retries` | `3` | 每筆請求最多嘗試次數，包含第一次；必須大於 0 |
| `--pause-every` | `0` | 每成功新增幾筆後暫停；0 關閉，不能為負數 |
| `--pause-seconds` | `60` | 暫停秒數，接受非負整數；0 關閉 |
| `--normalize-only` | 關閉 | 只轉換已有譯文，不呼叫模型 |
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

提示詞要求使用自然的台灣繁體中文、忠於原意、不摘要、不增加情節；將「地」當旁白；參考前文的人名術語，未知人名保留原文。模型回傳 `{"translation":"譯文"}`，由程式取出譯文欄位。

### 輸出檢查

新增譯文必須為非空白字串，不可包含實際 Tab 或換行。程式會比對部分常見佔位符的種類與出現次數，例如 `{0}`、`%s`，以及字面上的 `\n`、`\r`、`\t`。原文開頭的半形與全形空白會補回譯文。

OpenCC 轉換時會避開部分控制碼、大括號內容與尖括號標籤；但這不代表翻譯階段已完整驗證所有遊戲標籤。遊戲自訂語法仍需額外檢查。

既有譯文的轉換模式不會重新執行模型輸出驗證。這些檢查也無法判斷文意是否正確、是否漏譯或人物稱呼是否一致。

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

新版會顯示 HTTP 錯誤回應的詳細內容。HTTP 4xx 對該筆不重試，保留空白後繼續下一筆；若是模型名稱錯誤，請先停止並修正，避免整批都失敗。

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

### unrecognized arguments: --pause-every

表示目前執行的程式版本沒有這個參數。先停止翻譯，替換新版 `translate_tsv.py`，再執行 `--help` 確認。也請確認終端機所在資料夾正確，沒有執行另一份同名程式。

### 欄位錯誤、UnicodeDecodeError、id 重複

檢查檔案是否為 UTF-8、第一列是否為指定六個欄位、分隔符是否為 Tab，以及是否有額外空白列或重複編號。不要直接把整份文件改成逗號分隔格式。

### 原文與輸出筆數不同，或原文欄位已變動

程式會先驗證所有輸入與已有輸出，再開始請求模型。若原文已更新，請保留舊結果，改用新的輸出資料夾；不要只修改 `source_hash` 試圖繞過比對。

### 譯文遺漏控制碼、JSON 格式錯誤、輸出未完成或逾時

一般請求與驗證失敗會依 `--retries` 重試；預設最多嘗試 3 次，前兩次失敗分別等待 2、4 秒。最後仍失敗則保留空白，繼續下一筆。

可以重新執行相同指令處理失敗筆數；如果同一筆一直失敗，應檢查原文的特殊語法、回傳格式或生成長度，而非一直增加重試次數。

### PermissionError 或無法替換輸出檔

關閉可能鎖住 TSV 的編輯器、試算表程式或另一支翻譯程序，確認輸出資料夾可寫入，再重新執行。已完成的輸出可作為續跑進度。

## 9. 完成後如何確認

全部處理後，終端機會顯示類似：

```text
完成：本次新增 47 筆，失敗 0 次，尚未翻譯 0 筆。
```

「本次新增」不包含先前完成的譯文；「尚未翻譯」計算的是原文非空白、譯文仍空白的資料。只有空白原文的資料不會被當成未完成。

Windows PowerShell 可查看程式結束代碼：

```powershell
$LASTEXITCODE
```

| 代碼 | 常見意義 |
| --- | --- |
| `0` | 正常完成；也可能只是達到 `--limit` 或完成字形轉換，不一定代表全批翻完 |
| `1` | 整批跑完仍有未翻譯資料、發生處理錯誤，或達到 limit 前有失敗資料 |
| `2` | 命令列參數或前置檢查錯誤 |
| `130` | 使用者以 `Ctrl+C` 中斷 |

正式回填前，抽查旁白、對話、人物稱呼、專有名詞、佔位符與遊戲標籤。確認匯入工具能正確讀取輸出的 TSV，再進行遊戲內測試。

## 10. 目前功能邊界

- 沒有跨檔案的人名表、術語表或長期記憶；每檔只參考附近幾筆內容。
- OpenCC 改善簡繁字形，無法保證語意、台灣用語或姓名正確。
- `source_hash` 只保留並參與續跑比對，不驗算 SHA-256。
- 不會翻譯 `speaker`，也不會自動將結果回填到遊戲原始腳本。
- 休息計數不持久化；重新執行會從零累計。
- 不會監測 GPU 溫度，也不會根據溫度自動調整負載。定期休息是時間排程。
- 使用新輸出資料夾可保留舊版結果；字形轉換的 `.bak` 不是每次翻譯都建立的版本備份。

日常使用可保留這條指令，並將模型名稱換成你實際安裝的名稱：

```powershell
python .\translate_tsv.py --input .\original --output .\translated --model "qwen3:14b" --pause-every 50 --pause-seconds 60
```

## 免責聲明

1. 本工具僅供個人學習、技術研究與交流使用，請勿用於任何商業用途。
2. 本工具不包含任何遊戲本體、資源或腳本內容。使用者須自行持有合法取得的遊戲正版副本。
3. 遊戲文本、劇情、角色及相關素材的著作權，均屬原開發商與發行商所有。請勿將提取出的文本或翻譯成果公開散布、上傳或用於營利。
4. 本工具與 Norn、Miel、Cybele 及其相關公司無任何關聯，亦未獲其授權或背書。
5. 本工具依「現狀」提供，不附帶任何明示或默示的保證。使用本工具所造成的任何損失或法律責任，由使用者自行承擔，作者概不負責。
6. 使用本工具即表示你已閱讀並同意以上條款。若不同意，請勿使用。