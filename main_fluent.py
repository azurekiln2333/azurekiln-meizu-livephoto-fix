from __future__ import annotations

import sys
import importlib
import subprocess
import os
from collections import deque
from pathlib import Path

from gui_logic import PhotoItem, export_items, fix_items, scan_photo_items, format_size
from meizu_core import LivePhotoFixTool, check_photo_type
from qframelesswindow import FramelessMainWindow, StandardTitleBar

from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
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
    import win32api  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore
    from win32com.shell import shell, shellcon  # type: ignore


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


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


class MainWindow(FramelessMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Meizu LivePhoto Fix")
        self.resize(1280, 860)
        self._title_bar_height = 36
        self._set_blue_title_bar()

        self.items: dict[str, PhotoItem] = {}

        try:
            self.engine = LivePhotoFixTool()
        except FileNotFoundError as e:
            QMessageBox.critical(self, "依赖缺失", str(e))
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

        title = SubtitleLabel("魅族实况照片批量修复", self)
        title_font = QFont("Segoe UI", 15)
        title_font.setBold(True)
        title.setFont(title_font)

        subtitle = BodyLabel("扫描、筛选并批量修复 LivePhoto，支持复制或移动导出", self)
        subtitle.setStyleSheet("color: #667085;")


        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        path_card = CardWidget(self)
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(16, 14, 16, 14)
        path_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.input_edit = LineEdit(self)
        self.input_edit.setReadOnly(True)
        self.input_edit.setPlaceholderText("请选择源目录")
        btn_input = PushButton("选择源目录", self)
        btn_input.clicked.connect(self.choose_input)
        row1.addWidget(BodyLabel("源目录", self))
        row1.addWidget(self.input_edit, 1)
        row1.addWidget(btn_input)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.output_edit = LineEdit(self)
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("请选择输出目录")
        btn_output = PushButton("选择输出目录", self)
        btn_output.clicked.connect(self.choose_output)
        row2.addWidget(BodyLabel("输出目录", self))
        row2.addWidget(self.output_edit, 1)
        row2.addWidget(btn_output)

        path_layout.addLayout(row1)
        path_layout.addLayout(row2)

        option_card = CardWidget(self)
        option_layout = QVBoxLayout(option_card)
        option_layout.setContentsMargins(16, 14, 16, 14)
        option_layout.setSpacing(10)

        row3 = QHBoxLayout()
        row3.setSpacing(12)
        self.subdirs_cb = CheckBox("扫描子目录", self)
        self.subdirs_cb.setChecked(True)
        self.skip_radio = RadioButton("目标已存在时跳过", self)
        self.overwrite_radio = RadioButton("目标已存在时覆盖", self)
        self.skip_radio.setChecked(True)
        row3.addWidget(self.subdirs_cb)
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
        btn_scan = PushButton("扫描", self)
        btn_scan.clicked.connect(self.scan)

        btn_fix = PrimaryPushButton("修复勾选项", self)
        btn_fix.clicked.connect(self.fix_checked)

        btn_copy = PushButton("复制勾选项", self)
        btn_copy.clicked.connect(lambda: self.export_checked("copy"))

        btn_move = PushButton("移动勾选项", self)
        btn_move.clicked.connect(lambda: self.export_checked("move"))

        btn_all = ToolButton(_pick_icon("SELECT_ALL", "CHECKBOX", "ACCEPT"), self)
        btn_all.setToolTip("全选")
        btn_all.clicked.connect(self.select_all_rows)

        btn_invert = ToolButton(_pick_icon("SYNC", "SWITCH", "UPDATE"), self)
        btn_invert.setToolTip("反选")
        btn_invert.clicked.connect(self.invert_rows)

        row4.addStretch(1)
        row4.addWidget(btn_scan)
        row4.addWidget(btn_fix)
        row4.addWidget(btn_copy)
        row4.addWidget(btn_move)
        row4.addSpacing(8)
        row4.addWidget(btn_all)
        row4.addWidget(btn_invert)
        action_layout.addLayout(row4)

        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(8)

        self.drop_hint = BodyLabel("支持拖拽 JPG/JPEG 文件或文件夹到列表区域", self)
        self.drop_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")

        self.table = TableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["勾选", "相对路径", "大小", "魅族", "实况", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setAcceptDrops(True)
        self.table.viewport().setAcceptDrops(True)
        self.table.viewport().installEventFilter(self)

        header = self.table.horizontalHeader()
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
        self.status = BodyLabel("等待选择目录", self)
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
        self._sync_title_bar()

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

    def choose_input(self):
        path = QFileDialog.getExistingDirectory(self, "选择源目录")
        if not path:
            return
        self.input_edit.setText(path)
        self.output_edit.setText(str(Path(path) / "Fixed_MotionPhotos"))
        self.scan()

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_edit.setText(path)

    def _selected_items(self) -> list[PhotoItem]:
        selected: list[PhotoItem] = []
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if isinstance(cb, CheckBox) and cb.isChecked():
                item_id = cb.property("item_id")
                if isinstance(item_id, str) and item_id in self.items:
                    selected.append(self.items[item_id])
        return selected

    def _set_row_status(self, item_id: str, status: str):
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if isinstance(cb, CheckBox) and cb.property("item_id") == item_id:
                self.table.setItem(row, 5, QTableWidgetItem(status))
                return

    def _item_from_row(self, row: int) -> PhotoItem | None:
        if row < 0:
            return None
        cb = self.table.cellWidget(row, 0)
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
        act_open = menu.addAction("打开")
        act_open.triggered.connect(lambda: subprocess.run(["cmd", "/c", "start", "", str(path)], check=False))

        act_reveal = menu.addAction("打开所在目录")
        act_reveal.triggered.connect(lambda: subprocess.run(["explorer", "/select,", str(path)], check=False))

        act_copy_path = menu.addAction("复制路径")
        act_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(str(path)))

    def _show_table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        item = self._item_from_row(row)
        if item is None:
            return

        file_path = item.jpg_path
        global_pos = self.table.viewport().mapToGlobal(pos)
        if self._show_explorer_context_menu([file_path], global_pos):
            return

        menu = QMenu(self)

        verbs = self._get_shell_verbs(file_path) if sys.platform == "win32" else []
        if verbs:
            max_actions = 18
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
                    self._enqueue_dropped_paths(paths)
                    event.acceptProposedAction()
                    return True
        return super().eventFilter(obj, event)

    def _iter_drop_jpg_files(self, paths: list[Path]) -> list[Path]:
        files: list[Path] = []
        for p in paths:
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}:
                files.append(p)
            elif p.is_dir():
                try:
                    for root, _dirs, names in os.walk(p):
                        base = Path(root)
                        for name in names:
                            if name.lower().endswith((".jpg", ".jpeg")):
                                files.append(base / name)
                except Exception:
                    continue
        return sorted(set(files), key=lambda x: str(x))

    def _photo_item_from_path(self, jpg_path: Path, idx: int) -> PhotoItem:
        try:
            size_str = format_size(jpg_path.stat().st_size)
            is_meizu, is_live, is_fixed = check_photo_type(jpg_path)
        except Exception:
            size_str, is_meizu, is_live, is_fixed = "?", False, False, False

        needs_process = is_live and not is_fixed
        if needs_process:
            status = "等待处理"
        elif is_fixed:
            status = "已修复兼容"
        elif not is_meizu:
            status = "非魅族设备照片"
        else:
            status = "魅族普通静态图"

        return PhotoItem(
            item_id=f"drop_{idx}",
            jpg_path=jpg_path,
            rel_path=Path(jpg_path.name),
            size_str=size_str,
            is_meizu=is_meizu,
            is_live=is_live,
            is_fixed=is_fixed,
            needs_process=needs_process,
            status=status,
        )

    def _refresh_table(self):
        rows = sorted(self.items.values(), key=lambda x: str(x.jpg_path))
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            cb = CheckBox(self)
            cb.setChecked(item.needs_process)
            cb.setProperty("item_id", item.item_id)

            self.table.setCellWidget(row, 0, cb)
            self.table.setItem(row, 1, QTableWidgetItem(str(item.rel_path)))
            self.table.setItem(row, 2, QTableWidgetItem(item.size_str))
            self.table.setItem(row, 3, QTableWidgetItem("是" if item.is_meizu else "否"))
            self.table.setItem(row, 4, QTableWidgetItem("是" if item.is_live else "否"))
            self.table.setItem(row, 5, QTableWidgetItem(item.status))

    def _enqueue_dropped_paths(self, paths: list[Path]):
        jpg_files = self._iter_drop_jpg_files(paths)
        if not jpg_files:
            self._notify("无可添加文件", "仅支持拖入 JPG/JPEG 文件或文件夹", is_error=True)
            return

        if not hasattr(self, "_drop_queue"):
            self._drop_queue = deque()
            self._drop_total = 0
            self._drop_added = 0
            self._drop_seen: set[Path] = set()
            self._drop_existing: set[Path] = set()

        existed: set[Path] = set()
        for x in self.items.values():
            try:
                existed.add(x.jpg_path.resolve())
            except Exception:
                existed.add(x.jpg_path)
        self._drop_existing = existed

        enqueued = 0
        for p in jpg_files:
            try:
                rp = p.resolve()
            except Exception:
                rp = p
            if rp in existed or rp in self._drop_seen:
                continue
            self._drop_seen.add(rp)
            self._drop_queue.append((p, rp))
            enqueued += 1

        if enqueued == 0:
            self._notify("未新增", "拖入文件已全部存在于列表中", is_error=True)
            return

        self._drop_total += enqueued
        self.status.setText(f"正在添加文件 0/{self._drop_total}")
        if not hasattr(self, "_drop_timer"):
            self._drop_timer = QTimer(self)
            self._drop_timer.timeout.connect(self._process_drop_batch)
        if not self._drop_timer.isActive():
            self._drop_timer.start(0)

    def _process_drop_batch(self):
        batch_size = 20
        if not hasattr(self, "_drop_queue") or not self._drop_queue:
            if hasattr(self, "_drop_timer") and self._drop_timer.isActive():
                self._drop_timer.stop()
            total = getattr(self, "_drop_total", 0)
            added = getattr(self, "_drop_added", 0)
            if total > 0:
                self.status.setText(f"已新增 {added} 个文件，当前共 {len(self.items)} 项")
                self._notify("拖拽添加完成", f"新增 {added} / {total}")
            self._drop_total = 0
            self._drop_added = 0
            self._drop_seen = set()
            self._drop_existing = set()
            return

        changed = False
        for _ in range(batch_size):
            if not self._drop_queue:
                break
            jpg_path, resolved = self._drop_queue.popleft()
            if resolved in self._drop_existing:
                continue

            idx = len(self.items)
            item = self._photo_item_from_path(jpg_path, idx)
            self.items[item.item_id] = item
            self._drop_added += 1
            self._drop_existing.add(resolved)
            changed = True

        if changed:
            self._refresh_table()
        self.status.setText(f"正在添加文件 {self._drop_added}/{self._drop_total}")

    def scan(self):
        src = self.input_edit.text().strip()
        if not src:
            self.status.setText("请先选择源目录")
            self._notify("缺少源目录", "请先选择源目录再扫描", is_error=True)
            return

        items = scan_photo_items(Path(src), include_subdirs=self.subdirs_cb.isChecked())
        self.items = {x.item_id: x for x in items}
        self._refresh_table()

        self.progress.setValue(0)
        self.status.setText(f"扫描完成: {len(items)} 张")
        self._notify("扫描完成", f"共发现 {len(items)} 张图片")

    def select_all_rows(self):
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if isinstance(cb, CheckBox):
                cb.setChecked(True)

    def invert_rows(self):
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if isinstance(cb, CheckBox):
                cb.setChecked(not cb.isChecked())

    def export_checked(self, action: str):
        selected = self._selected_items()
        if not selected:
            QMessageBox.warning(self, "提示", "请先勾选要导出的照片")
            return

        target = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not target:
            return

        def progress_cb(i, n, item):
            self.progress.setValue(int(i * 100 / n))
            self.status.setText(f"{'复制' if action == 'copy' else '移动'}中 {i}/{n}: {item.rel_path.name}")
            QApplication.processEvents()

        s, f = export_items(selected, Path(target), action, progress_cb)
        self.progress.setValue(100)
        self.status.setText(f"导出完成: 成功 {s} / 失败 {f}")
        self._notify("导出完成", f"成功 {s} / 失败 {f}")
        self.scan()

    def fix_checked(self):
        src = self.input_edit.text().strip()
        dst = self.output_edit.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, "提示", "请先选择源目录和输出目录")
            return

        selected = [x for x in self._selected_items() if x.needs_process]
        if not selected:
            QMessageBox.warning(self, "提示", "勾选项中没有待修复照片")
            return

        exist_action = "skip" if self.skip_radio.isChecked() else "overwrite"

        def progress_cb(i, n, item, st):
            self.progress.setValue(int(i * 100 / n))
            self._set_row_status(item.item_id, st)
            self.status.setText(f"修复中 {i}/{n}: {item.rel_path.name} - {st}")
            QApplication.processEvents()

        s, skip, f = fix_items(self.engine, selected, Path(dst), exist_action, progress_cb)
        self.progress.setValue(100)
        self.status.setText(f"完成: 成功 {s} / 失败 {f} / 冲突跳过 {skip}")
        self._notify("修复完成", f"成功 {s} / 失败 {f} / 冲突跳过 {skip}")
        self.scan()


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
