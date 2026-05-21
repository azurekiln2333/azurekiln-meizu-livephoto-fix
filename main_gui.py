from __future__ import annotations

import sys
import importlib
import subprocess
import os
import ctypes
from pathlib import Path
from uuid import uuid4

from main_gui_logic import PhotoItem, export_items, fix_items, format_size
from flyme_livephoto_fix_core import LivePhotoFixTool, check_photo_type
from qframelesswindow import FramelessMainWindow, StandardTitleBar

from PyQt6.QtCore import QEvent, QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

QT_BINDING = "PyQt6"

if sys.platform == "win32":
    import win32con  # type: ignore
    import win32gui  # type: ignore
    from win32com.shell import shell, shellcon  # type: ignore


def _get_windows_pictures_dir() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        f_id_pictures = GUID(
            0x33E28130,
            0x4E1E,
            0x4676,
            (ctypes.c_ubyte * 8)(0x83, 0x5A, 0x98, 0x39, 0x5C, 0x3B, 0xC3, 0xBB),
        )
        out_path = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(f_id_pictures), 0, None, ctypes.byref(out_path))
        if hr != 0 or not out_path.value:
            return None
        path = Path(out_path.value)
        ole32.CoTaskMemFree(out_path)
        return path
    except Exception:
        return None


class DropScanWorker(QObject):
    batch_ready = pyqtSignal(object)
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int)

    def __init__(self, paths: list[Path], existing: set[Path]):
        super().__init__()
        self.paths = paths
        self.existing = existing

    def _iter_jpg_files(self) -> list[Path]:
        files: list[Path] = []
        for p in self.paths:
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}:
                files.append(p)
                continue
            if not p.is_dir():
                continue
            try:
                for root, _dirs, names in os.walk(p):
                    base = Path(root)
                    for name in names:
                        if name.lower().endswith((".jpg", ".jpeg")):
                            files.append(base / name)
            except Exception:
                continue
        return sorted(set(files), key=lambda x: str(x))

    def _build_item(self, jpg_path: Path) -> PhotoItem:
        try:
            size_str = format_size(jpg_path.stat().st_size)
            is_meizu, is_live, is_fixed = check_photo_type(jpg_path)
        except Exception:
            size_str, is_meizu, is_live, is_fixed = "?", False, False, False

        needs_process = is_live and not is_fixed
        if needs_process:
            status = "status_pending"
        elif is_fixed:
            status = "status_fixed_compatible"
        elif not is_meizu:
            status = "status_not_meizu"
        else:
            status = "status_static"

        return PhotoItem(
            item_id=f"drop_{uuid4().hex}",
            jpg_path=jpg_path,
            rel_path=Path(jpg_path.name),
            size_str=size_str,
            is_meizu=is_meizu,
            is_live=is_live,
            is_fixed=is_fixed,
            needs_process=needs_process,
            status=status,
        )

    def run(self):
        all_files = self._iter_jpg_files()
        candidates: list[Path] = []
        seen = set()
        for p in all_files:
            try:
                rp = p.resolve()
            except Exception:
                rp = p
            if rp in self.existing or rp in seen:
                continue
            seen.add(rp)
            candidates.append(p)

        total = len(candidates)
        if total == 0:
            self.finished.emit(0, 0)
            return

        batch: list[PhotoItem] = []
        added = 0
        for idx, p in enumerate(candidates, start=1):
            batch.append(self._build_item(p))
            added += 1
            if len(batch) >= 12:
                self.batch_ready.emit(batch)
                batch = []
            if idx % 8 == 0 or idx == total:
                self.progress.emit(idx, total, "analyzing")

        if batch:
            self.batch_ready.emit(batch)
        self.finished.emit(added, total)


