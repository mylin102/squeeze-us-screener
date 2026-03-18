# BMW FRM3 Recovery Tool (D-Flash to EEPROM Converter)

這是一個專門用於修復 BMW FRM3 (腳踏空間模組) 的工具。當 FRM3 模組因電壓不穩或電池斷開導致 EEPROM 模擬區域損壞（出現 "Short Circuit" 或無法連連線）時，可以使用此工具透過 D-Flash 備份檔重新構建正確的 EEPROM 數據。

## 項目結構

- `dflash_gui.py`: 現代化的圖形介面版本（推薦使用）。
- `dflash_to_eee.py`: 核心轉換邏輯，也可作為命令行工具使用。
- `gui.py`: 基礎圖形介面版本。
- `generate_test_bin.py`: 用於產生測試用的二進位檔案。

## 功能特點

- **D-Flash 轉換**：將從 MC9S12XEQ384 晶片讀取的 32KB D-Flash 轉換為 4KB 的 EEPROM (EEE) 鏡像。
- **資訊提取**：轉換過程中會自動從數據中提取：
  - 車身號碼 (VIN)
  - 車輛選配代碼 (FA/VO)
  - 硬體編號 (HW-NR)
  - 軟體編號 (SW-NR/ZB-NR)
  - 製造日期與編程日期
- **GUI 介面**：簡單直覺的介面，支援文件瀏覽與自動命名建議。

## 使用方法

### 1. 準備工作
你需要先使用編程器（如 XPROG, VVDI Prog, CGDI 等）從 FRM3 模組中讀取並儲存 **D-Flash** 內容（通常為 32KB）。

### 2. 執行圖形介面
在終端機或命令提示字元執行：
```bash
python3 dflash_gui.py
```

### 3. 操作步驟
1. 點擊 **Browse...** 選擇讀取出的 D-Flash `.bin` 檔案。
2. 系統會自動建議輸出檔名（例如 `input_eee.bin`）。
3. 點擊醒目的 **CONVERT NOW** 按鈕。
4. 下方輸出區域會顯示提取出的車輛資訊與處理狀態。

### 4. 寫回模組
使用編程器將產生的 4KB EEPROM 檔案寫回到晶片的 **EEE** (EEPROM Emulation) 區域。

## 技術背景
BMW FRM3 模組使用的 MC9S12XEQ384 處理器沒有實體 EEPROM，而是透過 D-Flash 模擬。當模擬區域損壞時，原始數據（如 VIN, 燈光配置）其實仍然存在於 D-Flash 的循環緩衝區中。本工具透過解析 D-Flash 中的寫入指令，重新模擬出最新的 EEPROM 狀態。

---
*本工具基於 Ben van Leeuwen Autotechniek 的研究與開發。*
