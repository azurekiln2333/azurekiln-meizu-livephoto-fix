# Flyme LivePhoto Fix

[中文](../README.md) | [English](README.en.md)

## Overview

This desktop tool (built with `PyQt6 + qfluentwidgets`) helps batch-fix compatibility issues for Meizu LivePhoto images.

Main capabilities:

- Drag-and-drop import for `JPG/JPEG` files and folders
- Batch fix selected items
- Batch copy/move selected items
- Right-click context actions per item

## Key Features

- PyQt6-only Qt stack
- Blue immersive title bar
- Asynchronous drag-drop parsing (background worker)
- Mouse drag multi-selection with a blue rubber-band box
- Clickable header sorting
- Sorting clears row highlight only (checkbox states remain unchanged)
- Default output directory:
  - `~/Pictures/FlymeLivePhotoFix`
  - Auto-created if missing

## Requirements

- Windows 10/11 (recommended)
- Python 3.10+

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install PyQt6 PyQt6-Fluent-Widgets pywin32
```

## Run

```powershell
.\.venv\Scripts\python.exe .\main_gui.py
```

## Usage

1. Start the app and verify output directory.
2. Drag image files/folders into the list.
3. Select items to process (drag-added items are checked by default).
4. Use bottom actions:
   - Fix selected
   - Copy selected
   - Move selected
5. Right-click an item for quick actions or open Windows system context menu.

## Interaction Notes

- Checkbox state controls processing/export participation.
- Row highlight is visual selection only.
- Sorting clears row highlight but keeps checkbox states unchanged.

## Core Files

- `main_gui.py`: UI and interaction layer
- `main_gui_logic.py`: batch processing/export logic
- `flyme_livephoto_fix_core.py`: detection/fix core

## License

See repository `LICENSE`.
