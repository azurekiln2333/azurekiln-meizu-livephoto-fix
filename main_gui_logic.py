from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from flyme_livephoto_fix_core import LivePhotoFixTool, check_photo_type

ITEM_KIND_PENDING_LIVE = "pending_live"
ITEM_KIND_FIXED_LIVE = "fixed_live"
ITEM_KIND_MEIZU_STATIC = "meizu_static"
ITEM_KIND_OTHER_PHOTO = "other_photo"
ITEM_KIND_OTHER_FILE = "other_file"


@dataclass
class PhotoItem:
    item_id: str
    jpg_path: Path
    source_root: Path | None
    rel_path: Path
    size_str: str
    item_kind: str
    is_meizu: bool
    is_live: bool
    is_fixed: bool
    is_native_compatible: bool
    needs_process: bool
    status: str


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def classify_item(file_path: Path) -> tuple[str, str, bool, bool, bool, bool, bool]:
    try:
        size_str = format_size(file_path.stat().st_size)
    except Exception:
        size_str = "?"

    suffix = file_path.suffix.lower()
    if suffix not in {".jpg", ".jpeg"}:
        return size_str, ITEM_KIND_OTHER_FILE, False, False, False, False, False

    try:
        is_meizu, is_live, is_fixed, is_native_compatible = check_photo_type(file_path)
    except Exception:
        is_meizu, is_live, is_fixed, is_native_compatible = False, False, False, False

    needs_process = is_live and not is_fixed
    if needs_process:
        item_kind = ITEM_KIND_PENDING_LIVE
    elif is_fixed:
        item_kind = ITEM_KIND_FIXED_LIVE
    elif is_meizu:
        item_kind = ITEM_KIND_MEIZU_STATIC
    else:
        item_kind = ITEM_KIND_OTHER_PHOTO
    return size_str, item_kind, is_meizu, is_live, is_fixed, is_native_compatible, needs_process


def default_status_for_item(item_kind: str, is_native_compatible: bool) -> str:
    if item_kind == ITEM_KIND_PENDING_LIVE:
        return "status_pending"
    if item_kind == ITEM_KIND_FIXED_LIVE:
        if is_native_compatible:
            return "status_native_compatible"
        return "status_fixed_compatible"
    if item_kind == ITEM_KIND_MEIZU_STATIC:
        return "status_static"
    if item_kind == ITEM_KIND_OTHER_PHOTO:
        return "status_not_meizu"
    return "status_other_file"


def _iter_files(input_dir: Path, include_subdirs: bool):
    if include_subdirs:
        for path in input_dir.rglob("*"):
            if path.is_file():
                yield path
        return
    for path in input_dir.iterdir():
        if path.is_file():
            yield path