def _import_fluent():
    module_candidates = (
        ("qfluentwidgetspro", True),
        ("qfluentwidgets_pro", True),
        ("qfluentwidgets", False),
    )

    module = None
    is_pro = False
    last_exc = None
    for mod_name, pro_flag in module_candidates:
        try:
            module = importlib.import_module(mod_name)
            is_pro = pro_flag
            break
        except Exception as exc:
            last_exc = exc

    if module is None:
        raise ImportError(
            "未安装 qfluentwidgets。请安装对应版本：\n"
            "- PyQt6: pip install PyQt6-Fluent-Widgets\n"
            "如果你要使用 Pro，请按官方文档安装 Pro 版本。"
        ) from last_exc

    return {
        "ok": True,
        "theme": module.Theme,
        "set_theme": module.setTheme,
        "PrimaryPushButton": module.PrimaryPushButton,
        "PushButton": module.PushButton,
        "LineEdit": module.LineEdit,
        "TableWidget": module.TableWidget,
        "ProgressBar": module.ProgressBar,
        "CheckBox": module.CheckBox,
        "RadioButton": module.RadioButton,
        "CardWidget": module.CardWidget,
        "SubtitleLabel": module.SubtitleLabel,
        "BodyLabel": module.BodyLabel,
        "InfoBar": module.InfoBar,
        "InfoBarPosition": module.InfoBarPosition,
        "FluentIcon": module.FluentIcon,
        "ToolButton": module.ToolButton,
        "set_theme_color": module.setThemeColor,
        "is_pro": is_pro,
    }


FW = _import_fluent()
Theme = FW["theme"]
setTheme = FW["set_theme"]
PrimaryPushButton = FW["PrimaryPushButton"]
PushButton = FW["PushButton"]
LineEdit = FW["LineEdit"]
TableWidget = FW["TableWidget"]
ProgressBar = FW["ProgressBar"]
CheckBox = FW["CheckBox"]
RadioButton = FW["RadioButton"]
CardWidget = FW["CardWidget"]
SubtitleLabel = FW["SubtitleLabel"]
BodyLabel = FW["BodyLabel"]
InfoBar = FW["InfoBar"]
InfoBarPosition = FW["InfoBarPosition"]
FluentIcon = FW["FluentIcon"]
ToolButton = FW["ToolButton"]
setThemeColor = FW["set_theme_color"]
IS_PRO = FW["is_pro"]


