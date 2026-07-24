# 台股智慧預測與分析系統

本專案是一套以台股為核心、整合台美市場資料、技術面、籌碼面與模型預測的研究平台。第一版聚焦台灣加權指數、台積電、聯發科、鴻海、廣達、緯創，以及 TSM、NVDA、AMD、AVGO、MU 與主要美股市場指標。

> 重要聲明：本系統僅供資料分析、教育與研究使用。任何預測、訊號與回測結果均不代表或保證未來獲利，亦不構成投資建議。

## 目前進度

- [x] 第一階段：專案架構、集中設定、色彩規格、環境變數範例與開發文件初稿
- [x] 第二階段：BigQuery 資料表與初始化工具
- [ ] 第三階段：台股及美股行情蒐集
- [ ] 第四階段：技術指標與跨市場日期對齊
- [ ] 第五階段：Logistic Regression 基準模型
- [ ] 第六階段：Streamlit 基本畫面
- [ ] 第七階段：XGBoost 模型
- [ ] 第八階段：法人、籌碼及基本面
- [ ] 第九階段：完整回測系統
- [ ] 第十階段：排程、模型監控與部署

## 系統架構

```text
外部資料來源
  ├─ 台股行情／法人／基本面
  └─ 美股／匯率／利率／總體資料
              │
              ▼
        蒐集與日期對齊層
              │
              ▼
          Google BigQuery
              │
      ┌───────┴────────┐
      ▼                ▼
 技術指標與特徵工程   資料品質檢查
      │
      ▼
 Logistic / Random Forest / XGBoost
      │
      ├─ 1日、5日、20日機率與預期報酬
      ├─ 訊號與風險分級
      └─ 歷史回測與模型監控
              │
              ▼
       Streamlit + Plotly
```

## 目錄說明

```text
stock-predictor/
├── app.py                    # Streamlit 入口
├── config/                   # 環境設定、顏色、第一版標的清單
├── collectors/               # 行情、法人、基本面與總體資料蒐集
├── database/                 # BigQuery client、schema 與建表 SQL
├── features/                 # 技術指標、日期對齊、特徵與目標
├── models/                   # 基準／進階模型、訓練與版本管理
├── backtest/                 # 策略、撮合與績效指標
├── pages/                    # Streamlit 各功能頁
├── quality/                  # 資料品質、未來資訊與異常檢查
├── scripts/                  # 初始化、每日更新與模型重訓入口
├── tests/                    # 自動測試
├── data/                     # 本機暫存資料（不提交內容）
├── artifacts/models/         # 本機模型產物（不提交內容）
└── logs/                     # 執行紀錄（不提交內容）
```

## 執行環境

- Python 3.11（建議）
- Google Cloud 專案與 BigQuery dataset
- Windows PowerShell 7 或更新版本

## Windows PowerShell 安裝

```powershell
cd C:\Users\USER\Documents\股票\stock-predictor
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

安裝完成後可直接雙擊 `start_dashboard.cmd`，系統會在背景啟動並自動開啟瀏覽器。要停止時雙擊 `stop_dashboard.cmd`。

編輯 `.env`，填入自己的 Google Cloud 專案與 API 設定。真實密鑰、帳號與服務帳戶 JSON 不可提交至 Git。

## BigQuery 設定（第二階段啟用）

1. 建立或選擇 Google Cloud 專案。
2. 啟用 BigQuery API。
3. 建立具備必要 BigQuery 權限的服務帳戶。
4. 將 JSON 憑證放在專案外的安全位置。
5. 在 `.env` 設定 `GCP_PROJECT_ID`、`BIGQUERY_DATASET`、`BIGQUERY_LOCATION` 與 `GOOGLE_APPLICATION_CREDENTIALS`。
6. 先執行本機 schema 驗證：`python -m scripts.initialize_database --validate-only`。
7. 確認設定後執行：`python -m scripts.initialize_database`。

初始化工具採 `exists_ok` 行為，可安全重複執行，不會刪除既有資料。大型時間序列表依查詢日期分割、依股票代碼叢集並要求日期篩選，以控制 BigQuery 掃描成本。

`us_market_daily` 與 `us_stock_daily` 同時保存資料真正可取得時間和第一個可使用的台股交易日；財務資料保存實際公告時間與有效交易日。這些欄位是防止未來資訊洩漏的必要條件，實際日期映射演算法將於第四階段完成。

## 預定操作命令

以下命令會隨對應階段逐步啟用：

```powershell
# 初始化 BigQuery（第二階段）
python -m scripts.initialize_database

