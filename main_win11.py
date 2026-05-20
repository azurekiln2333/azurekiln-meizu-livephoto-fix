from __future__ import annotations

import sys
from pathlib import Path

from gui_logic import PhotoItem, export_items, fix_items, scan_photo_items
from meizu_core import LivePhotoFixTool

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QCheckBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QProgressBar,
        QRadioButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
        QHeaderView,
        QFrame,
    )
    QT_BINDING = "PySide6"
except ImportError:
    from PyQt6.QtCore import Qt  # type: ignore
    from PyQt6.QtGui import QFont  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QApplication,
        QFileDialog,
        QCheckBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QProgressBar,
        QRadioButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
        QHeaderView,
        QFrame,
    )
    QT_BINDING = "PyQt6"


WIN11_QSS = """
QMainWindow {
    background: #f3f3f3;
}
QFrame#Surface {
    background: #ffffff;
    border: 1px solid #e7e7e7;
    border-radius: 12px;
}
QLabel {
    color: #1f1f1f;
}
QLineEdit {
    background: #fbfbfb;
    border: 1px solid #d7d7d7;
    border-radius: 8px;
    padding: 8px 10px;
    color: #111111;
}
QLineEdit:focus {
    border: 1px solid #0078d4;
    background: #ffffff;
}
QPushButton {
    background: #f9f9f9;
    color: #1f1f1f;
    border: 1px solid #d0d0d0;
    border-radius: 8px;
    padding: 8px 14px;
}
QPushButton:hover {
    background: #f2f2f2;
}
QPushButton:pressed {
    background: #ececec;
}
QPushButton#Primary {
    background: #0078d4;
    color: #ffffff;
    border: 1px solid #0078d4;
}
QPushButton#Primary:hover {
    background: #106ebe;
}
QPushButton#Primary:pressed {
    background: #005a9e;
}
QTableWidget {
    background: #ffffff;
    border: 1px solid #e1e1e1;
    border-radius: 10px;
    gridline-color: #efefef;
    selection-background-color: #eaf3ff;
    selection-color: #1f1f1f;
}
QHeaderView::section {
    background: #f7f7f7;
    border: none;
    border-bottom: 1px solid #e7e7e7;
    padding: 8px;
    color: #1f1f1f;
}
QProgressBar {
    border: 1px solid #dcdcdc;
    border-radius: 8px;
    text-align: center;
    background: #f0f0f0;
    min-height: 18px;
}
QProgressBar::chunk {
    border-radius: 7px;
    background: #0078d4;
}
QCheckBox, QRadioButton {
    spacing: 6px;
    color: #1f1f1f;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Meizu LivePhoto Fix - Win11 Fluent Style ({QT_BINDING})")
        self.resize(1220, 780)

        self.items: dict[str, PhotoItem] = {}

        try:
            self.engine = LivePhotoFixTool()
        except FileNotFoundError as e:
            QMessageBox.critical(self, "依赖缺失", str(e))
            raise

        root = QWidget()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        panel = QFrame()
        panel.setObjectName("Surface")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(10)

        title = QLabel("魅族实况照片批量修复")
        f = QFont("Segoe UI", 13)
        f.setBold(True)
        title.setFont(f)
        panel_layout.addWidget(title)

        row1 = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setReadOnly(True)
        btn_input = QPushButton("选择源目录")
        btn_input.clicked.connect(self.choose_input)
        row1.addWidget(QLabel("源目录"))
        row1.addWidget(self.input_edit, 1)
        row1.addWidget(btn_input)

        row2 = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        btn_output = QPushButton("选择输出目录")
        btn_output.clicked.connect(self.choose_output)
        row2.addWidget(QLabel("输出目录"))
        row2.addWidget(self.output_edit, 1)
        row2.addWidget(btn_output)

        row3 = QHBoxLayout()
        self.subdirs_cb = QCheckBox("扫描子目录")
        self.subdirs_cb.setChecked(True)
        self.skip_radio = QRadioButton("目标已存在时跳过")
        self.overwrite_radio = QRadioButton("目标已存在时覆盖")
        self.skip_radio.setChecked(True)
        row3.addWidget(self.subdirs_cb)
        row3.addStretch(1)
        row3.addWidget(self.skip_radio)
        row3.addWidget(self.overwrite_radio)

        row4 = QHBoxLayout()
        btn_scan = QPushButton("扫描")
        btn_scan.clicked.connect(self.scan)

        btn_fix = QPushButton("修复勾选项")
        btn_fix.setObjectName("Primary")
        btn_fix.clicked.connect(self.fix_checked)

        btn_copy = QPushButton("复制勾选项")
        btn_copy.clicked.connect(lambda: self.export_checked("copy"))

        btn_move = QPushButton("移动勾选项")
        btn_move.clicked.connect(lambda: self.export_checked("move"))

        row4.addWidget(btn_scan)
        row4.addWidget(btn_fix)
        row4.addWidget(btn_copy)
        row4.addWidget(btn_move)
        row4.addStretch(1)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["勾选", "相对路径", "大小", "魅族", "实况", "状态"])
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        row5 = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("等待选择目录")
        row5.addWidget(self.progress, 2)
        row5.addWidget(self.status, 3)

        panel_layout.addLayout(row1)
        panel_layout.addLayout(row2)
        panel_layout.addLayout(row3)
        panel_layout.addLayout(row4)
        panel_layout.addWidget(self.table, 1)
        panel_layout.addLayout(row5)

        outer.addWidget(panel, 1)

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
        result: list[PhotoItem] = []
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if isinstance(cb, QCheckBox) and cb.isChecked():
                item_id = cb.property("item_id")
                if isinstance(item_id, str) and item_id in self.items:
                    result.append(self.items[item_id])
        return result

    def _set_row_status(self, item_id: str, status: str):
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if isinstance(cb, QCheckBox) and cb.property("item_id") == item_id:
                self.table.setItem(row, 5, QTableWidgetItem(status))
                return

    def scan(self):
        src = self.input_edit.text().strip()
        if not src:
            self.status.setText("请先选择源目录")
            return

        items = scan_photo_items(Path(src), include_subdirs=self.subdirs_cb.isChecked())
        self.items = {x.item_id: x for x in items}

        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            cb = QCheckBox()
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
        self.scan()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(WIN11_QSS)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
