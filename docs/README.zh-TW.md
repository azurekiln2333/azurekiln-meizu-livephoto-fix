# Flyme LivePhoto Fix Tool（魅族實況照片修復工具）

[简体中文](../README.md) | 繁體中文 | [English](README.en.md)

事情的起因是近期在整理照片時，我發現此前使用魅族 21/21 Note（Flyme 12.6 以下版本）系統相機拍攝的 LivePhoto，在 Microsoft Photos 與 Google Photos 中無法被正確識別為動態照片。

理論上，這個問題僅存在於 Flyme 12.6 以下版本。目前，魅族已在最新版本 `Flyme 12.6.0.0A (2026/01/29)` 的系統相機中修復了這個相容性問題。
因此，這個專案就是為了修復這些歷史遺留的 LivePhoto 檔案相容性問題而誕生的。專案基於 ExifTool 對照片的 Exif 中繼資料進行修補，支援批次修復 Flyme 12.6 以下版本系統相機拍攝的 LivePhoto，讓它們能被 `Microsoft Photos`、`Google Photos` 等平台正確識別為動態照片。

同時，專案基於 `PyQt6` 設計了 Windows 11 風格的 GUI，並提供智慧檔案分類與匯出功能，以提升批次處理體驗。

## 核心特性

**智慧識別與修復**
- **精準分類**：自動識別並區分 Flyme 待修復動態照片、已相容動態照片、靜態照片、其他手機照片及無關檔案。
- **批次修復**：一鍵處理中繼資料，讓 Flyme 動態照片能在其他裝置或平台上正常顯示。
- **彈性匯出**：非動態照片支援原樣複製匯出，並可依檔案類別隨時啟用或停用匯出。
- **防衝突機制**：當目標目錄已有同名檔案時，可自由選擇「跳過」或「覆蓋」。

**現代化互動體驗**
- **拖曳操作**：支援直接將檔案或資料夾拖入清單，自動進行非同步掃描，並可選擇是否包含子目錄。
- **流暢清單**：支援滑鼠拖曳框選、邊緣自動捲動、多欄位資料排序。
- **便捷選單**：提供豐富的右鍵選單，支援呼叫系統預設右鍵選單、快速定位檔案、複製路徑等功能。
- **設定記憶**：自動儲存輸出目錄、介面語言、分類開關等個人偏好設定。

---

## 快速開始

### 1. 執行環境
- 作業系統：Windows 10 / 11
- 執行相依：Python 3.10+
- 核心元件：[ExifTool](https://exiftool.org/)

> **關於 ExifTool 的說明**：
> 程式會自動在以下位置尋找 `exiftool.exe`：
> 1. `vendor/exiftool/exiftool.exe`（建議放在此處）
> 2. `exiftool/exiftool.exe`
> 3. `bin/exiftool.exe`
> 4. 系統環境變數（Path）

### 2. 由原始碼執行（開發者）

複製倉庫後，安裝相依套件並啟動：

```powershell
# 建立並啟用虛擬環境
python -m venv .venv
.\.venv\Scripts\activate

# 安裝相依套件
pip install PyQt6 PyQt6-Fluent-Widgets pywin32

# 啟動程式
python main_gui.py
```

---

## 使用指南

1. **匯入檔案**：啟動程式後，將需要處理的照片或資料夾直接拖入主介面中，並依需求勾選「掃描子目錄」。
2. **確認輸出位置**：在「輸出設定」中確認或修改匯出路徑，預設為 `~/Pictures/FlymeLivePhotoFix_output`。
3. **設定篩選規則**：勾選你想匯出的檔案類型，以及遇到同名檔案時的處理策略（跳過或覆蓋）。
4. **一鍵修復／匯出**：
   - 勾選清單中需要處理的項目，拖曳匯入的新項目預設會自動勾選。
   - 點擊 **「修復並輸出」** 按鈕。
   - *說明：Flyme 待處理照片會先修復再輸出，其他已勾選的一般照片則會直接複製到目標目錄。*

> **提示**：如果只是想整理檔案而不進行修復，也可以直接使用上方的「複製勾選項目」或「移動勾選項目」功能。

---

## 打包構建

若需要將 GUI 與 `ExifTool` 打包成獨立的免安裝 `exe` 程式，請執行以下命令：

```powershell
pip install pyinstaller

pyinstaller --noconfirm --clean --windowed --name FlymeLivePhotoFix `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --add-data "vendor/exiftool;exiftool" `
  .\main_gui.py
```
*構建產物將輸出至 `dist/FlymeLivePhotoFix/` 目錄。*

---

## 專案結構與設定

- **本機設定**：使用者設定會自動儲存到 `%APPDATA%\FlymeLivePhotoFix\settings.json`。
- `main_gui.py`：主介面 UI 與基礎互動邏輯。
- `main_gui_logic.py`：檔案掃描、分類、輸出、修復的核心業務流程。
- `flyme_livephoto_fix_core.py`：基於 `ExifTool` 的底層識別與修復引擎。

## 開源授權
本專案依照倉庫中的 `LICENSE` 檔案發布。
