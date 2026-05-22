from __future__ import annotations

import json
import sys
import importlib
import subprocess
import os
import ctypes
from pathlib import Path
from uuid import uuid4

from ui_translations import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TRANSLATIONS
from main_gui_logic import (
    ITEM_KIND_FIXED_LIVE,
    ITEM_KIND_MEIZU_STATIC,
    ITEM_KIND_OTHER_FILE,
    ITEM_KIND_OTHER_PHOTO,
    ITEM_KIND_PENDING_LIVE,
    PhotoItem,
    classify_item,
    default_status_for_item,
    export_items,
    output_items,
)
from flyme_livephoto_fix_core import LivePhotoFixTool
from qframelesswindow import FramelessMainWindow, StandardTitleBar

from PyQt6.QtCore import QEvent, QObject, QThread, Qt, pyqtSignal, QRect, QItemSelectionModel, QPoint, QTimer
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QRubberBand,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

QT_BINDING = "PyQt6"
APP_NAME = "FlymeLivePhotoFix"

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


def _get_settings_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


class DropScanWorker(QObject):
    batch_ready = pyqtSignal(object)
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int)

    def __init__(self, paths: list[Path], existing: set[Path], scan_subdirs: bool = True):
        super().__init__()
        self.paths = paths
        self.existing = existing
        self.scan_subdirs = scan_subdirs

    def _iter_files(self) -> list[tuple[Path, Path | None]]:
        files: list[tuple[Path, Path | None]] = []
        for p in self.paths:
            if p.is_file():
                files.append((p, p.parent))
                continue
            if not p.is_dir():
                continue
            try:
                if self.scan_subdirs:
                    for root, _dirs, names in os.walk(p):
                        base = Path(root)
                        for name in names:
                            files.append((base / name, p))
                else:
                    for child in p.iterdir():
                        if child.is_file():
                            files.append((child, p))
            except Exception:
                continue
        dedup: dict[str, tuple[Path, Path | None]] = {}
        for file_path, root in files:
            try:
                key = str(file_path.resolve())
            except Exception:
                key = str(file_path)
            dedup[key] = (file_path, root)
        return [dedup[k] for k in sorted(dedup, key=lambda x: x)]

    def _build_item(self, file_path: Path, source_root: Path | None) -> PhotoItem:
        size_str, item_kind, is_meizu, is_live, is_fixed, is_native_compatible, needs_process = classify_item(
            file_path
        )
        if source_root is not None:
            try:
                rel_path = file_path.relative_to(source_root)
            except ValueError:
                rel_path = Path(file_path.name)
        else:
            rel_path = Path(file_path.name)

        return PhotoItem(
            item_id=f"drop_{uuid4().hex}",
            jpg_path=file_path,
            source_root=source_root,
            rel_path=rel_path,
            size_str=size_str,
            item_kind=item_kind,
            is_meizu=is_meizu,
            is_live=is_live,
            is_fixed=is_fixed,
            is_native_compatible=is_native_compatible,
            needs_process=needs_process,
            status=default_status_for_item(item_kind, is_native_compatible),
        )

    def run(self):
        all_files = self._iter_files()
        candidates: list[tuple[Path, Path | None]] = []
        seen = set()
        for p, root in all_files:
            try:
                rp = p.resolve()
            except Exception:
                rp = p
            if rp in self.existing or rp in seen:
                continue
            seen.add(rp)
            candidates.append((p, root))

        total = len(candidates)
        if total == 0:
            self.finished.emit(0, 0)
            return

        batch: list[PhotoItem] = []
        added = 0
        for idx, (p, root) in enumerate(candidates, start=1):
            batch.append(self._build_item(p, root))
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
        "ComboBox": module.ComboBox,
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
ComboBox = FW["ComboBox"]
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


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


