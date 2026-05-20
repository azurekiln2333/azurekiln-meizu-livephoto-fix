from __future__ import annotations

import sys
import importlib
from pathlib import Path

from gui_logic import PhotoItem, export_items, fix_items, scan_photo_items
from meizu_core import LivePhotoFixTool
from qframelesswindow import FramelessMainWindow, StandardTitleBar

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

QT_BINDING = "PyQt6"


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
        edition = "Pro" if IS_PRO else "Base"
        self.setWindowTitle(f"Meizu LivePhoto Fix - Fluent {edition} ({QT_BINDING})")
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

        version = BodyLabel(
            f"Fluent 版本: {edition}  |  Qt: {QT_BINDING}  |  模式: Light",
            self,
        )
        version.setStyleSheet("color: #98a2b3;")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        header_layout.addWidget(version)

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

        control_card = CardWidget(self)
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(16, 14, 16, 14)
        control_layout.setSpacing(10)

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

        row4.addWidget(btn_scan)
        row4.addWidget(btn_fix)
        row4.addWidget(btn_copy)
        row4.addWidget(btn_move)
        row4.addSpacing(8)
        row4.addWidget(btn_all)
        row4.addWidget(btn_invert)
        row4.addStretch(1)

        control_layout.addLayout(row3)
        control_layout.addLayout(row4)

        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(8)

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

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(56)
        self.table.verticalHeader().setDefaultSectionSize(36)

        table_layout.addWidget(self.table)

        foot_card = CardWidget(self)
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setContentsMargins(16, 12, 16, 12)
        foot_layout.setSpacing(10)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100)
        self.status = BodyLabel("等待选择目录", self)
        self.status.setStyleSheet("color: #475467;")
        foot_layout.addWidget(self.progress, 2)
        foot_layout.addWidget(self.status, 3)

        outer.addWidget(header_card)
        outer.addWidget(path_card)
        outer.addWidget(control_card)
        outer.addWidget(table_card, 1)
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
            btn.setNormalColor("#FFFFFF")
            btn.setHoverColor("#FFFFFF")
            btn.setPressedColor("#FFFFFF")
            btn.setNormalBackgroundColor("#1677FF")
            btn.setHoverBackgroundColor("#3A8DFF")
            btn.setPressedBackgroundColor("#0B62E6")

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

    def scan(self):
        src = self.input_edit.text().strip()
        if not src:
            self.status.setText("请先选择源目录")
            self._notify("缺少源目录", "请先选择源目录再扫描", is_error=True)
            return

        items = scan_photo_items(Path(src), include_subdirs=self.subdirs_cb.isChecked())
        self.items = {x.item_id: x for x in items}

        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            cb = CheckBox(self)
            cb.setChecked(item.needs_process)
            cb.setProperty("item_id", item.item_id)

            self.table.setCellWidget(row, 0, cb)
            self.table.setItem(row, 1, QTableWidgetItem(str(item.rel_path)))
            self.table.setItem(row, 2, QTableWidgetItem(item.size_str))
            self.table.setItem(row, 3, QTableWidgetItem("是" if item.is_meizu else "否"))
            self.table.setItem(row, 4, QTableWidgetItem("是" if item.is_live else "否"))
            self.table.setItem(row, 5, QTableWidgetItem(item.status))

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
