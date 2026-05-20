from __future__ import annotations

from pathlib import Path

import flet as ft

from gui_logic import PhotoItem, export_items, fix_items, scan_photo_items
from meizu_core import LivePhotoFixTool


def main(page: ft.Page):
    page.title = "Meizu LivePhoto Fix - Flet"
    page.window_width = 1200
    page.window_height = 760
    page.padding = 12

    try:
        engine = LivePhotoFixTool()
    except FileNotFoundError as e:
        page.add(ft.Text(f"依赖缺失: {e}", color=ft.Colors.RED_600))
        page.update()
        return

    items_map: dict[str, PhotoItem] = {}

    input_dir = ft.TextField(label="源目录", read_only=True, expand=True)
    output_dir = ft.TextField(label="输出目录", read_only=True, expand=True)

    include_subdirs = ft.Switch(label="扫描子目录", value=True)
    exist_action = ft.RadioGroup(
        content=ft.Row(
            [
                ft.Radio(value="skip", label="目标已存在时跳过"),
                ft.Radio(value="overwrite", label="目标已存在时覆盖"),
            ]
        ),
        value="skip",
    )

    status_text = ft.Text("等待选择目录", size=13)
    progress_bar = ft.ProgressBar(value=0)

    data_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("勾选")),
            ft.DataColumn(ft.Text("相对路径")),
            ft.DataColumn(ft.Text("大小")),
            ft.DataColumn(ft.Text("魅族")),
            ft.DataColumn(ft.Text("实况")),
            ft.DataColumn(ft.Text("状态")),
        ],
        rows=[],
        column_spacing=18,
        divider_thickness=0.6,
    )

    def selected_items() -> list[PhotoItem]:
        selected: list[PhotoItem] = []
        for row in data_table.rows:
            cb = row.cells[0].content
            if isinstance(cb, ft.Checkbox) and cb.value:
                item_id = cb.data
                item = items_map.get(item_id)
                if item:
                    selected.append(item)
        return selected

    def refresh_table(items: list[PhotoItem]):
        items_map.clear()
        rows: list[ft.DataRow] = []
        for item in items:
            items_map[item.item_id] = item
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Checkbox(value=item.needs_process, data=item.item_id)),
                        ft.DataCell(ft.Text(str(item.rel_path), no_wrap=False)),
                        ft.DataCell(ft.Text(item.size_str)),
                        ft.DataCell(ft.Text("是" if item.is_meizu else "否")),
                        ft.DataCell(ft.Text("是" if item.is_live else "否")),
                        ft.DataCell(ft.Text(item.status)),
                    ]
                )
            )
        data_table.rows = rows
        page.update()

    def choose_input(_):
        picker.get_directory_path(dialog_title="选择源目录")

    def choose_output(_):
        output_picker.get_directory_path(dialog_title="选择输出目录")

    def on_input_picked(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        input_dir.value = e.path
        out_default = str(Path(e.path) / "Fixed_MotionPhotos")
        output_dir.value = out_default
        scan(None)

    def on_output_picked(e: ft.FilePickerResultEvent):
        if e.path:
            output_dir.value = e.path
            page.update()

    def scan(_):
        if not input_dir.value:
            status_text.value = "请先选择源目录"
            page.update()
            return

        items = scan_photo_items(Path(input_dir.value), include_subdirs=bool(include_subdirs.value))
        refresh_table(items)
        status_text.value = f"扫描完成: {len(items)} 张"
        progress_bar.value = 0
        page.update()

    def run_fix(_):
        src = input_dir.value.strip()
        dst = output_dir.value.strip()
        if not src or not dst:
            status_text.value = "请先选择源目录和输出目录"
            page.update()
            return

        selected = [x for x in selected_items() if x.needs_process]
        if not selected:
            status_text.value = "勾选项中没有待修复照片"
            page.update()
            return

        total = len(selected)

        def progress_cb(i, n, item, st):
            progress_bar.value = i / n if n else 0
            status_text.value = f"修复中 {i}/{n}: {item.rel_path.name} - {st}"
            page.update()

        s, skip, f = fix_items(
            engine=engine,
            items=selected,
            output_dir=Path(dst),
            exist_action=exist_action.value or "skip",
            progress_cb=progress_cb,
        )
        status_text.value = f"完成: 成功 {s} / 失败 {f} / 冲突跳过 {skip}"
        progress_bar.value = 1 if total else 0
        scan(None)

    def do_export(action: str):
        selected = selected_items()
        if not selected:
            status_text.value = "请先勾选要导出的照片"
            page.update()
            return
        target_picker.data = action
        target_picker.get_directory_path(dialog_title=f"选择{ '复制' if action == 'copy' else '移动'}目标目录")

    def on_target_picked(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        action = str(target_picker.data or "copy")
        selected = selected_items()
        if not selected:
            status_text.value = "没有可导出的勾选项"
            page.update()
            return

        def progress_cb(i, n, item):
            progress_bar.value = i / n if n else 0
            status_text.value = f"{'复制' if action == 'copy' else '移动'}中 {i}/{n}: {item.rel_path.name}"
            page.update()

        s, f = export_items(selected, Path(e.path), action, progress_cb)
        status_text.value = f"导出完成: 成功 {s} / 失败 {f}"
        progress_bar.value = 1
        scan(None)

    picker = ft.FilePicker(on_result=on_input_picked)
    output_picker = ft.FilePicker(on_result=on_output_picked)
    target_picker = ft.FilePicker(on_result=on_target_picked)
    page.overlay.extend([picker, output_picker, target_picker])

    page.add(
        ft.Column(
            [
                ft.Row([input_dir, ft.ElevatedButton("选择源目录", on_click=choose_input)]),
                ft.Row([output_dir, ft.ElevatedButton("选择输出目录", on_click=choose_output)]),
                ft.Row([include_subdirs]),
                ft.Row([ft.Text("冲突处理:"), exist_action]),
                ft.Row(
                    [
                        ft.ElevatedButton("扫描", on_click=scan),
                        ft.ElevatedButton("修复勾选项", on_click=run_fix),
                        ft.OutlinedButton("复制勾选项", on_click=lambda _: do_export("copy")),
                        ft.OutlinedButton("移动勾选项", on_click=lambda _: do_export("move")),
                    ]
                ),
                ft.Container(ft.Row([progress_bar, status_text], alignment=ft.MainAxisAlignment.START), padding=6),
                ft.Divider(),
                ft.Container(ft.Column([data_table], scroll=ft.ScrollMode.AUTO), expand=True),
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
