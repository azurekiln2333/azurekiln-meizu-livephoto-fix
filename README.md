# Flyme LivePhoto Fix Tool (魅族实况照片修复工具)

简体中文 | [繁體中文](docs/README.zh-TW.md) | [English](docs/README.en.md)

事情的起因是近期在整理照片时，我发现此前使用 魅族21/21Note (Flyme 12.6 以下版本) 系统相机拍摄的 LivePhoto，在 Microsoft Photos 与 Google Photos 中无法被正确识别为动态照片。

理论上，该问题仅存在于 Flyme 12.6 以下版本。目前，魅族已在最新版本 `Flyme 12.6.0.0A(2026/01/29)` 的系统相机中修复了这一兼容性问题。
所以这个项目就是为了修复这些历史遗留的 LivePhoto 文件兼容性问题诞生的。项目基于 ExifTool 对照片 Exif 元数据进行修补，支持批量修复 Flyme 12.6 以下版本系统相机拍摄的 LivePhoto，使其能够被 `Microsoft Photos`、`Google Photos` 等平台正确识别为动态照片。

同时，项目基于 `PyQt6` 设计了 Windows 11 风格的 GUI，并提供智能文件分类与导出功能，以提升批量处理体验。

##  核心特性

**智能识别与修复**
- **精准分类**：自动识别并区分 Flyme 待修复动态照片、已兼容动态照片、静态照片、其他手机照片及无关文件。
- **批量修复**：一键处理元数据，让 Flyme 动态照片在其他设备或平台上正常显示。
- **灵活导出**：非动态照片支持原样复制导出，支持按文件类别随时开启/关闭导出。
- **防冲突机制**：目标目录存在同名文件时，可自由选择“跳过”或“覆盖”。

**现代化交互体验**
- **拖拽操作**：支持直接将文件或文件夹拖入列表，自动异步扫描（支持包含子目录）。
- **流畅列表**：支持鼠标拖拽框选、边缘自动滚动、多列数据排序。
- **便捷菜单**：提供丰富的右键菜单，支持调用系统默认右键菜单、快速定位文件、复制路径等。
- **配置记忆**：自动保存输出目录、界面语言、分类开关等个人偏好设置。

---

## 快速开始

### 1. 运行环境
- 操作系统：Windows 10 / 11
- 运行依赖：Python 3.10+
- 核心组件：[ExifTool](https://exiftool.org/)

> **关于 ExifTool 的说明**：
> 程序会自动在以下位置寻找 `exiftool.exe`：
> 1. `vendor/exiftool/exiftool.exe`（推荐放在此处）
> 2. `exiftool/exiftool.exe`
> 3. `bin/exiftool.exe`
> 4. 系统环境变量（Path）

### 2. 源码运行 (开发者)

克隆仓库后，安装依赖并启动：

```powershell
# 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\activate

# 安装依赖
pip install PyQt6 PyQt6-Fluent-Widgets pywin32

# 启动程序
python main_gui.py
```

---

## 使用指南

1. **导入文件**：启动程序后，将需要处理的照片或文件夹直接拖入软件主界面（按需勾选“扫描子目录”）。
2. **确认输出位置**：在“输出设置”中确认或修改导出路径（默认为 `~/Pictures/FlymeLivePhotoFix_output`）。
3. **设置过滤规则**：勾选你想要导出的文件类型，以及遇到同名文件时的处理策略（跳过/覆盖）。
4. **一键修复/导出**：
   - 勾选列表中需要处理的条目（拖拽导入的新项目默认已勾选）。
   - 点击 **“修复并输出”** 按钮。
   - *说明：Flyme 待处理照片会被修复后输出，其他被勾选的常规照片将直接复制到目标目录。*

> ** 提示**：如果只需整理文件而不做修复，可以直接使用顶部的“复制勾选项”或“移动勾选项”功能。

---

##  打包构建

如果需要将 GUI 和 `ExifTool` 打包成一个独立的免安装 `exe` 程序，请执行以下命令：

```powershell
pip install pyinstaller

pyinstaller --noconfirm --clean --windowed --name FlymeLivePhotoFix `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --add-data "vendor/exiftool;exiftool" `
  .\main_gui.py
```
*构建产物将输出至 `dist/FlymeLivePhotoFix/` 目录。*

---

## 项目结构与配置

- **本地配置**：用户设置会自动保存在 `%APPDATA%\FlymeLivePhotoFix\settings.json`。
- `main_gui.py`：主界面 UI 与基础交互逻辑。
- `main_gui_logic.py`：文件扫描、分类、输出、修复的核心业务流程。
- `flyme_livephoto_fix_core.py`：基于 `ExifTool` 的底层识别与修复引擎。

## 开源协议
本项目基于仓库中的 `LICENSE` 文件发布。