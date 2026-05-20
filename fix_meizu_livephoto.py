import subprocess
import os
import sys

class LivePhotoFixTool:
    def __init__(self):
        # 寻找 exiftool 的二进制路径（支持打包后的路径）
        self.exiftool_path = self._get_exiftool_path()

    def _get_exiftool_path(self):
        # 如果是 PyInstaller 打包后的环境，二进制文件在 _MEIPASS 临时目录下
        if hasattr(sys, '_MEIPASS'):
            bundle_path = os.path.join(sys._MEIPASS, 'exiftool.exe')
            if os.path.exists(bundle_path):
                return bundle_path
        # 开发环境下，默认从当前目录或系统变量找
        return 'exiftool'

    def fix_photo(self, input_path, output_dir=None):
        """
        修复照片。如果指定了 output_dir，则另存到该目录。
        """
        try:
            # 基础命令
            cmd = [
                self.exiftool_path,
                '-if',
                '$MIMEType eq "image/jpeg" and $XMP-MZCamera:LivePhoto and $XMP-MZCamera:LivePhoto ne "-000000001_-000000001"',
                '-XMP-GCamera:MotionPhoto=1',
                '-XMP-GCamera:MicroVideo=1',
                '-XMP-GCamera:MicroVideoVersion=1',
                '-XMP-GCamera:MicroVideoOffset<${XMP-MZCamera:LivePhoto;s/.*_//;s/^0+//}',
                '-XMP-GCamera:MotionPhotoPresentationTimestampUs=',
            ]

            # 另存为逻辑
            if output_dir:
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                # 使用 -o 参数指定输出路径。注意：-o 要求目标文件不能已存在
                # exiftool -o 目标目录/文件名 源文件
                output_path = os.path.join(output_dir, os.path.basename(input_path))
                cmd.extend(['-o', output_path])
            else:
                # 没指定输出目录，直接覆盖原图
                cmd.append('-overwrite_original')

            cmd.append(input_path)

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

            if result.returncode == 0:
                return True, "修复成功"
            else:
                if "condition" in result.stderr or "files failed condition" in result.stdout:
                    return True, "跳过：非实况照片"
                return False, result.stderr
        except Exception as e:
            return False, str(e)