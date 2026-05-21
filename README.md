# Flyme LivePhoto Fix

简体中文 | [繁體中文](docs/README.zh-TW.md) | [English](docs/README.en.md)

基于 `PyQt6 + qfluentwidgets + ExifTool` 的 Windows 桌面工具，用于批量修复魅族 Flyme 实况照片的 Motion Photos 兼容性，并按分类输出文件。

## 当前功能

- 拖拽文件或文件夹到列表，异步扫描并分类
- 支持是否扫描子目录
- 自动识别并区分：
  - Flyme 待处理动态照片
  - 已处理好的动态照片
  - Flyme 静态照片
  - 其他相机/手机照片
  - 其他文件
- 勾选项支持“修复并输出”
- 非待处理动态照片可直接复制副本到输出目录
- 输出设置支持按类别启用/禁用
- 支持目标已存在时跳过或覆盖
- 支持右键菜单、复制文件、剪切文件、复制路径
- 支持鼠标蓝色框选、自动滚动框选、排序
- 配置自动保存到本地 `settings.json`

## 运行环境

- Windows 10/11
- Python 3.10+
- `exiftool.exe`

## 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install PyQt6 PyQt6-Fluent-Widgets pywin32
```

ExifTool 官网：<https://exiftool.org/>

`ExifTool` 需要能被程序找到。当前代码会优先查找这些位置：

- `vendor/exiftool/exiftool.exe`
- `exiftool/exiftool.exe`
- `bin/exiftool.exe`
- 系统环境变量中的 `exiftool`

## 启动方式

```powershell
.\.venv\Scripts\python.exe .\main_gui.py
```

## 构建命令

如需将 GUI 和仓库内置的 `ExifTool` 一起打包，可执行：

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name FlymeLivePhotoFix `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --add-data "vendor/exiftool;exiftool" `
  .\main_gui.py
```

构建完成后，产物默认输出到 `dist/FlymeLivePhotoFix/`。

## 使用说明

1. 启动程序后，确认输出目录。默认目录为 `~/Pictures/FlymeLivePhotoFix_output`。
2. 将需要处理的文件或文件夹拖入列表。
3. 根据需要决定是否勾选“扫描子目录”。
4. 在“输出设置”里选择要输出的文件类型，以及“目标已存在时跳过/覆盖”策略。
5. 勾选要参与处理的条目。拖拽新增项目默认会自动勾选。
6. 点击“修复并输出”：
   - Flyme 待处理动态照片会调用 `ExifTool` 修复后输出
   - 其他已启用类别会直接复制副本到输出目录
7. 如需单纯复制/移动当前勾选项，也可以使用“复制勾选项 / 移动勾选项”。

## 交互说明

- 列表顶部右侧提供：`全选 / 反选 / 清空列表`
- 复选框决定条目是否参与输出或导出
- 行选中阴影只表示视觉选中，不等于复选框状态
- 支持鼠标拖拽蓝色框选，拖到边缘会自动滚动
- 右键文件可快速打开、定位、复制路径，也可调用系统右键菜单

## 配置文件

程序会自动保存以下设置：

- 界面语言
- 输出目录
- 是否扫描子目录
- 输出类型开关
- 目标已存在时跳过/覆盖

Windows 下默认保存到：

```text
%APPDATA%\FlymeLivePhotoFix\settings.json
```

## 核心文件

- `main_gui.py`：主界面与交互逻辑
- `main_gui_logic.py`：分类、输出、修复流程
- `flyme_livephoto_fix_core.py`：基于 `ExifTool` 的识别与修复核心
- `docs/README.en.md`：英文文档

## 许可

本项目基于仓库中的 `LICENSE` 文件发布。