TRANSLATIONS = {
    "zh": {
        "app_title": "Meizu LivePhoto Fix",
        "missing_dependency_title": "依赖缺失",
        "header_title": "魅族Flyme实况图LivePhoto兼容修复",
        "header_subtitle": "修复兼容MotionPhotos支持，支持复制或移动导出",
        "language": "界面语言",
        "output_placeholder": "输出目录（默认图片目录）",
        "choose_output": "选择输出目录",
        "output_dir": "输出目录",
        "skip_existing": "目标已存在时跳过",
        "overwrite_existing": "目标已存在时覆盖",
        "fix_checked": "修复勾选项",
        "copy_checked": "复制勾选项",
        "move_checked": "移动勾选项",
        "select_all": "全选",
        "invert_selection": "反选",
        "clear_list": "清空列表",
        "drop_hint": "支持拖拽 JPG/JPEG 文件或文件夹到列表区域",
        "table_checked": "勾选",
        "table_rel_path": "相对路径",
        "table_size": "大小",
        "table_meizu": "魅族",
        "table_live": "实况",
        "table_status": "状态",
        "waiting_choose_dir": "等待选择目录",
        "waiting_drop": "等待拖拽文件到列表",
        "dialog_choose_output": "选择输出目录",
        "open": "打开",
        "open_folder": "打开所在目录",
        "copy_path": "复制路径",
        "system_context_menu": "系统右键菜单...",
        "yes": "是",
        "no": "否",
        "busy_title": "正在处理",
        "busy_content": "上一批拖拽仍在处理中，请稍候",
        "parsing_drop": "正在解析拖拽文件...",
        "adding_files": "正在添加文件 {done}/{total}",
        "no_new_jpg": "未发现可新增 JPG/JPEG",
        "no_new_title": "未新增",
        "no_new_content": "拖入文件已全部存在于列表中或格式不支持",
        "drop_done_status": "拖拽完成：新增 {added}/{total}，当前共 {count} 项",
        "drop_done_title": "拖拽添加完成",
        "added_count": "新增 {added}/{total}",
        "list_cleared": "列表已清空",
        "list_cleared_content": "列表已清空，等待拖拽文件",
        "hint": "提示",
        "select_export_first": "请先勾选要导出的照片",
        "dialog_choose_export": "选择导出目录",
        "copying": "复制中 {i}/{n}: {name}",
        "moving": "移动中 {i}/{n}: {name}",
        "export_done_status": "导出完成: 成功 {success} / 失败 {failed}",
        "export_done_title": "导出完成",
        "success_failed": "成功 {success} / 失败 {failed}",
        "choose_output_first": "请先选择输出目录",
        "no_fix_items": "勾选项中没有待修复照片",
        "fixing": "修复中 {i}/{n}: {name} - {status}",
        "fix_done_status": "完成: 成功 {success} / 失败 {failed} / 冲突跳过 {skipped}",
        "fix_done_title": "修复完成",
        "fix_done_content": "成功 {success} / 失败 {failed} / 冲突跳过 {skipped}",
        "status_pending": "等待处理",
        "status_fixed_compatible": "已修复兼容",
        "status_not_meizu": "非魅族设备照片",
        "status_static": "魅族普通静态图",
        "status_skip_exists": "跳过(目标已存在)",
        "status_fixing": "正在修复",
        "status_fix_success": "修复成功",
        "status_failed_prefix": "失败:",
    },
    "en": {
        "app_title": "Meizu LivePhoto Fix",
        "missing_dependency_title": "Missing dependency",
        "header_title": "Meizu Flyme LivePhoto Compatibility Fix",
        "header_subtitle": "Fix Motion Photos compatibility, then copy or move selected photos",
        "language": "Language",
        "output_placeholder": "Output folder (Pictures by default)",
        "choose_output": "Choose output folder",
        "output_dir": "Output folder",
        "skip_existing": "Skip when target exists",
        "overwrite_existing": "Overwrite when target exists",
        "fix_checked": "Fix selected",
        "copy_checked": "Copy selected",
        "move_checked": "Move selected",
        "select_all": "Select all",
        "invert_selection": "Invert selection",
        "clear_list": "Clear list",
        "drop_hint": "Drag JPG/JPEG files or folders into the list",
        "table_checked": "Selected",
        "table_rel_path": "Relative path",
        "table_size": "Size",
        "table_meizu": "Meizu",
        "table_live": "Live",
        "table_status": "Status",
        "waiting_choose_dir": "Waiting for output folder",
        "waiting_drop": "Drop files into the list",
        "dialog_choose_output": "Choose output folder",
        "open": "Open",
        "open_folder": "Show in folder",
        "copy_path": "Copy path",
        "system_context_menu": "System context menu...",
        "yes": "Yes",
        "no": "No",
        "busy_title": "Processing",
        "busy_content": "The previous drop batch is still being processed. Please wait.",
        "parsing_drop": "Analyzing dropped files...",
        "adding_files": "Adding files {done}/{total}",
        "no_new_jpg": "No new JPG/JPEG files found",
        "no_new_title": "No files added",
        "no_new_content": "All dropped files already exist in the list or use an unsupported format.",
        "drop_done_status": "Drop complete: added {added}/{total}, {count} items total",
        "drop_done_title": "Drop complete",
        "added_count": "Added {added}/{total}",
        "list_cleared": "List cleared",
        "list_cleared_content": "The list is empty. Drop files to continue.",
        "hint": "Notice",
        "select_export_first": "Select photos to export first.",
        "dialog_choose_export": "Choose export folder",
        "copying": "Copying {i}/{n}: {name}",
        "moving": "Moving {i}/{n}: {name}",
        "export_done_status": "Export complete: {success} succeeded / {failed} failed",
        "export_done_title": "Export complete",
        "success_failed": "{success} succeeded / {failed} failed",
        "choose_output_first": "Choose an output folder first.",
        "no_fix_items": "No selected photos need fixing.",
        "fixing": "Fixing {i}/{n}: {name} - {status}",
        "fix_done_status": "Complete: {success} succeeded / {failed} failed / {skipped} skipped",
        "fix_done_title": "Fix complete",
        "fix_done_content": "{success} succeeded / {failed} failed / {skipped} skipped",
        "status_pending": "Pending",
        "status_fixed_compatible": "Already compatible",
        "status_not_meizu": "Not a Meizu photo",
        "status_static": "Meizu static photo",
        "status_skip_exists": "Skipped (target exists)",
        "status_fixing": "Fixing",
        "status_fix_success": "Fixed",
        "status_failed_prefix": "Failed:",
    },
}


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


