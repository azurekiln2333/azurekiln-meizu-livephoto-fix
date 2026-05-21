# Flyme LivePhoto Fix

[简体中文](../README.md) | [繁體中文](README.zh-TW.md) | English

Windows desktop tool built with `PyQt6 + qfluentwidgets + ExifTool` for batch-fixing Motion Photos compatibility of Meizu Flyme live photos and exporting files by category.

## Current Features

- Drag files or folders into the list and scan them asynchronously
- Optional subdirectory scanning
- Automatically classify files as:
  - Flyme live photos pending processing
  - Already processed live photos
  - Flyme static photos
  - Other camera/phone photos
  - Other files
- Checked items can be fixed and output in one step
- Non-pending live photos can be copied directly to the output folder
- Output settings support enabling or disabling each category
- Support skipping or overwriting when the target already exists
- Support right-click actions, copy file, cut file, and copy path
- Support blue drag selection box, auto-scroll drag selection, and sorting
- Automatically save configuration to local `settings.json`

## Requirements

- Windows 10/11
- Python 3.10+
- `exiftool.exe`

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install PyQt6 PyQt6-Fluent-Widgets pywin32
```

ExifTool official site: <https://exiftool.org/>

`ExifTool` must be discoverable by the application. The current code checks these locations first:

- `vendor/exiftool/exiftool.exe`
- `exiftool/exiftool.exe`
- `bin/exiftool.exe`
- `exiftool` from the system environment

## Launch

```powershell
.\.venv\Scripts\python.exe .\main_gui.py
```

## Build

To package the GUI together with the repository-bundled `ExifTool`, run:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name FlymeLivePhotoFix `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --add-data "vendor/exiftool;exiftool" `
  .\main_gui.py
```

The packaged output is written to `dist/FlymeLivePhotoFix/` by default.

## Usage

1. Start the application and confirm the output directory. The default path is `~/Pictures/FlymeLivePhotoFix_output`.
2. Drag files or folders to process into the list.
3. Decide whether to enable `Scan subdirectories`.
4. In `Output settings`, choose which file categories should be output and whether existing targets should be skipped or overwritten.
5. Check the items that should participate in the operation. Newly dropped items are checked by default.
6. Click `Fix and output`:
   - Pending Flyme live photos are fixed through `ExifTool` and then written to the output folder
   - Other enabled categories are copied directly to the output folder
7. If you only want to export currently checked items, you can still use `Copy selected` or `Move selected`.

## Interaction Notes

- The right side of the list header provides `Select all / Invert / Clear list`
- Checkboxes determine whether an item participates in output or export
- Row highlight is only a visual selection state and is independent from the checkbox state
- A blue rubber-band box is supported for drag selection, and the list auto-scrolls near the edges
- Right-clicking a file can quickly open it, locate it, copy its path, or open the system context menu

## Configuration File

The application automatically saves these settings:

- UI language
- Output directory
- Whether subdirectories are scanned
- Output category toggles
- Skip or overwrite behavior when the target already exists

On Windows, the default path is:

```text
%APPDATA%\FlymeLivePhotoFix\settings.json
```

## Core Files

- `main_gui.py`: main window and interaction logic
- `main_gui_logic.py`: classification, output, and fix workflow
- `flyme_livephoto_fix_core.py`: `ExifTool`-based detection and fix core
- `README.md`: Simplified Chinese documentation
- `docs/README.zh-TW.md`: Traditional Chinese documentation

## License

This project is distributed under the `LICENSE` file in this repository.
