# 發布至 Streamlit Community Cloud

1. 將本專案推送到 GitHub 儲存庫的 `main` 分支。
2. 前往 <https://share.streamlit.io>，使用 GitHub 登入。
3. 選擇 **Create app**，指定儲存庫、`main` 分支與入口檔 `app.py`。
4. Python 選擇 3.11，按下 Deploy。
5. 在 App settings → Sharing 設為公開，即可把固定網址分享給朋友。

## 自動更新

`.github/workflows/update-data.yml` 使用 UTC 排程，換算台北時間為每天：

- 07:00
- 14:00
- 21:00

工作完成後會把 `data/raw`、`data/processed` 與更新狀態提交回目前分支，Streamlit Cloud
偵測到 GitHub 變更後會重新載入網站資料。GitHub 排程可能因平台繁忙而延後數分鐘。

## 手動更新

網站左側選擇「系統狀態」，按「立即更新所有資料」。同一時間只允許一個更新程序，避免重複執行。
GitHub 儲存庫的 Actions 頁亦可選擇 **Update stock data → Run workflow**，此方式會把結果永久提交回儲存庫。

## 機密資料

任何 API 金鑰及雲端憑證只可放在 GitHub Actions Secrets 或 Streamlit App Secrets，禁止提交 `.env`、
`secrets.toml` 或服務帳戶 JSON。