# 第一次下載與每日更新（第三、十階段）
python -m scripts.update_daily_data

# 訓練模型（第五、七階段）
python -m models.train

# 重新訓練正式模型（第十階段）
python -m scripts.retrain_model

# 啟動儀表板（第六階段完整啟用；第一階段已有狀態首頁）
streamlit run app.py

# 執行測試
pytest -q
```

## 網頁版與自動更新

啟動網頁後，首頁會顯示最後更新時間、每個更新步驟的成功或失敗狀態，並提供「立即更新所有資料」按鈕。更新程序具備互斥鎖，連續按鈕或排程重疊時不會同時覆寫檔案。

系統保留每日三次完整更新：

- 07:00：美股收盤後與台股開盤前更新
- 14:00：台股收盤後更新
- 21:00：晚間資料補充更新

也可以在 GitHub Repository 的 **Actions → Update stock data → Run workflow** 隨時手動執行。GitHub 使用 UTC cron，設定檔已完成 UTC+8 換算。

Windows 本機排程可用系統管理員 PowerShell 註冊：

```powershell
cd C:\Users\USER\Documents\股票\stock-predictor
powershell -ExecutionPolicy Bypass -File .\scripts\register_windows_schedule.ps1
```

排程電腦必須在執行時間開機且可連線。設定使用 `StartWhenAvailable`，錯過執行時間後會在電腦恢復可用時補跑；重疊更新會自動忽略第二個程序。

手動命令更新：

```powershell
python -m scripts.update_daily_data --trigger manual
```

本機更新資料存放在 `data/raw/tw` 與 `data/raw/us`，狀態與錯誤紀錄存放在 `logs`。GitHub 執行產生的資料會保留為 14 天的工作成果檔；第二階段接入 BigQuery 後，雲端排程將直接寫入持久化資料庫供網頁讀取。

## 日期與未來資訊原則

- 美國市場資料以實際可取得時間映射至下一個可交易的台股交易日，不以相同日曆日期直接合併。
- 美股夏令／冬令時間、台美休市差異與盤後公告均使用具時區的時間戳處理。
- 財報與基本面資料以實際公告時間及 `effective_trade_date` 決定模型可用日期。
- 所有滾動指標、正規化與缺失值處理只允許使用預測當時已知資料。
- 訓練、驗證與測試採時間序列切割，禁止隨機打散造成未來資訊洩漏。

## 排程與部署（第十階段完成）

- GitHub Actions：每日台股收盤後更新；每週或每月重訓。
- Google Cloud：可用 Cloud Run 執行 Streamlit，Cloud Scheduler 觸發更新工作。
- Streamlit Community Cloud：適合展示版，敏感值放入平台 Secrets。
- 正式環境建議 BigQuery 使用最小權限服務帳戶，並以 Secret Manager 管理憑證。

## 常見問題

- `GCP_PROJECT_ID is required`：先確認 `.env` 已由 `.env.example` 複製並填入專案 ID。
- 找不到 Google 憑證：確認 `GOOGLE_APPLICATION_CREDENTIALS` 是有效的絕對路徑，且 JSON 未放入版本庫。
- PowerShell 禁止啟用虛擬環境：可在目前使用者範圍執行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，變更前請遵循組織安全政策。
- 資料來源暫時失敗：後續蒐集器會重試、保留上次成功資料並寫入管理頁面可見的紀錄。

## 開發原則

- 設定、門檻與顏色集中管理，不在頁面或模型內重複寫死。
- 憑證只由環境變數或雲端秘密管理服務提供。
- 每個階段先完成自動測試，再進入下一階段。
- 所有圖表使用台股紅漲綠跌慣例與固定色盤，並用線型輔助色盲辨識。
- 圖表人工驗收請參考 `docs/chart_style_guide.md`；程式仍以 `config/color_config.py` 為唯一顏色來源。
