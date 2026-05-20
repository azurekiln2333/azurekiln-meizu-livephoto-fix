# meizu_core.py
import os
import sys
import subprocess
from pathlib import Path


def check_photo_type(file_path: Path) -> tuple[bool, bool, bool]:
    """
    极速预检：通过读取前 128KB 快速查找特征码。
    返回: (is_meizu, is_live, is_fixed)
    """
    try:
        with open(file_path, 'rb') as f:
            data = f.read(131072)  # 读取前 128KB

            is_meizu = b'MEIZU' in data.upper()
            is_live = b'MZCamera:LivePhoto' in data and b'-000000001_-000000001' not in data

            # 如果是实况图，进一步检测是否已经写入了 Google 的兼容标签
            is_fixed = False
            if is_live:
                is_fixed = b'GCamera:MotionPhoto' in data and b'GCamera:MicroVideoOffset' in data

            return is_meizu, is_live, is_fixed
    except Exception:
        return False, False, False


class LivePhotoFixTool:
    """魅族实况照片修复引擎"""

    def __init__(self):
        self.exiftool_path = self._get_exiftool_path()
        self._check_exiftool()

    def _get_exiftool_path(self) -> str:
        if hasattr(sys, '_MEIPASS'):
            bundle_path = os.path.join(sys._MEIPASS, 'exiftool.exe')
            if os.path.exists(bundle_path):
                return bundle_path
        return 'exiftool'

    def _check_exiftool(self):
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            subprocess.run([self.exiftool_path, '-ver'], capture_output=True, check=True, startupinfo=startupinfo)
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

            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', startupinfo=startupinfo)

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
                return False, f"ExifTool 报错: {error_msg[:30]}..."
        except Exception as e:
            return False, f"系统错误: {str(e)}"