class MainWindow(FramelessMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "zh"
        self._last_status_key = "waiting_choose_dir"
        self._last_status_kwargs = {}
        self.setWindowTitle(self.tr("app_title"))
        self.resize(1280, 860)
        self._title_bar_height = 36
        self._set_blue_title_bar()

        self.items: dict[str, PhotoItem] = {}
        self._drop_thread: QThread | None = None
        self._drop_worker: DropScanWorker | None = None
        self._suspend_selection_sync = False

        try:
            self.engine = LivePhotoFixTool()
        except FileNotFoundError as e:
            QMessageBox.critical(self, self.tr("missing_dependency_title"), str(e))
            raise

        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, self._title_bar_height + 12, 20, 18)
        outer.setSpacing(12)

        header_card = CardWidget(self)
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(4)

        self.title_label = SubtitleLabel(self.tr("header_title"), self)
        title_font = QFont("Segoe UI", 15)
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.subtitle_label = BodyLabel(self.tr("header_subtitle"), self)
        self.subtitle_label.setStyleSheet("color: #667085;")

        self.language_label = BodyLabel(self.tr("language"), self)
        self.language_combo = QComboBox(self)
        self.language_combo.addItem("中文", "zh")
        self.language_combo.addItem("English", "en")
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row = QHBoxLayout()
        language_row.addStretch(1)
        language_row.addWidget(self.language_label)
        language_row.addWidget(self.language_combo)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.subtitle_label)
        header_layout.addLayout(language_row)

        path_card = CardWidget(self)
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(16, 14, 16, 14)
        path_layout.setSpacing(10)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.output_edit = LineEdit(self)
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText(self.tr("output_placeholder"))
        self.btn_output = PushButton(self.tr("choose_output"), self)
        self.btn_output.clicked.connect(self.choose_output)
        self.output_label = BodyLabel(self.tr("output_dir"), self)
        row2.addWidget(self.output_label)
        row2.addWidget(self.output_edit, 1)
        row2.addWidget(self.btn_output)

        path_layout.addLayout(row2)

        option_card = CardWidget(self)
        option_layout = QVBoxLayout(option_card)
        option_layout.setContentsMargins(16, 14, 16, 14)
        option_layout.setSpacing(10)

        row3 = QHBoxLayout()
        row3.setSpacing(12)
        self.skip_radio = RadioButton(self.tr("skip_existing"), self)
        self.overwrite_radio = RadioButton(self.tr("overwrite_existing"), self)
        self.skip_radio.setChecked(True)
        row3.addStretch(1)
        row3.addWidget(self.skip_radio)
        row3.addWidget(self.overwrite_radio)
        option_layout.addLayout(row3)

        action_card = CardWidget(self)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(8)

        row4 = QHBoxLayout()
        row4.setSpacing(8)
        self.btn_fix = PrimaryPushButton(self.tr("fix_checked"), self)
        self.btn_fix.clicked.connect(self.fix_checked)

        self.btn_copy = PushButton(self.tr("copy_checked"), self)
        self.btn_copy.clicked.connect(lambda: self.export_checked("copy"))

        self.btn_move = PushButton(self.tr("move_checked"), self)
        self.btn_move.clicked.connect(lambda: self.export_checked("move"))

        self.btn_all = ToolButton(_pick_icon("SELECT_ALL", "CHECKBOX", "ACCEPT"), self)
        self.btn_all.setToolTip(self.tr("select_all"))
        self.btn_all.clicked.connect(self.select_all_rows)

        self.btn_invert = ToolButton(_pick_icon("SYNC", "SWITCH", "UPDATE"), self)
        self.btn_invert.setToolTip(self.tr("invert_selection"))
        self.btn_invert.clicked.connect(self.invert_rows)

        self.btn_clear = PushButton(self.tr("clear_list"), self)
        self.btn_clear.clicked.connect(self.clear_list)

        row4.addStretch(1)
        row4.addWidget(self.btn_fix)
        row4.addWidget(self.btn_copy)
        row4.addWidget(self.btn_move)
        row4.addSpacing(8)
        row4.addWidget(self.btn_all)
        row4.addWidget(self.btn_invert)
        row4.addWidget(self.btn_clear)
        action_layout.addLayout(row4)

        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(8)

        self.drop_hint = BodyLabel(self.tr("drop_hint"), self)
        self.drop_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")

        self.table = TableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(self._table_headers())
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setAcceptDrops(True)
        self.table.viewport().setAcceptDrops(True)
        self.table.viewport().installEventFilter(self)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_sort_clicked)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(56)
        self.table.verticalHeader().setDefaultSectionSize(36)

        table_layout.addWidget(self.drop_hint)
        table_layout.addWidget(self.table)

        foot_card = CardWidget(self)
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setContentsMargins(16, 12, 16, 12)
        foot_layout.setSpacing(10)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(14)
        self.progress.setMinimumWidth(280)
        self.progress.setMaximumWidth(420)
        self.status = BodyLabel(self.tr("waiting_choose_dir"), self)
        self.status.setStyleSheet("color: #475467;")
        foot_layout.addStretch(1)
        foot_layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        foot_layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        outer.addWidget(header_card)
        outer.addWidget(path_card)
        outer.addWidget(option_card)
        outer.addWidget(table_card, 1)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)
        self._init_default_output_dir()
        self._sync_title_bar()

    def tr(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS.get(self.lang, TRANSLATIONS["zh"]).get(key, key)
        return text.format(**kwargs) if kwargs else text

    def _table_headers(self) -> list[str]:
        return [
            self.tr("table_checked"),
            self.tr("table_rel_path"),
            self.tr("table_size"),
            self.tr("table_meizu"),
            self.tr("table_live"),
            self.tr("table_status"),
        ]

    def _set_status_text(self, key: str, **kwargs):
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self.status.setText(self.tr(key, **kwargs))

    def _display_status(self, status: str) -> str:
        key = status
        if key is not None:
            return self.tr(key)
        failed_prefix = "失败:"
        if status.startswith(failed_prefix):
            return f"{self.tr('status_failed_prefix')} {status[len(failed_prefix):].strip()}"
        return status

    def _on_language_changed(self, _index: int):
        lang = self.language_combo.currentData()
        if lang not in TRANSLATIONS or lang == self.lang:
            return
        self.lang = lang
        self._apply_language()

    def _apply_language(self):
        self.setWindowTitle(self.tr("app_title"))
        self.title_label.setText(self.tr("header_title"))
        self.subtitle_label.setText(self.tr("header_subtitle"))
        self.language_label.setText(self.tr("language"))
        self.output_edit.setPlaceholderText(self.tr("output_placeholder"))
        self.btn_output.setText(self.tr("choose_output"))
        self.output_label.setText(self.tr("output_dir"))
        self.skip_radio.setText(self.tr("skip_existing"))
        self.overwrite_radio.setText(self.tr("overwrite_existing"))
        self.btn_fix.setText(self.tr("fix_checked"))
        self.btn_copy.setText(self.tr("copy_checked"))
        self.btn_move.setText(self.tr("move_checked"))
        self.btn_all.setToolTip(self.tr("select_all"))
        self.btn_invert.setToolTip(self.tr("invert_selection"))
        self.btn_clear.setText(self.tr("clear_list"))
        self.drop_hint.setText(self.tr("drop_hint"))
        self.table.setHorizontalHeaderLabels(self._table_headers())
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        self._refresh_table()

    def _cell_checkbox(self, row: int) -> CheckBox | None:
        wrap = self.table.cellWidget(row, 0)
        if wrap is None:
            return None
        cb = wrap.findChild(CheckBox)
        return cb if isinstance(cb, CheckBox) else None

    def _set_blue_title_bar(self):
        self.setTitleBar(StandardTitleBar(self))
        self._title_bar_height = self.titleBar.height()
        self.titleBar.setStyleSheet(
            """
            QWidget {
                background: #1677FF;
            }
            QLabel {
                color: #FFFFFF;
                background: transparent;
            }
            """
        )
        for btn in (self.titleBar.minBtn, self.titleBar.maxBtn, self.titleBar.closeBtn):
            btn.setNormalBackgroundColor("#00000000")
            btn.setHoverBackgroundColor("#33FFFFFF")
            btn.setPressedBackgroundColor("#55FFFFFF")

    def _sync_title_bar(self):
        if not hasattr(self, "titleBar"):
            return
        self.titleBar.move(0, 0)
        self.titleBar.resize(self.width(), self._title_bar_height)
        self.titleBar.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        self._sync_title_bar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sync_title_bar()

    def _notify(self, title: str, content: str, is_error: bool = False):
        if is_error:
            InfoBar.error(
                title=title,
                content=content,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2200,
                parent=self,
            )
            return

        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1800,
            parent=self,
        )

    def _on_header_sort_clicked(self, _logical_index: int):
        # Keep checkbox state as-is, only clear visual row selection highlight.
        self._suspend_selection_sync = True
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self._suspend_selection_sync = False

    def _sync_checks_to_selection(self):
        if self._suspend_selection_sync:
            return
        selected_rows = {idx.row() for idx in self.table.selectionModel().selectedRows()}
        for row in range(self.table.rowCount()):
            cb = self._cell_checkbox(row)
            if isinstance(cb, CheckBox):
                cb.setChecked(row in selected_rows)

    def _init_default_output_dir(self):
        pics_dir = _get_windows_pictures_dir() or (Path.home() / "Pictures")
        base = pics_dir / "FlymeLivePhotoFix"
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.output_edit.setText(str(base))
        self._set_status_text("waiting_drop")

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, self.tr("dialog_choose_output"))
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)
            self.output_edit.setText(path)

    def _selected_items(self) -> list[PhotoItem]:
        selected: list[PhotoItem] = []
        for row in range(self.table.rowCount()):
            cb = self._cell_checkbox(row)
            if isinstance(cb, CheckBox) and cb.isChecked():
                item_id = cb.property("item_id")
                if isinstance(item_id, str) and item_id in self.items:
                    selected.append(self.items[item_id])
        return selected

    def _set_row_status(self, item_id: str, status: str):
        for row in range(self.table.rowCount()):
            cb = self._cell_checkbox(row)
            if isinstance(cb, CheckBox) and cb.property("item_id") == item_id:
                self.table.setItem(row, 5, QTableWidgetItem(self._display_status(status)))
                return

    def _item_from_row(self, row: int) -> PhotoItem | None:
        if row < 0:
            return None
        cb = self._cell_checkbox(row)
        if not isinstance(cb, CheckBox):
            return None
        item_id = cb.property("item_id")
        if not isinstance(item_id, str):
            return None
        return self.items.get(item_id)

    def _get_shell_verbs(self, path: Path) -> list[tuple[str, object]]:
        try:
            import win32com.client  # type: ignore
        except Exception:
            return []

        try:
            shell = win32com.client.Dispatch("Shell.Application")
            folder = shell.NameSpace(str(path.parent))
            if folder is None:
                return []
            file_item = folder.ParseName(path.name)
            if file_item is None:
                return []
            verbs = []
            for verb in file_item.Verbs():
                name = str(verb.Name).replace("&", "").strip()
                if not name:
                    continue
                verbs.append((name, verb))
            return verbs
        except Exception:
            return []

    def _show_explorer_context_menu(self, file_paths: list[Path], global_pos) -> bool:
        if sys.platform != "win32" or not file_paths:
            return False

        try:
            folder = shell.SHGetDesktopFolder()
            abs_paths = [str(p.resolve()) for p in file_paths]
            parent_dir = str(Path(abs_paths[0]).parent)

            parent_pidl = shell.SHParseDisplayName(parent_dir, 0)[0]
            parent_folder = folder.BindToObject(parent_pidl, None, shell.IID_IShellFolder)

            child_pidls = []
            for p in abs_paths:
                rel_name = Path(p).name
                child_pidl = parent_folder.ParseDisplayName(0, None, rel_name)[1]
                child_pidls.append(child_pidl)

            _inout, cm = parent_folder.GetUIObjectOf(
                int(self.table.winId()),
                child_pidls,
                shell.IID_IContextMenu,
                0,
                shell.IID_IContextMenu,
            )

            hmenu = win32gui.CreatePopupMenu()
            try:
                id_cmd_first = 1
                flags = shellcon.CMF_NORMAL
                cm.QueryContextMenu(hmenu, 0, id_cmd_first, 0x7FFF, flags)

                win32gui.SetForegroundWindow(int(self.table.winId()))
                cmd = win32gui.TrackPopupMenu(
                    hmenu,
                    win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON,
                    global_pos.x(),
                    global_pos.y(),
                    0,
                    int(self.table.winId()),
                    None,
                )
            finally:
                win32gui.DestroyMenu(hmenu)

            if cmd:
                ci = (0, int(self.table.winId()), cmd - id_cmd_first, None, parent_dir, 0, 0, 0)
                cm.InvokeCommand(ci)
            else:
                win32gui.PostMessage(int(self.table.winId()), win32con.WM_NULL, 0, 0)
            return True
        except Exception:
            return False

    def _fallback_file_menu(self, menu: QMenu, path: Path):
        act_open = menu.addAction(self.tr("open"))
        act_open.triggered.connect(lambda: subprocess.run(["cmd", "/c", "start", "", str(path)], check=False))

        act_reveal = menu.addAction(self.tr("open_folder"))
        act_reveal.triggered.connect(lambda: subprocess.run(["explorer", "/select,", str(path)], check=False))

        act_copy_path = menu.addAction(self.tr("copy_path"))
        act_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(str(path)))

    def _show_table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        item = self._item_from_row(row)
        if item is None:
            return
        self.table.setCurrentCell(row, 1)

        file_path = item.jpg_path
        global_pos = self.table.viewport().mapToGlobal(pos)
        menu = QMenu(self)
        if sys.platform == "win32":
            act_shell = menu.addAction(self.tr("system_context_menu"))
            act_shell.triggered.connect(lambda: self._show_explorer_context_menu([file_path], global_pos))
            menu.addSeparator()

        verbs = self._get_shell_verbs(file_path) if sys.platform == "win32" else []
        if verbs:
            max_actions = 10
            for i, (name, verb_obj) in enumerate(verbs):
                if i >= max_actions:
                    break
                action = menu.addAction(name)
                action.triggered.connect(lambda _checked=False, v=verb_obj: v.DoIt())
            menu.addSeparator()
            self._fallback_file_menu(menu, file_path)
        else:
            self._fallback_file_menu(menu, file_path)

        menu.exec(global_pos)

    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
            if event.type() == QEvent.Type.ContextMenu:
                self._show_table_context_menu(event.pos())
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._sync_checks_to_selection()
                return False
            if event.type() == QEvent.Type.DragEnter:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.DragMove:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.Drop:
                urls = event.mimeData().urls()
                paths = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
                if paths:
                    self._start_drop_worker(paths)
                    event.acceptProposedAction()
                    return True
        return super().eventFilter(obj, event)

    def _refresh_table(self):
        self.table.setSortingEnabled(False)
        rows = sorted(self.items.values(), key=lambda x: str(x.jpg_path))
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            cb = CheckBox(self.table)
            cb.setChecked(item.needs_process)
            cb.setProperty("item_id", item.item_id)
            cb_wrap = QWidget(self.table)
            cb_layout = QHBoxLayout(cb_wrap)
            cb_layout.setContentsMargins(10, 0, 16, 0)
            cb_layout.setSpacing(0)
            cb_layout.addWidget(cb, 0, Qt.AlignmentFlag.AlignCenter)
            cb_layout.addStretch(1)

            self.table.setCellWidget(row, 0, cb_wrap)
            self.table.setItem(row, 1, QTableWidgetItem(str(item.rel_path)))
            self.table.setItem(row, 2, QTableWidgetItem(item.size_str))
            self.table.setItem(row, 3, QTableWidgetItem(self.tr("yes") if item.is_meizu else self.tr("no")))
            self.table.setItem(row, 4, QTableWidgetItem(self.tr("yes") if item.is_live else self.tr("no")))
            self.table.setItem(row, 5, QTableWidgetItem(self._display_status(item.status)))
        self.table.setSortingEnabled(True)

    def _current_existing_paths(self) -> set[Path]:
        existed: set[Path] = set()
        for item in self.items.values():
            try:
                existed.add(item.jpg_path.resolve())
            except Exception:
                existed.add(item.jpg_path)
        return existed

    def _start_drop_worker(self, paths: list[Path]):
        if self._drop_thread is not None and self._drop_thread.isRunning():
            self._notify(self.tr("busy_title"), self.tr("busy_content"), is_error=True)
            return

        self._set_status_text("parsing_drop")
        self.progress.setRange(0, 0)

        self._drop_thread = QThread(self)
        self._drop_worker = DropScanWorker(paths, self._current_existing_paths())
        self._drop_worker.moveToThread(self._drop_thread)
        self._drop_thread.started.connect(self._drop_worker.run)
        self._drop_worker.batch_ready.connect(self._on_drop_batch_ready)
        self._drop_worker.progress.connect(self._on_drop_progress)
        self._drop_worker.finished.connect(self._on_drop_finished)
        self._drop_worker.finished.connect(self._drop_thread.quit)
        self._drop_worker.finished.connect(self._drop_worker.deleteLater)
        self._drop_thread.finished.connect(self._drop_thread.deleteLater)
        self._drop_thread.start()

    def _on_drop_batch_ready(self, batch):
        for item in batch:
            item.needs_process = True
        for item in batch:
            self.items[item.item_id] = item
        self._refresh_table()
        QApplication.processEvents()

    def _on_drop_progress(self, done: int, total: int, _stage: str):
        self._set_status_text("adding_files", done=done, total=total)

    def _on_drop_finished(self, added: int, total: int):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        if total == 0:
            self._set_status_text("no_new_jpg")
            self._notify(self.tr("no_new_title"), self.tr("no_new_content"), is_error=True)
        else:
            self._set_status_text("drop_done_status", added=added, total=total, count=len(self.items))
            self._notify(self.tr("drop_done_title"), self.tr("added_count", added=added, total=total))
        self._drop_worker = None
        self._drop_thread = None

    def clear_list(self):
        self.items.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self._set_status_text("list_cleared")
        self._notify(self.tr("list_cleared"), self.tr("list_cleared_content"))

    def select_all_rows(self):
        for row in range(self.table.rowCount()):
            cb = self._cell_checkbox(row)
            if isinstance(cb, CheckBox):
                cb.setChecked(True)

    def invert_rows(self):
        for row in range(self.table.rowCount()):
            cb = self._cell_checkbox(row)
            if isinstance(cb, CheckBox):
                cb.setChecked(not cb.isChecked())

    def export_checked(self, action: str):
        selected = self._selected_items()
        if not selected:
            QMessageBox.warning(self, self.tr("hint"), self.tr("select_export_first"))
            return

        target = QFileDialog.getExistingDirectory(self, self.tr("dialog_choose_export"))
        if not target:
            return

        def progress_cb(i, n, item):
            self.progress.setValue(int(i * 100 / n))
            key = "copying" if action == "copy" else "moving"
            self._set_status_text(key, i=i, n=n, name=item.rel_path.name)
            QApplication.processEvents()

        s, f = export_items(selected, Path(target), action, progress_cb)
        self.progress.setValue(100)
        self._set_status_text("export_done_status", success=s, failed=f)
        self._notify(self.tr("export_done_title"), self.tr("success_failed", success=s, failed=f))
        self._refresh_table()

    def fix_checked(self):
        dst = self.output_edit.text().strip()
        if not dst:
            QMessageBox.warning(self, self.tr("hint"), self.tr("choose_output_first"))
            return

        selected = [x for x in self._selected_items() if x.needs_process]
        if not selected:
            QMessageBox.warning(self, self.tr("hint"), self.tr("no_fix_items"))
            return

        exist_action = "skip" if self.skip_radio.isChecked() else "overwrite"

        def progress_cb(i, n, item, st):
            self.progress.setValue(int(i * 100 / n))
            self._set_row_status(item.item_id, st)
            self._set_status_text("fixing", i=i, n=n, name=item.rel_path.name, status=self._display_status(st))
            QApplication.processEvents()

        s, skip, f = fix_items(self.engine, selected, Path(dst), exist_action, progress_cb)
        self.progress.setValue(100)
        self._set_status_text("fix_done_status", success=s, failed=f, skipped=skip)
        self._notify(self.tr("fix_done_title"), self.tr("fix_done_content", success=s, failed=f, skipped=skip))
        self._refresh_table()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    setThemeColor("#1677FF")
    setTheme(Theme.LIGHT)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
