# Flyme LivePhoto Fix Tool (Meizu Live Photo Repair Tool)

[简体中文](../README.md) | [繁體中文](README.zh-TW.md) | English

It started when I was organizing photos recently and found that Live Photos taken with the system camera on the Meizu 21/21 Note running versions earlier than Flyme 12.6 could not be correctly recognized as motion photos in Microsoft Photos and Google Photos.

In theory, this issue only exists on versions earlier than Flyme 12.6. Meizu has already fixed this compatibility issue in the system camera of the latest version, `Flyme 12.6.0.0A (2026/01/29)`.
This project was created to fix those legacy LivePhoto file compatibility issues. Based on ExifTool, it patches photo EXIF metadata and supports batch repair of Live Photos taken with the system camera on versions earlier than Flyme 12.6, so they can be correctly recognized as motion photos by platforms such as `Microsoft Photos` and `Google Photos`.

At the same time, the project provides a Windows 11-style GUI built with `PyQt6`, along with intelligent file classification and export features, to improve the batch processing experience.

## Core Features

**Smart Detection and Repair**
- **Accurate classification**: Automatically identifies and separates Flyme live photos that need fixing, already compatible live photos, static photos, other mobile photos, and unrelated files.
- **Batch repair**: Processes metadata in one click so Flyme live photos can display properly on other devices or platforms.
- **Flexible export**: Non-live photos can be copied out as-is, and export can be enabled or disabled by file category at any time.
- **Conflict prevention**: When a file with the same name already exists in the target directory, you can choose to skip it or overwrite it.

**Modern Interaction Experience**
- **Drag-and-drop workflow**: Drag files or folders directly into the list for automatic asynchronous scanning, with optional subdirectory scanning.
- **Smooth list operations**: Supports drag selection, edge auto-scroll, and multi-column sorting.
- **Convenient menus**: Provides rich right-click actions, including the system context menu, quick file location, copy path, and more.
- **Preference persistence**: Automatically saves personal settings such as output directory, UI language, and category toggles.

---

## Quick Start

### 1. Requirements
- Operating system: Windows 10 / 11
- Runtime dependency: Python 3.10+
- Core component: [ExifTool](https://exiftool.org/)

> **About ExifTool**:
> The program will automatically look for `exiftool.exe` in the following locations:
> 1. `vendor/exiftool/exiftool.exe` (recommended)
> 2. `exiftool/exiftool.exe`
> 3. `bin/exiftool.exe`
> 4. System environment variable (`Path`)

### 2. Run from Source (Developers)

After cloning the repository, install the dependencies and start the app:

```powershell
# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install PyQt6 PyQt6-Fluent-Widgets pywin32

# Launch the application
python main_gui.py
```

---

## Usage Guide

1. **Import files**: After starting the application, drag the photos or folders you want to process into the main window directly. Enable `Scan subdirectories` if needed.
2. **Confirm output location**: In `Output settings`, confirm or change the export path. The default path is `~/Pictures/FlymeLivePhotoFix_output`.
3. **Set filtering rules**: Choose which file types should be exported and how duplicate file names should be handled: skip or overwrite.
4. **One-click repair/export**:
   - Check the items you want to process. Newly imported items are checked by default.
   - Click the **`Fix and output`** button.
   - *Note: Flyme live photos pending processing will be repaired before export, while other checked regular photos will be copied directly to the target directory.*

> **Tip**: If you only want to organize files without repairing them, you can directly use the `Copy selected` or `Move selected` actions at the top.

---

## Packaging Build

If you want to package the GUI and `ExifTool` into a standalone portable `exe`, run:

```powershell
pip install pyinstaller

pyinstaller --noconfirm --clean --windowed --name FlymeLivePhotoFix `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --add-data "vendor/exiftool;exiftool" `
  .\main_gui.py
```
*The build output will be written to `dist/FlymeLivePhotoFix/`.*

---

## Project Structure and Configuration

- **Local configuration**: User settings are automatically saved to `%APPDATA%\FlymeLivePhotoFix\settings.json`.
- `main_gui.py`: Main UI and basic interaction logic.
- `main_gui_logic.py`: Core workflow for file scanning, classification, output, and repair.
- `flyme_livephoto_fix_core.py`: Low-level detection and repair engine built on `ExifTool`.

## License
This project is distributed under the `LICENSE` file in the repository.
