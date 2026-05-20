from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from meizu_core import LivePhotoFixTool, check_photo_type


@dataclass
class PhotoItem:
    item_id: str
    jpg_path: Path
    rel_path: Path
    size_str: str
    is_meizu: bool
    is_live: bool
    is_fixed: bool
    needs_process: bool
    status: str


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _iter_jpg_files(input_dir: Path, include_subdirs: bool):
    patterns = ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG")
    for pattern in patterns:
        if include_subdirs:
            yield from input_dir.rglob(pattern)
        else:
            yield from input_dir.glob(pattern)


def scan_photo_items(input_dir: Path, include_subdirs: bool = True) -> list[PhotoItem]:
    if not input_dir.is_dir():
        return []

    jpg_files = set(_iter_jpg_files(input_dir, include_subdirs))
    items: list[PhotoItem] = []

    for idx, jpg_path in enumerate(sorted(jpg_files, key=lambda p: str(p))):
        try:
            size_str = format_size(jpg_path.stat().st_size)
            is_meizu, is_live, is_fixed = check_photo_type(jpg_path)
        except Exception:
            size_str, is_meizu, is_live, is_fixed = "?", False, False, False

        try:
            rel_path = jpg_path.relative_to(input_dir)
        except ValueError:
            rel_path = Path(jpg_path.name)

        needs_process = is_live and not is_fixed
        if needs_process:
            status = "等待处理"
        elif is_fixed:
            status = "已修复兼容"
        elif not is_meizu:
            status = "非魅族设备照片"
        else:
            status = "魅族普通静态图"

        items.append(
            PhotoItem(
                item_id=f"item_{idx}",
                jpg_path=jpg_path,
                rel_path=rel_path,
                size_str=size_str,
                is_meizu=is_meizu,
                is_live=is_live,
                is_fixed=is_fixed,
                needs_process=needs_process,
                status=status,
            )
        )

    return items


def export_items(
    items: list[PhotoItem],
    target_dir: Path,
    action: str,
    progress_cb: Callable[[int, int, PhotoItem], None] | None = None,
) -> tuple[int, int]:
    target_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    failed = 0
    total = len(items)

    for idx, item in enumerate(items, start=1):
        if progress_cb:
            progress_cb(idx, total, item)

        dst = target_dir / item.rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if action == "copy":
                shutil.copy2(item.jpg_path, dst)
            elif action == "move":
                shutil.move(str(item.jpg_path), str(dst))
            else:
                raise ValueError(f"Unsupported action: {action}")
            success += 1
        except Exception:
            failed += 1

    return success, failed


def fix_items(
    engine: LivePhotoFixTool,
    items: list[PhotoItem],
    output_dir: Path,
    exist_action: str,
    progress_cb: Callable[[int, int, PhotoItem, str], None] | None = None,
) -> tuple[int, int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    skipped_exists_count = 0
    fail_count = 0
    total = len(items)

    for idx, item in enumerate(items, start=1):
        output_file = output_dir / item.rel_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if output_file.exists() and output_file.resolve() != item.jpg_path.resolve():
            if exist_action == "skip":
                skipped_exists_count += 1
                item.status = "跳过(目标已存在)"
                if progress_cb:
                    progress_cb(idx, total, item, item.status)
                continue
            try:
                output_file.unlink(missing_ok=True)
            except Exception:
                pass

        item.status = "正在修复"
        if progress_cb:
            progress_cb(idx, total, item, item.status)

        ok, msg = engine.fix_photo(item.jpg_path, output_file)
        if ok:
            success_count += 1
            item.needs_process = False
            item.is_fixed = True
            item.status = "修复成功"
        else:
            fail_count += 1
            item.status = f"失败: {msg[:40]}"

        if progress_cb:
            progress_cb(idx, total, item, item.status)

    return success_count, skipped_exists_count, fail_count
