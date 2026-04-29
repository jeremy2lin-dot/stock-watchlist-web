# 個股監控網站部署說明

## 已支援的部署方式

這個專案已整理成可部署版本：

- `Procfile`: 適合 Render/Railway/Heroku 類型平台。
- `render.yaml`: Render Blueprint，可建立 Web Service 與 persistent disk。
- `Dockerfile`: 適合 Fly.io、Railway Docker、VPS、NAS、雲端主機。

## 必設環境變數

正式上線時請設定：

```text
WATCHLIST_USER=你的登入帳號
WATCHLIST_PASSWORD=你的登入密碼
WATCHLIST_DATA_PATH=/var/data/watchlist_data.json
```

`WATCHLIST_USER` 與 `WATCHLIST_PASSWORD` 會啟用基本登入保護。

## Render 部署建議

1. 把整個資料夾推到 GitHub repository。
2. 在 Render 建立新的 Blueprint 或 Web Service。
3. 使用 `render.yaml`。
4. 設定 `WATCHLIST_USER` 與 `WATCHLIST_PASSWORD`。
5. 確認 persistent disk 掛載在 `/var/data`。

## 注意事項

- 不建議把沒有登入保護的網站公開到網路。
- 免費或休眠型主機可能會讓第一次更新比較慢。
- `watchlist_data.json` 必須放在 persistent disk，否則主機重建後資料可能消失。
- TWSE/TPEX 或 Yahoo 歷史備援資料源可能受來源網站限制，正式交易用途仍建議改接券商官方 API。
