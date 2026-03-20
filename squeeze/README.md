# Squeeze Stock Screener (Taiwan Market) v1.1

專為台灣股市設計的自動化標的篩選工具，採用 Squeeze Momentum 擠壓動能邏輯與進階形態識別技術。

## 核心功能
- **高效能掃描**：採用混合多執行緒 (I/O) 與多處理器 (CPU) 引擎，快速掃描全台股。
- **進階形態識別**：支援 TTM Squeeze、后羿射日 (Houyi Shooting Sun) 及大鯨魚交易 (Whale Trading) 形態。
- **明確交易信號**：每檔個股皆提供明確的操作建議，如「強烈買入 (爆發)」、「觀察 (跌勢收斂)」或「觀望」。
- **中文支援**：完整支援台灣上市櫃公司之中文名稱顯示。
- **多維度過濾**：可根據市值、成交量、股價區間及百分比評分 (Value Score) 進行篩選。
- **專業報告系統**：自動生成中文 Markdown 摘要報告，並支援匯出 CSV 與 JSON。
- **自動化通知**：整合 LINE Bot 與 Email (SMTP) 通知，支援多收件人設定。
- **雲端視覺化**：每日自動生成專業的 K 線圖並附帶技術指標疊加。

## 快速開始

### 安裝
```bash
pip install ./squeeze
```

### 執行掃描
```bash
# 掃描目前的擠壓動能標的，並生成圖表與發送通知
squeeze scan --export --plot --notify
```

## 自動化設定 (GitHub Actions)
專案預設包含 `.github/workflows/daily_scan.yml`，於每個交易日 15:30 (TST) 自動執行。

### 必要的 GitHub Secrets
若要啟用通知，請在 GitHub 倉庫設定以下 Secrets：
- **`SMTP_USERNAME`**: 您的 Gmail 地址。
- **`SMTP_PASSWORD`**: 您的 Gmail 應用程式密碼。
- **`SMTP_RECIPIENT`**: (選填) 收件人信箱，多個請用逗號隔開。
- **`LINE_CHANNEL_ACCESS_TOKEN`**: (選填) LINE Bot 權杖。
- **`LINE_USER_ID`**: (選填) 您的 LINE ID。

## 開發與測試
- **執行測試**: `python3 -m pytest squeeze/tests/`
- **程式碼檢查**: `ruff check .`

---
*由 Gemini CLI 生成與維護*
