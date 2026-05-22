# meizu_core.py
import os
import sys
import subprocess
from pathlib import Path
import shutil


def _contains_any(data: bytes, patterns: tuple[bytes, ...]) -> bool:
    return any(pattern in data for pattern in patterns)


def _has_google_legacy_motion_photo_tags(data: bytes) -> bool:
    return _contains_any(data, (b'GCamera:MotionPhoto', b'Camera:MotionPhoto')) and _contains_any(
        data, (b'GCamera:MicroVideoOffset', b'Camera:MicroVideoOffset')
    )


def _has_google_container_motion_photo_tags(data: bytes) -> bool:
    return (
        _contains_any(data, (b'GCamera:MotionPhoto', b'Camera:MotionPhoto'))
        and _contains_any(
            data,
            (
                b'GCamera:MotionPhotoPresentationTimestampUs',
                b'Camera:MotionPhotoPresentationTimestampUs',
            ),
        )
        and _contains_any(data, (b'GContainer:Directory', b'Container:Directory'))
        and b'Item:Semantic="MotionPhoto"' in data
        and b'Item:Mime="video/mp4"' in data
    )


def _detect_motion_photo_compatibility(data: bytes) -> str:
    if _has_google_container_motion_photo_tags(data):
        return "native_container"
    if _has_google_legacy_motion_photo_tags(data):
        return "legacy_fixed"
    return "none"


def check_photo_type(file_path: Path) -> tuple[bool, bool, bool, bool]:
    """
    极速预检：通过读取前 128KB 快速查找特征码。
    返回: (is_meizu, is_live, is_fixed, is_native_compatible)
    """
    try:
        with open(file_path, 'rb') as f:
            data = f.read(131072)  # 读取前 128KB

            is_meizu = b'MEIZU' in data.upper()
            has_meizu_live_tag = b'MZCamera:LivePhoto' in data and b'-000000001_-000000001' not in data
            is_live = is_meizu and has_meizu_live_tag

            # 如果是实况图，进一步检测是否已经写入了 Google 的兼容标签
            is_fixed = False
            is_native_compatible = False
            if is_live:
                compatibility = _detect_motion_photo_compatibility(data)
                is_fixed = compatibility != "none"
                is_native_compatible = compatibility == "native_container"

            return is_meizu, is_live, is_fixed, is_native_compatible
    except Exception:
        return False, False, False, False


class LivePhotoFixTool:
    """魅族实况照片修复引擎"""

    def __init__(self):
        self.exiftool_path = self._get_exiftool_path()
        self._check_exiftool()

    def _startupinfo(self):
        if os.name != 'nt':
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo

    def _get_exiftool_path(self) -> str:
        if hasattr(sys, '_MEIPASS'):
            bundle_path = os.path.join(sys._MEIPASS, 'exiftool.exe')
            if os.path.exists(bundle_path):
                return bundle_path
            # Some Windows exiftool builds are a launcher depending on exiftool_files.
            # Keep a fallback search under a bundled exiftool folder.
            bundle_path2 = os.path.join(sys._MEIPASS, 'exiftool', 'exiftool.exe')
            if os.path.exists(bundle_path2):
                return bundle_path2
        # Prefer repository-bundled exiftool first to avoid unexpected system version differences.
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = (
            os.path.join(base_dir, 'vendor', 'exiftool', 'exiftool.exe'),
            os.path.join(base_dir, 'exiftool', 'exiftool.exe'),
            os.path.join(base_dir, 'bin', 'exiftool.exe'),
        )
        for local_path in candidates:
            if os.path.exists(local_path):
                return local_path
        return 'exiftool'

    def _run_exiftool(self, cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            startupinfo=self._startupinfo(),
        )

    def _check_exiftool(self):
        try:
            subprocess.run(
                [self.exiftool_path, '-ver'],
                capture_output=True,
                check=True,
                startupinfo=self._startupinfo(),
            )
        except Exception:
            raise FileNotFoundError("未找到 exiftool！请确保 exiftool.exe 在当前目录或已添加到系统环境变量。")

    def fix_photo(self, input_path: Path, output_path: Path = None) -> tuple[bool, str]:
        try:
            cmd = [
                self.exiftool_path,
                '-P',  # 保留原图时间戳
                '-if',
                '$MIMEType eq "image/jpeg" and $XMP-MZCamera:LivePhoto and $XMP-MZCamera:LivePhoto ne "-000000001_-000000001"',
                '-XMP-GCamera:MotionPhoto=1',
                '-XMP-GCamera:MicroVideo=1',
                '-XMP-GCamera:MicroVideoVersion=1',
                '-XMP-GCamera:MicroVideoOffset<${XMP-MZCamera:LivePhoto;s/.*_//;s/^0+//}',
                '-XMP-GCamera:MotionPhotoPresentationTimestampUs=',
            ]

            is_overwrite = False
            if output_path and str(input_path.resolve()) != str(output_path.resolve()):
                cmd.extend(['-o', str(output_path)])
            else:
                cmd.append('-overwrite_original')
                is_overwrite = True

            cmd.append(str(input_path))

            result = self._run_exiftool(cmd)

            if result.returncode == 0:
                if "failed condition" in result.stdout or "failed condition" in result.stderr:
                    return False, "跳过：不符合魅族实况图特征(可能为普通静态图)"
                return True, "修复成功"
            else:
                error_msg = result.stderr.strip()
                if not error_msg:
                    error_msg = result.stdout.strip()

                if not is_overwrite and "already exists" in error_msg:
                    return False, "目标文件已存在，ExifTool 拒绝覆盖"
                # exiftool on Windows may fail writing with -o in some shell/encoding/path cases.
                # Fallback: copy to destination first, then write in-place on destination.
                if (not is_overwrite) and ("Error Writing output" in error_msg):
                    try:
                        if output_path is None:
                            return False, f"ExifTool 报错: {error_msg}"

                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(input_path, output_path)

                        fallback_cmd = [
                            self.exiftool_path,
                            '-P',
                            '-overwrite_original',
                            '-if',
                            '$MIMEType eq "image/jpeg" and $XMP-MZCamera:LivePhoto and $XMP-MZCamera:LivePhoto ne "-000000001_-000000001"',
                            '-XMP-GCamera:MotionPhoto=1',
                            '-XMP-GCamera:MicroVideo=1',
                            '-XMP-GCamera:MicroVideoVersion=1',
                            '-XMP-GCamera:MicroVideoOffset<${XMP-MZCamera:LivePhoto;s/.*_//;s/^0+//}',
                            '-XMP-GCamera:MotionPhotoPresentationTimestampUs=',
                            str(output_path),
                        ]
                        fallback_result = self._run_exiftool(fallback_cmd)
                        if fallback_result.returncode == 0:
                            return True, "修复成功(写出回退路径)"
                        fallback_err = fallback_result.stderr.strip() or fallback_result.stdout.strip()
                        return False, f"ExifTool 报错: {fallback_err}"
                    except Exception as fallback_e:
                        return False, f"ExifTool 报错: {error_msg}; 回退失败: {fallback_e}"

                return False, f"ExifTool 报错: {error_msg}"
        except Exception as e:
            return False, f"系统错误: {str(e)}"