def scan_photo_items(input_dir: Path, include_subdirs: bool = True) -> list[PhotoItem]:
    if not input_dir.is_dir():
        return []

    jpg_files = set(_iter_files(input_dir, include_subdirs))
    items: list[PhotoItem] = []

    for idx, jpg_path in enumerate(sorted(jpg_files, key=lambda p: str(p))):
        size_str, item_kind, is_meizu, is_live, is_fixed, is_native_compatible, needs_process = classify_item(
            jpg_path
        )

        try:
            rel_path = jpg_path.relative_to(input_dir)
        except ValueError:
            rel_path = Path(jpg_path.name)

        items.append(
            PhotoItem(
                item_id=f"item_{idx}",
                jpg_path=jpg_path,
                source_root=input_dir,
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


def output_items(
    engine: LivePhotoFixTool,
    items: list[PhotoItem],
    output_dir: Path,
    exist_action: str,
    progress_cb: Callable[[int, int, PhotoItem, str], None] | None = None,
    should_pause: Callable[[], bool] | None = None,
    should_stop: Callable[[], bool] | None = None,
    idle_cb: Callable[[], None] | None = None,
) -> tuple[int, int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    skipped_exists_count = 0
    fail_count = 0
    total = len(items)

    for idx, item in enumerate(items, start=1):
        while should_pause and should_pause():
            if should_stop and should_stop():
                return success_count, skipped_exists_count, fail_count
            if idle_cb:
                idle_cb()

        if should_stop and should_stop():
            return success_count, skipped_exists_count, fail_count

        output_file = output_dir / item.rel_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            same_file = output_file.exists() and output_file.resolve() == item.jpg_path.resolve()
        except Exception:
            same_file = False

        if item.needs_process:
            if output_file.exists() and not same_file:
                if exist_action == "skip":
                    skipped_exists_count += 1
                    item.status = "status_skip_exists"
                    if progress_cb:
                        progress_cb(idx, total, item, item.status)
                    continue
                try:
                    output_file.unlink(missing_ok=True)
                except Exception:
                    pass

            item.status = "status_fixing"
            if progress_cb:
                progress_cb(idx, total, item, item.status)

            ok, msg = engine.fix_photo(item.jpg_path, output_file)
            if ok:
                success_count += 1
                item.needs_process = False
                item.is_fixed = True
                item.is_native_compatible = False
                item.item_kind = ITEM_KIND_FIXED_LIVE
                item.status = "status_fix_success"
            else:
                fail_count += 1
                item.status = f"失败: {msg[:40]}"
        else:
            if same_file:
                skipped_exists_count += 1
                item.status = "status_skip_exists"
                if progress_cb:
                    progress_cb(idx, total, item, item.status)
                continue
            if output_file.exists():
                if exist_action == "skip":
                    skipped_exists_count += 1
                    item.status = "status_skip_exists"
                    if progress_cb:
                        progress_cb(idx, total, item, item.status)
                    continue
                try:
                    output_file.unlink(missing_ok=True)
                except Exception:
                    pass

            item.status = "status_copying"
            if progress_cb:
                progress_cb(idx, total, item, item.status)
            try:
                shutil.copy2(item.jpg_path, output_file)
                success_count += 1
                item.status = "status_output_copy_success"
            except Exception as e:
                fail_count += 1
                item.status = f"失败: {str(e)[:40]}"

        if progress_cb:
            progress_cb(idx, total, item, item.status)

    return success_count, skipped_exists_count, fail_count


def fix_items(
    engine: LivePhotoFixTool,
    items: list[PhotoItem],
    output_dir: Path,
    exist_action: str,
    progress_cb: Callable[[int, int, PhotoItem, str], None] | None = None,
    should_pause: Callable[[], bool] | None = None,
    should_stop: Callable[[], bool] | None = None,
    idle_cb: Callable[[], None] | None = None,
) -> tuple[int, int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    skipped_exists_count = 0
    fail_count = 0
    total = len(items)

    for idx, item in enumerate(items, start=1):
        while should_pause and should_pause():
            if should_stop and should_stop():
                return success_count, skipped_exists_count, fail_count
            if idle_cb:
                idle_cb()

        if should_stop and should_stop():
            return success_count, skipped_exists_count, fail_count

        output_file = output_dir / item.rel_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if output_file.exists() and output_file.resolve() != item.jpg_path.resolve():
            if exist_action == "skip":
                skipped_exists_count += 1
                item.status = "status_skip_exists"
                if progress_cb:
                    progress_cb(idx, total, item, item.status)
                continue
            try:
                output_file.unlink(missing_ok=True)
            except Exception:
                pass

        item.status = "status_fixing"
        if progress_cb:
            progress_cb(idx, total, item, item.status)

        ok, msg = engine.fix_photo(item.jpg_path, output_file)
        if ok:
            success_count += 1
            item.needs_process = False
            item.is_fixed = True
            item.is_native_compatible = False
            item.status = "status_fix_success"
        else:
            fail_count += 1
            item.status = f"失败: {msg[:40]}"

        if progress_cb:
            progress_cb(idx, total, item, item.status)

    return success_count, skipped_exists_count, fail_count
