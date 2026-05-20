import tkinter as tk
from tkinter import filedialog, messagebox
import os
from fix_meizu_livephoto import LivePhotoFixTool  # 导入逻辑层


class LivePhotoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("魅族 21 实况照片修复工具")
        self.root.geometry("600x450")

        # 初始化逻辑引擎
        self.engine = LivePhotoFixTool()

        self.setup_ui()

        # ... 前面部分保持不变 ...
    def setup_ui(self):
            # 输出目录选择区域
        out_frame = tk.Frame(self.root)
        out_frame.pack(fill=tk.X, padx=20, pady=5)

        tk.Label(out_frame, text="保存到:").pack(side=tk.LEFT)
        self.output_entry = tk.Entry(out_frame)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        tk.Button(out_frame, text="浏览", command=self.select_output_dir).pack(side=tk.LEFT)

            # 按钮容器
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)

    def select_output_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, path)

    def handle_files(self):
        files = filedialog.askopenfilenames(filetypes=[("JPEG images", "*.jpg;*.jpeg")])
        out_dir = self.output_entry.get().strip() or None

    def log(self, message):
        self.log_box.insert(tk.END, message + "\n")
        self.log_box.see(tk.END)
        self.root.update()

    def handle_files(self):
        files = filedialog.askopenfilenames(filetypes=[("JPEG images", "*.jpg;*.jpeg")])
        if not files:
            return

        count = 0
        for f in files:
            self.log(f"正在处理: {os.path.basename(f)}...")
            success, msg = self.engine.fix_photo(f)
            if success:
                count += 1
            else:
                self.log(f"错误: {msg}")

        messagebox.showinfo("完成", f"成功处理 {count} 张照片！")
        self.log(f"--- 批量处理完成，共 {count} 张 ---")

    def handle_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return

        self.log(f"正在扫描目录: {folder}...")
        success, msg = self.engine.fix_photo(folder)
        if success:
            self.log("目录处理成功完成。")
            messagebox.showinfo("完成", "整个目录处理完毕！")
        else:
            self.log(f"处理出错: {msg}")


if __name__ == "__main__":
    root = tk.Tk()
    app = LivePhotoApp(root)
    root.mainloop()