class MainWindow(FramelessMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = DEFAULT_LANGUAGE
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
        self._suspend_settings_save = False
        self._settings_path = _get_settings_path()
        self._rubber_band_origin = None
        self._rubber_band_press_pos = None
        self._rubber_band_last_pos = None
        self._rubber_band_pending = False
        self._rubber_band_active = False
        self._rubber_band_additive = False
        self._rubber_band_base_rows: set[int] = set()
        self._rubber_band_scroll_timer = QTimer(self)
        self._rubber_band_scroll_timer.setInterval(16)
        self._rubber_band_scroll_timer.timeout.connect(self._auto_scroll_rubber_band)
        self._fix_running = False
        self._fix_paused = False
        self._fix_stop_requested = False

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

        header_card = QWidget(self)
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(4, 6, 4, 10)
        header_layout.setSpacing(4)

        self.title_label = SubtitleLabel(self.tr("header_title"), self)
        title_font = QFont("Microsoft YaHei", 15)
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.subtitle_label = BodyLabel(self.tr("header_subtitle"), self)
        self.subtitle_label.setStyleSheet("color: #667085;")
        self.subtitle_note_label = BodyLabel(self.tr("header_note"), self)
        self.subtitle_note_label.setStyleSheet("color: #98A2B3;")

        self.language_label = BodyLabel(self.tr("language"), self)
        self.language_combo = ComboBox(self)
        self.language_combo.addItem("中文", "zh")
        self.language_combo.addItem("English", "en")
        self.language_combo.setFixedWidth(128)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row = QHBoxLayout()
        language_row.addStretch(1)
        language_row.addWidget(self.language_label)
        language_row.addWidget(self.language_combo)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.subtitle_label)
        header_layout.addWidget(self.subtitle_note_label)
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
        self.scan_subdirs_check = CheckBox(self.tr("scan_subdirs"), self)
        self.scan_subdirs_check.setChecked(False)
        row3.addWidget(self.scan_subdirs_check)
        row3.addStretch(1)
        option_layout.addLayout(row3)

        action_card = CardWidget(self)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(8)

        row4 = QHBoxLayout()
        row4.setSpacing(8)
        self.btn_fix = PrimaryPushButton(self.tr("fix_checked"), self)
        self.btn_fix.clicked.connect(self.fix_checked)

        self.btn_pause = PushButton(self.tr("pause_fix"), self)
        self.btn_pause.setIcon(_pick_icon("PAUSE", "PAUSE_BOLD"))
        self.btn_pause.clicked.connect(self.toggle_fix_pause)
        self.btn_pause.setEnabled(False)

        self.btn_stop = PushButton(self.tr("stop_fix"), self)
        self.btn_stop.setIcon(_pick_icon("CLOSE", "CANCEL", "REMOVE"))
        self.btn_stop.clicked.connect(self.stop_fix)
        self.btn_stop.setEnabled(False)

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

        row4.addWidget(self.btn_copy)
        row4.addWidget(self.btn_move)
        row4.addStretch(1)
        row4.addWidget(self.btn_pause)
        row4.addWidget(self.btn_stop)
        row4.addWidget(self.btn_fix)
        action_layout.addLayout(row4)

        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(8)

        hint_row = QHBoxLayout()
        hint_row.setSpacing(8)
        self.drop_hint = BodyLabel(self.tr("drop_hint"), self)
        self.drop_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")
        hint_row.addWidget(self.drop_hint)
        hint_row.addStretch(1)
        hint_row.addWidget(self.btn_all)
        hint_row.addWidget(self.btn_invert)
        hint_row.addWidget(self.btn_clear)

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
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.table.viewport())
        self._rubber_band.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._rubber_band.setStyleSheet(
            "background-color: rgba(0, 120, 215, 40); border: 1px solid rgba(0, 120, 215, 180);"
        )
        self._rubber_band.hide()

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

        table_layout.addLayout(hint_row)
        table_layout.addWidget(self.table)

        output_card = CardWidget(self)
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(16, 14, 16, 14)
        output_layout.setSpacing(8)
        self.output_settings_label = BodyLabel(self.tr("output_settings"), self)
        self.output_settings_label.setStyleSheet("font-weight: 600;")
        output_layout.addWidget(self.output_settings_label)

        exist_row = QHBoxLayout()
        exist_row.setSpacing(12)
        self.skip_radio = RadioButton(self.tr("skip_existing"), self)
        self.overwrite_radio = RadioButton(self.tr("overwrite_existing"), self)
        self.skip_radio.setChecked(True)
        exist_row.addWidget(self.skip_radio)
        exist_row.addWidget(self.overwrite_radio)
        exist_row.addStretch(1)
        output_layout.addLayout(exist_row)

        output_flags_row = QHBoxLayout()
        output_flags_row.setSpacing(12)
        self.output_fixed_live_check = CheckBox(self.tr("include_fixed_live"), self)
        self.output_static_check = CheckBox(self.tr("include_static"), self)
        self.output_other_photo_check = CheckBox(self.tr("include_other_photo"), self)
        self.output_other_file_check = CheckBox(self.tr("include_other_file"), self)
        self.output_fixed_live_check.setChecked(True)
        self.output_static_check.setChecked(True)
        self.output_other_photo_check.setChecked(True)
        self.output_other_file_check.setChecked(True)
        output_flags_row.addWidget(self.output_fixed_live_check)
        output_flags_row.addWidget(self.output_static_check)
        output_flags_row.addWidget(self.output_other_photo_check)
        output_flags_row.addWidget(self.output_other_file_check)
        output_flags_row.addStretch(1)
        output_layout.addLayout(output_flags_row)
        self.output_settings_note = BodyLabel(self.tr("output_note"), self)
        self.output_settings_note.setStyleSheet("color: #6b7280;")
        output_layout.addWidget(self.output_settings_note)

        foot_card = CardWidget(self)
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setContentsMargins(16, 12, 16, 12)
        foot_layout.setSpacing(10)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(10)
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
        outer.addWidget(output_card)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)
        self._init_default_output_dir()
        self._load_settings()
        self._apply_language()
        self._connect_settings_signals()
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
            translated = self.tr(key)
            if translated != key or key.startswith("status_"):
                return translated
        failed_prefix = "失败:"
        if status.startswith(failed_prefix):
            return f"{self.tr('status_failed_prefix')} {status[len(failed_prefix):].strip()}"
        failed_prefix_en = "Failed:"
        if status.startswith(failed_prefix_en):
            return f"{self.tr('status_failed_prefix')} {status[len(failed_prefix_en):].strip()}"
        return status

    def _is_output_enabled_for_item(self, item: PhotoItem) -> bool:
        if item.needs_process:
            return True
        if item.item_kind == ITEM_KIND_FIXED_LIVE:
            return self.output_fixed_live_check.isChecked()
        if item.item_kind == ITEM_KIND_MEIZU_STATIC:
            return self.output_static_check.isChecked()
        if item.item_kind == ITEM_KIND_OTHER_PHOTO:
            return self.output_other_photo_check.isChecked()
        if item.item_kind == ITEM_KIND_OTHER_FILE:
            return self.output_other_file_check.isChecked()
        return False

    def _selected_output_items(self) -> list[PhotoItem]:
        return [item for item in self._selected_items() if self._is_output_enabled_for_item(item)]

    def _settings_payload(self) -> dict:
        return {
            "language": self.lang,
            "output_dir": self.output_edit.text().strip(),
            "scan_subdirs": self.scan_subdirs_check.isChecked(),
            "exist_action": "skip" if self.skip_radio.isChecked() else "overwrite",
            "include_fixed_live": self.output_fixed_live_check.isChecked(),
            "include_static": self.output_static_check.isChecked(),
            "include_other_photo": self.output_other_photo_check.isChecked(),
            "include_other_file": self.output_other_file_check.isChecked(),
        }

    def _save_settings(self):
        if self._suspend_settings_save:
            return
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings_path.write_text(
                json.dumps(self._settings_payload(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_settings(self):
        if not self._settings_path.exists():
            return
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except Exception:
            return

        self._suspend_settings_save = True
        try:
            lang = data.get("language")
            if lang in SUPPORTED_LANGUAGES:
                self.lang = lang
                for idx in range(self.language_combo.count()):
                    if self.language_combo.itemData(idx) == lang:
                        self.language_combo.setCurrentIndex(idx)
                        break

            output_dir = str(data.get("output_dir", "")).strip()
            if output_dir:
                self.output_edit.setText(output_dir)

            self.scan_subdirs_check.setChecked(bool(data.get("scan_subdirs", self.scan_subdirs_check.isChecked())))
            exist_action = data.get("exist_action", "skip")
            self.skip_radio.setChecked(exist_action != "overwrite")
            self.overwrite_radio.setChecked(exist_action == "overwrite")
            self.output_fixed_live_check.setChecked(bool(data.get("include_fixed_live", True)))
            self.output_static_check.setChecked(bool(data.get("include_static", True)))
            self.output_other_photo_check.setChecked(bool(data.get("include_other_photo", True)))
            self.output_other_file_check.setChecked(bool(data.get("include_other_file", True)))
        finally:
            self._suspend_settings_save = False

    def _connect_settings_signals(self):
        for widget in (
            self.scan_subdirs_check,
            self.skip_radio,
            self.overwrite_radio,
            self.output_fixed_live_check,
            self.output_static_check,
            self.output_other_photo_check,
            self.output_other_file_check,
        ):
            widget.toggled.connect(lambda _checked=False: self._save_settings())

    def _on_language_changed(self, _index: int):
        lang = self.language_combo.currentData()
        if lang not in SUPPORTED_LANGUAGES or lang == self.lang:
            return
        self.lang = lang
        self._apply_language()
        self._save_settings()

    def _apply_language(self):
        self.setWindowTitle(self.tr("app_title"))
        self.title_label.setText(self.tr("header_title"))
        self.subtitle_label.setText(self.tr("header_subtitle"))
        self.subtitle_note_label.setText(self.tr("header_note"))
        self.language_label.setText(self.tr("language"))
        self.output_edit.setPlaceholderText(self.tr("output_placeholder"))
        self.btn_output.setText(self.tr("choose_output"))
        self.output_label.setText(self.tr("output_dir"))
        self.output_settings_label.setText(self.tr("output_settings"))
        self.output_fixed_live_check.setText(self.tr("include_fixed_live"))
        self.output_static_check.setText(self.tr("include_static"))
        self.output_other_photo_check.setText(self.tr("include_other_photo"))
        self.output_other_file_check.setText(self.tr("include_other_file"))
        self.output_settings_note.setText(self.tr("output_note"))
        self.scan_subdirs_check.setText(self.tr("scan_subdirs"))
        self.skip_radio.setText(self.tr("skip_existing"))
        self.overwrite_radio.setText(self.tr("overwrite_existing"))
        self.btn_fix.setText(self.tr("fix_checked"))
        self.btn_pause.setText(self.tr("resume_fix") if self._fix_paused else self.tr("pause_fix"))
        self.btn_stop.setText(self.tr("stop_fix"))
        self.btn_copy.setText(self.tr("copy_checked"))
        self.btn_move.setText(self.tr("move_checked"))
        self.btn_all.setToolTip(self.tr("select_all"))
        self.btn_invert.setToolTip(self.tr("invert_selection"))
        self.btn_clear.setText(self.tr("clear_list"))
        self.drop_hint.setText(self.tr("drop_hint"))
        self.table.setHorizontalHeaderLabels(self._table_headers())
        self.btn_pause.setIcon(_pick_icon("PLAY", "PLAY_SOLID") if self._fix_paused else _pick_icon("PAUSE", "PAUSE_BOLD"))
        self.btn_stop.setIcon(_pick_icon("CLOSE", "CANCEL", "REMOVE"))
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
        self.titleBar.setObjectName("blueTitleBar")
        self.titleBar.setStyleSheet(
            """
            QWidget#blueTitleBar {
                background: #1677FF;
            }
            QWidget#blueTitleBar QLabel {
                color: #FFFFFF;
                background: transparent;
            }
            """
        )
        for btn in (self.titleBar.minBtn, self.titleBar.maxBtn):
            btn.setNormalColor("#1F2937")
            btn.setHoverColor("#1F2937")
            btn.setPressedColor("#1F2937")
            btn.setNormalBackgroundColor("#00000000")
            btn.setHoverBackgroundColor("#4DFFFFFF")
            btn.setPressedBackgroundColor("#80FFFFFF")

        self.titleBar.closeBtn.setNormalColor("#1F2937")
        self.titleBar.closeBtn.setHoverColor("#FFFFFF")
        self.titleBar.closeBtn.setPressedColor("#FFFFFF")
        self.titleBar.closeBtn.setNormalBackgroundColor("#00000000")
        self.titleBar.closeBtn.setHoverBackgroundColor("#E81123")
        self.titleBar.closeBtn.setPressedBackgroundColor("#F1707A")

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

    def _viewport_to_content_pos(self, pos: QPoint) -> QPoint:
        return QPoint(pos.x(), pos.y() + self.table.verticalScrollBar().value())

    def _content_to_clamped_viewport_pos(self, pos: QPoint) -> QPoint:
        return self._clamp_rubber_band_pos(QPoint(pos.x(), pos.y() - self.table.verticalScrollBar().value()))

    def _row_rect(self, row: int) -> QRect:
        y = self.table.rowViewportPosition(row) + self.table.verticalScrollBar().value()
        h = self.table.rowHeight(row)
        if y < 0 or h <= 0:
            return QRect()
        return QRect(0, y, self.table.viewport().width(), h)

    def _rows_in_rect(self, rect: QRect) -> list[int]:
        band_rect = rect.normalized()
        if band_rect.isEmpty():
            return []
        rows: list[int] = []
        for row in range(self.table.rowCount()):
            row_rect = self._row_rect(row)
            if row_rect.isValid() and row_rect.intersects(band_rect):
                rows.append(row)
        return rows

    def _apply_row_selection(self, rows: list[int]):
        model = self.table.selectionModel()
        if model is None:
            return
        model.clearSelection()
        if not rows:
            return
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for row in rows:
            idx = self.table.model().index(row, 0)
            if idx.isValid():
                model.select(idx, flags)

    def _clamp_rubber_band_pos(self, pos: QPoint) -> QPoint:
        rect = self.table.viewport().rect()
        x = min(max(pos.x(), rect.left()), rect.right())
        y = min(max(pos.y(), rect.top()), rect.bottom())
        return QPoint(x, y)

    def _start_rubber_band(self, pos, additive: bool):
        self._rubber_band_origin = self._viewport_to_content_pos(pos)
        self._rubber_band_press_pos = pos
        self._rubber_band_last_pos = pos
        self._rubber_band_additive = additive
        self._rubber_band_active = True
        model = self.table.selectionModel()
        self._rubber_band_base_rows = {idx.row() for idx in model.selectedRows()} if additive and model else set()
        self._rubber_band.setGeometry(QRect(self._clamp_rubber_band_pos(pos), self._clamp_rubber_band_pos(pos)))
        self._rubber_band.show()
        self._rubber_band.raise_()
        self._rubber_band_scroll_timer.start()
        if not additive:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)

    def _update_rubber_band(self, pos):
        if not self._rubber_band_active or self._rubber_band_origin is None:
            return
        self._rubber_band_last_pos = pos
        current_content_pos = self._viewport_to_content_pos(pos)
        draw_rect = QRect(
            self._content_to_clamped_viewport_pos(self._rubber_band_origin),
            self._clamp_rubber_band_pos(pos),
        ).normalized()
        self._rubber_band.setGeometry(draw_rect)
        rows = set(self._rows_in_rect(QRect(self._rubber_band_origin, current_content_pos).normalized()))
        if self._rubber_band_additive:
            rows |= self._rubber_band_base_rows
        self._apply_row_selection(sorted(rows))

    def _auto_scroll_rubber_band(self):
        if not self._rubber_band_active or self._rubber_band_last_pos is None:
            return
        rect = self.table.viewport().rect()
        pos = self._rubber_band_last_pos
        dy = 0
        if pos.y() < rect.top():
            distance = rect.top() - pos.y()
            dy = -min(24, max(2, distance // 6 + 2))
        elif pos.y() > rect.bottom():
            distance = pos.y() - rect.bottom()
            dy = min(24, max(2, distance // 6 + 2))
        if dy == 0:
            return
        bar = self.table.verticalScrollBar()
        new_value = min(max(bar.value() + dy, bar.minimum()), bar.maximum())
        if new_value == bar.value():
            return
        bar.setValue(new_value)
        self._update_rubber_band(pos)

    def _finish_rubber_band(self, pos):
        if not self._rubber_band_active or self._rubber_band_origin is None:
            return
        current_content_pos = self._viewport_to_content_pos(pos)
        self._rubber_band.hide()
        self._rubber_band_scroll_timer.stop()
        self._rubber_band_active = False
        rows = set(self._rows_in_rect(QRect(self._rubber_band_origin, current_content_pos).normalized()))
        self._rubber_band_origin = None
        if self._rubber_band_additive:
            rows |= self._rubber_band_base_rows
        self._apply_row_selection(sorted(rows))
        self._rubber_band_base_rows.clear()
        self._rubber_band_press_pos = None
        self._rubber_band_last_pos = None
        self._rubber_band_pending = False
        self._sync_checks_to_selection()

    def _cancel_rubber_band(self):
        self._rubber_band.hide()
        self._rubber_band_scroll_timer.stop()
        self._rubber_band_origin = None
        self._rubber_band_press_pos = None
        self._rubber_band_last_pos = None
        self._rubber_band_pending = False
        self._rubber_band_active = False
        self._rubber_band_base_rows.clear()

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
        base = pics_dir / "FlymeLivePhotoFix_output"
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
            self._save_settings()

    def _auto_set_output_dir_from_drop(self, paths: list[Path]):
        drop_dirs = [p for p in paths if p.is_dir()]
        if not drop_dirs:
            return
        # If multiple folders are dropped, use the first one as the output base.
        target = drop_dirs[0] / "FlymeLivePhotoFix_output"
        try:
            target.mkdir(parents=True, exist_ok=True)
            self.output_edit.setText(str(target))
            self._save_settings()
        except Exception:
            return

    def _selected_items(self) -> list[PhotoItem]:
        selected: list[PhotoItem] = []
        for row in range(self.table.rowCount()):
            cb = self._cell_checkbox(row)
            if isinstance(cb, CheckBox) and cb.isChecked():
                item_id = cb.property("item_id")
                if isinstance(item_id, str) and item_id in self.items:
                    selected.append(self.items[item_id])
        return selected

    def _selected_row_numbers(self) -> list[int]:
        model = self.table.selectionModel()
        if model is None:
            return []
        return sorted({idx.row() for idx in model.selectedRows()})

    def _context_file_paths(self, row: int) -> list[Path]:
        item = self._item_from_row(row)
        if item is None:
            return []
        selected_rows = self._selected_row_numbers()
        if row in selected_rows:
            paths = [self._item_from_row(selected_row) for selected_row in selected_rows]
            return [path_item.jpg_path for path_item in paths if path_item is not None]
        self.table.clearSelection()
        idx = self.table.model().index(row, 0)
        if idx.isValid():
            flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
            self.table.selectionModel().select(idx, flags)
        self.table.setCurrentCell(row, 1)
        return [item.jpg_path]

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
            owner_hwnd = int(self.window().winId())
            folder = shell.SHGetDesktopFolder()
            abs_paths = [str(p.resolve()) for p in file_paths]
            parent_dirs = {str(Path(p).parent) for p in abs_paths}
            if len(parent_dirs) != 1:
                return False
            parent_dir = str(Path(abs_paths[0]).parent)

            parent_pidl = shell.SHParseDisplayName(parent_dir, 0)[0]
            parent_folder = folder.BindToObject(parent_pidl, None, shell.IID_IShellFolder)

            child_pidls = []
            for p in abs_paths:
                rel_name = Path(p).name
                child_pidl = parent_folder.ParseDisplayName(0, None, rel_name)[1]
                child_pidls.append(child_pidl)

            _inout, cm = parent_folder.GetUIObjectOf(
                owner_hwnd,
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

                win32gui.SetForegroundWindow(owner_hwnd)
                cmd = win32gui.TrackPopupMenu(
                    hmenu,
                    win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON,
                    global_pos.x(),
                    global_pos.y(),
                    0,
                    owner_hwnd,
                    None,
                )
            finally:
                win32gui.DestroyMenu(hmenu)

            if cmd:
                ci = (0, owner_hwnd, cmd - id_cmd_first, None, parent_dir, 0, 0, 0)
                cm.InvokeCommand(ci)
            else:
                win32gui.PostMessage(owner_hwnd, win32con.WM_NULL, 0, 0)
            return True
        except Exception:
            return False

    def _show_explorer_context_menu_deferred(self, file_paths: list[Path]) -> None:
        paths = list(file_paths)
        QTimer.singleShot(0, lambda: self._show_explorer_context_menu(paths, QCursor.pos()))

    def _set_file_clipboard(self, paths: list[Path], cut: bool = False) -> bool:
        if not paths:
            return False
        if sys.platform != "win32":
            QApplication.clipboard().setText("\n".join(str(p) for p in paths))
            return True

        class _Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class _DropFiles(ctypes.Structure):
            _fields_ = [
                ("pFiles", ctypes.c_uint32),
                ("pt", _Point),
                ("fNC", ctypes.c_int),
                ("fWide", ctypes.c_int),
            ]

        def _alloc_block(raw: bytes):
            kernel32 = ctypes.windll.kernel32
            kernel32.GlobalAlloc.restype = ctypes.c_void_p
            kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
            handle = kernel32.GlobalAlloc(0x0042, len(raw))
            if not handle:
                raise MemoryError("GlobalAlloc failed")
            locked = kernel32.GlobalLock(handle)
            if not locked:
                kernel32.GlobalFree(handle)
                raise MemoryError("GlobalLock failed")
            try:
                ctypes.memmove(locked, raw, len(raw))
            finally:
                kernel32.GlobalUnlock(handle)
            return handle

        try:
            abs_paths = [str(p.resolve()) for p in paths]
        except Exception:
            abs_paths = [str(p) for p in paths]
        file_list = ("\0".join(abs_paths) + "\0\0").encode("utf-16le")
        header = _DropFiles(pFiles=ctypes.sizeof(_DropFiles), pt=_Point(0, 0), fNC=0, fWide=1)
        payload = ctypes.string_at(ctypes.byref(header), ctypes.sizeof(header)) + file_list
        effect = (2 if cut else 1).to_bytes(4, "little")
        text = ("\r\n".join(abs_paths) + "\0").encode("utf-16le")

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        cf_hdrop = 15
        cf_unicode_text = 13
        preferred_effect = user32.RegisterClipboardFormatW("Preferred DropEffect")
        drop_handle = _alloc_block(payload)
        effect_handle = _alloc_block(effect)
        text_handle = _alloc_block(text)
        try:
            if not user32.OpenClipboard(int(self.winId())):
                return False
            try:
                user32.EmptyClipboard()
                if not user32.SetClipboardData(cf_hdrop, drop_handle):
                    return False
                drop_handle = None
                if preferred_effect and user32.SetClipboardData(preferred_effect, effect_handle):
                    effect_handle = None
                if user32.SetClipboardData(cf_unicode_text, text_handle):
                    text_handle = None
                return True
            finally:
                user32.CloseClipboard()
        finally:
            if drop_handle:
                kernel32.GlobalFree(drop_handle)
            if effect_handle:
                kernel32.GlobalFree(effect_handle)
            if text_handle:
                kernel32.GlobalFree(text_handle)

    def _copy_paths_text(self, paths: list[Path]):
        QApplication.clipboard().setText("\n".join(str(p) for p in paths))

    def _append_file_clipboard_actions(self, menu: QMenu, paths: list[Path]):
        if not paths:
            return
        act_copy_files = menu.addAction(self.tr("copy_files"))
        act_copy_files.triggered.connect(lambda: self._set_file_clipboard(paths, cut=False))

        act_cut_files = menu.addAction(self.tr("cut_files"))
        act_cut_files.triggered.connect(lambda: self._set_file_clipboard(paths, cut=True))

    def _fallback_file_menu(self, menu: QMenu, paths: list[Path]):
        if not paths:
            return
        first_path = paths[0]
        if len(paths) == 1:
            act_open = menu.addAction(self.tr("open"))
            act_open.triggered.connect(lambda: subprocess.run(["cmd", "/c", "start", "", str(first_path)], check=False))

        act_reveal = menu.addAction(self.tr("open_folder"))
        act_reveal.triggered.connect(lambda: subprocess.run(["explorer", "/select,", str(first_path)], check=False))

        act_copy_path = menu.addAction(self.tr("copy_path"))
        act_copy_path.triggered.connect(lambda: self._copy_paths_text(paths))

    def _show_table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        file_paths = self._context_file_paths(row)
        if not file_paths:
            return
        global_pos = self.table.viewport().mapToGlobal(pos)
        menu = QMenu(self)
        same_parent = len({str(path.parent) for path in file_paths}) == 1

        self._append_file_clipboard_actions(menu, file_paths)
        menu.addSeparator()

        if sys.platform == "win32":
            act_shell = menu.addAction(self.tr("system_context_menu"))
            act_shell.setEnabled(same_parent)
            act_shell.triggered.connect(lambda: self._show_explorer_context_menu_deferred(file_paths))
            menu.addSeparator()

        verbs = self._get_shell_verbs(file_paths[0]) if sys.platform == "win32" and len(file_paths) == 1 else []
        if verbs:
            max_actions = 10
            for i, (name, verb_obj) in enumerate(verbs):
                if i >= max_actions:
                    break
                action = menu.addAction(name)
                action.triggered.connect(lambda _checked=False, v=verb_obj: v.DoIt())
            menu.addSeparator()
            self._fallback_file_menu(menu, file_paths)
        else:
            self._fallback_file_menu(menu, file_paths)

        menu.exec(global_pos)

    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
            if event.type() == QEvent.Type.ContextMenu:
                self._show_table_context_menu(event.pos())
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._rubber_band_press_pos = event.pos()
                self._rubber_band_pending = True
                self._rubber_band_active = False
                return False
            if event.type() == QEvent.Type.MouseMove and self._rubber_band_active:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self._update_rubber_band(event.pos())
                    return True
            if event.type() == QEvent.Type.MouseMove and self._rubber_band_pending and self._rubber_band_press_pos is not None:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    if (event.pos() - self._rubber_band_press_pos).manhattanLength() >= QApplication.startDragDistance():
                        additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                        self._start_rubber_band(self._rubber_band_press_pos, additive)
                        self._update_rubber_band(event.pos())
                        return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                if self._rubber_band_active:
                    self._finish_rubber_band(event.pos())
                    return True
                self._cancel_rubber_band()
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
                    self._auto_set_output_dir_from_drop(paths)
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
            cb.setChecked(True)
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
            meizu_text = "" if item.item_kind == ITEM_KIND_OTHER_FILE else (self.tr("yes") if item.is_meizu else self.tr("no"))
            live_text = "" if item.item_kind == ITEM_KIND_OTHER_FILE else (self.tr("yes") if item.is_live else self.tr("no"))
            self.table.setItem(row, 3, QTableWidgetItem(meizu_text))
            self.table.setItem(row, 4, QTableWidgetItem(live_text))
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
        self._drop_worker = DropScanWorker(paths, self._current_existing_paths(), self.scan_subdirs_check.isChecked())
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

    def _set_fix_running_state(self, running: bool):
        self._fix_running = running
        self.btn_fix.setEnabled(not running)
        self.btn_pause.setEnabled(running)
        self.btn_stop.setEnabled(running)
        self.btn_copy.setEnabled(not running)
        self.btn_move.setEnabled(not running)
        self.btn_output.setEnabled(not running)
        self.output_fixed_live_check.setEnabled(not running)
        self.output_static_check.setEnabled(not running)
        self.output_other_photo_check.setEnabled(not running)
        self.output_other_file_check.setEnabled(not running)
        self.scan_subdirs_check.setEnabled(not running)
        self.skip_radio.setEnabled(not running)
        self.overwrite_radio.setEnabled(not running)
        self.btn_all.setEnabled(not running)
        self.btn_invert.setEnabled(not running)
        self.btn_clear.setEnabled(not running)
        if running:
            self.btn_pause.setText(self.tr("pause_fix"))
            self.btn_pause.setIcon(_pick_icon("PAUSE", "PAUSE_BOLD"))
        else:
            self._fix_paused = False
            self._fix_stop_requested = False
            self.btn_pause.setText(self.tr("pause_fix"))
            self.btn_pause.setIcon(_pick_icon("PAUSE", "PAUSE_BOLD"))

    def toggle_fix_pause(self):
        if not self._fix_running:
            return
        self._fix_paused = not self._fix_paused
        self.btn_pause.setText(self.tr("resume_fix") if self._fix_paused else self.tr("pause_fix"))
        self.btn_pause.setIcon(_pick_icon("PLAY", "PLAY_SOLID") if self._fix_paused else _pick_icon("PAUSE", "PAUSE_BOLD"))
        if self._fix_paused:
            self._set_status_text("fix_paused_status")

    def stop_fix(self):
        if not self._fix_running:
            return
        self._fix_stop_requested = True
        self._fix_paused = False
        self.btn_pause.setText(self.tr("pause_fix"))
        self._set_status_text("fix_stopping_status")
        QApplication.processEvents()

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
            self._set_status_text(key, i=i, n=n, name=str(item.rel_path))
            QApplication.processEvents()

        s, f = export_items(selected, Path(target), action, progress_cb)
        self.progress.setValue(100)
        self._set_status_text("export_done_status", success=s, failed=f)
        self._notify(self.tr("export_done_title"), self.tr("success_failed", success=s, failed=f))
        self._refresh_table()

    def fix_checked(self):
        if self._fix_running:
            return

        dst = self.output_edit.text().strip()
        if not dst:
            QMessageBox.warning(self, self.tr("hint"), self.tr("choose_output_first"))
            return

        selected = self._selected_output_items()
        if not selected:
            QMessageBox.warning(self, self.tr("hint"), self.tr("no_output_items"))
            return

        exist_action = "skip" if self.skip_radio.isChecked() else "overwrite"

        def progress_cb(i, n, item, st):
            self.progress.setValue(int(i * 100 / n))
            self._set_row_status(item.item_id, st)
            self._set_status_text("fixing", i=i, n=n, name=str(item.rel_path), status=self._display_status(st))
            QApplication.processEvents()

        def should_pause():
            return self._fix_paused

        def should_stop():
            return self._fix_stop_requested

        def idle_cb():
            QApplication.processEvents()

        self._fix_paused = False
        self._fix_stop_requested = False
        self._set_fix_running_state(True)

        try:
            s, skip, f = output_items(
                self.engine,
                selected,
                Path(dst),
                exist_action,
                progress_cb,
                should_pause,
                should_stop,
                idle_cb,
            )
            stopped = self._fix_stop_requested
        finally:
            self._set_fix_running_state(False)

        if stopped:
            self._set_status_text("fix_stopped_status", success=s, failed=f, skipped=skip)
            self._notify(self.tr("fix_stopped_title"), self.tr("fix_stopped_content", success=s, failed=f, skipped=skip), is_error=True)
        else:
            self.progress.setValue(100)
            self._set_status_text("fix_done_status", success=s, failed=f, skipped=skip)
            self._notify(self.tr("fix_done_title"), self.tr("fix_done_content", success=s, failed=f, skipped=skip))
        self._refresh_table()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    setThemeColor("#1677FF")
    setTheme(Theme.LIGHT)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
