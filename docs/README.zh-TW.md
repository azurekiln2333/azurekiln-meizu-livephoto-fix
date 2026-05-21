# Flyme LivePhoto Fix

[简体中文](../README.md) | 繁體中文 | [English](README.en.md)

基於 `PyQt6 + qfluentwidgets + ExifTool` 的 Windows 桌面工具，用於批次修復魅族 Flyme 實況照片的 Motion Photos 相容性，並依分類輸出檔案。

## 目前功能

- 將檔案或資料夾拖曳到清單，非同步掃描並分類
- 支援是否掃描子目錄
- 自動識別並區分：
  - Flyme 待處理動態照片
  - 已處理好的動態照片
  - Flyme 靜態照片
  - 其他相機/手機照片
  - 其他檔案
- 勾選項目支援「修復並輸出」
- 非待處理動態照片可直接複製副本到輸出目錄
- 輸出設定支援依類別啟用或停用
- 支援目標已存在時跳過或覆蓋
- 支援右鍵選單、複製檔案、剪下檔案、複製路徑
- 支援滑鼠藍色框選、自動捲動框選與排序
- 設定會自動儲存到本機 `settings.json`

## 執行環境

- Windows 10/11
- Python 3.10+
- `exiftool.exe`

## 安裝相依套件

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install PyQt6 PyQt6-Fluent-Widgets pywin32
```

ExifTool 官網：<https://exiftool.org/>

`ExifTool` 需要能被程式找到。當前程式碼會優先查找這些位置：

- `vendor/exiftool/exiftool.exe`
- `exiftool/exiftool.exe`
- `bin/exiftool.exe`
- 系統環境變數中的 `exiftool`

## 啟動方式

```powershell
.\.venv\Scripts\python.exe .\main_gui.py
```

## 構建命令

如需將 GUI 與倉庫內建的 `ExifTool` 一起打包，可執行：

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name FlymeLivePhotoFix `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --add-data "vendor/exiftool;exiftool" `
  .\main_gui.py
```

構建完成後，產物預設輸出到 `dist/FlymeLivePhotoFix/`。

## 使用說明

1. 啟動程式後，確認輸出目錄。預設目錄為 `~/Pictures/FlymeLivePhotoFix_output`。
2. 將需要處理的檔案或資料夾拖入清單。
3. 依需求決定是否勾選「掃描子目錄」。
4. 在「輸出設定」中選擇要輸出的檔案類型，以及「目標已存在時跳過/覆蓋」策略。
5. 勾選要參與處理的項目。拖曳新增項目預設會自動勾選。
6. 點擊「修復並輸出」：
   - Flyme 待處理動態照片會呼叫 `ExifTool` 修復後輸出
   - 其他已啟用類別會直接複製副本到輸出目錄
7. 如需單純複製或移動目前勾選項目，也可以使用「複製勾選項目 / 移動勾選項目」。

## 互動說明

- 清單頂部右側提供：`全選 / 反選 / 清空清單`
- 核取方塊決定項目是否參與輸出或匯出
- 列選取陰影只表示視覺選取，不等於核取方塊狀態
- 支援滑鼠拖曳藍色框選，拖到邊緣時會自動捲動
- 右鍵檔案可快速開啟、定位、複製路徑，也可呼叫系統右鍵選單

## 設定檔

程式會自動儲存以下設定：

- 介面語言
- 輸出目錄
- 是否掃描子目錄
- 輸出類型開關
- 目標已存在時跳過或覆蓋

Windows 下預設儲存到：

```text
%APPDATA%\FlymeLivePhotoFix\settings.json
```

## 核心檔案

- `main_gui.py`：主介面與互動邏輯
- `main_gui_logic.py`：分類、輸出與修復流程
- `flyme_livephoto_fix_core.py`：基於 `ExifTool` 的識別與修復核心
- `README.md`：簡體中文文件
- `docs/README.en.md`：英文文件

## 授權

本專案依照倉庫中的 `LICENSE` 檔案發布。
