## DAT 指標 Dashboard：Premium to NAV（MSTR 範例）

這個小專案是一個**可部署的網站**，用每日資料觀察 DAT（Digital Asset Treasury company）常用指標：**Premium to NAV**。

### 指標定義

- **Premium to NAV (%)**：
  \[
  \text{Premium} = \left(\frac{\text{Share Price}}{\text{NAV per Share}} - 1\right)\times 100
  \]
- **NAV per Share**（此作業版簡化）：
  \[
  \text{NAV per Share} = \frac{\text{BTC Holdings}\times \text{BTC Price}}{\text{Shares Outstanding}}
  \]

### 資料來源

- **BTC/USD 日線**：CoinGecko `market_chart` API
- **MSTR 日線收盤**：AlphaVantage `TIME_SERIES_DAILY_ADJUSTED`（需 API key）
- **MSTR BTC holdings（Total Bitcoin）**：BuyBitcoinWorldwide 的 purchase history 表格（用 BeautifulSoup 解析）

> 注意：`shares outstanding` 在此版本為**假設值**（可用環境變數或 query 調整）。若要更精準，可改成每日/季度 fully-diluted share count 的時間序列。

---

## 本機執行

在專案根目錄 `dat_premium_nav/`：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ALPHAVANTAGE_API_KEY="你的key"
uvicorn app.main:app --reload --port 8000
```

打開 `http://127.0.0.1:8000/`。

### 可調參數

- **環境變數**
  - `MSTR_SHARES_OUTSTANDING`：預設 `17500000`
  - `DEFAULT_DAYS`：預設 `365`
  - `ALPHAVANTAGE_API_KEY`：必填（用來抓 MSTR 日線）
- **API Query**
  - `/api/premium-to-nav?days=365&symbol=MSTR&shares_outstanding=17500000`

---

## 部署（Render，一鍵）

此專案已附 `render.yaml`，可用 Render Blueprint 直接部署。

### 步驟

1. 把專案推到 GitHub（整個 `dat_premium_nav/` 資料夾）
2. Render → New → Blueprint
3. 選你的 repo（會自動讀到 `render.yaml`）
4. 在 Render 的環境變數填：
   - `ALPHAVANTAGE_API_KEY`

部署完成後，你會拿到一個公開網址（交作業用）。

---

## 部署（Docker / Fly.io / Railway）

專案已附 `Dockerfile`。

重點環境變數：

- `ALPHAVANTAGE_API_KEY`（必填）
- `PORT`（平台通常會自動提供）

---

## 與 BTC 的關係（交作業可引用）

Premium to NAV 量化了市場願意為「公司持有的 BTC 淨值」支付多少**溢價/折價**。由於 NAV 的主要驅動是 BTC 價格，Premium 的變化常被用來觀察：

- 投資人是否把 DAT 公司視為 **BTC 的高 Beta 代理**（包含融資、增持、槓桿與股權市場流動性）
- 當 Premium 上升：可能反映風險偏好提升與對「BTC per share 增長能力」的定價
- 當 Premium 下滑/轉負：可能反映風險偏好下降、稀釋疑慮、或股票相對 BTC 轉弱
