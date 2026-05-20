# main_gui.py
import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# 导入抽离出去的核心逻辑引擎
from meizu_core import LivePhotoFixTool, check_photo_type


class MeizuLivePhotoGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("魅族实况照片批量修复与管理工具 (带分组/复选)")
        self.root.geometry("1050x750")
        self.root.minsize(900, 550)

        try:
            self.engine = LivePhotoFixTool()
        except FileNotFoundError as e:
            messagebox.showerror("依赖缺失", str(e))
            self.root.destroy()
            return

        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        self.include_subdirs = tk.BooleanVar(value=True)
        self.exist_action = tk.StringVar(value="skip")

        self.file_data_map = {}  # 存储 item_id -> file_data 的映射
        self.is_processing = False

        self.create_widgets()

    def update_ui_status(self, item_id, status_text, progress_percent, lbl_text=None):
        """更新处理过程中的界面状态"""
        # 1. 更新表格中该行的“当前状态”
        if self.tree.exists(item_id):
            self.tree.set(item_id, column="Status", value=status_text)

        # 2. 更新进度条
        self.progress_var.set(progress_percent)

        # 3. 更新左下角的文字提示 (如果有传的话)
        if lbl_text is not None:
            self.lbl_status.config(text=lbl_text)
            
    def create_widgets(self):
        # --- 顶部文件夹选择区 ---
        frame_top = tk.Frame(self.root, padx=10, pady=5)
        frame_top.pack(fill=tk.X)

        tk.Label(frame_top, text="源文件夹 (包含原片 JPG):").grid(row=0, column=0, sticky=tk.W, pady=5)
        tk.Entry(frame_top, textvariable=self.input_dir, width=70, state='readonly').grid(row=0, column=1, padx=5,
                                                                                          pady=5)
        tk.Button(frame_top, text="浏览...", command=self.browse_input).grid(row=0, column=2, padx=5, pady=5)

        tk.Label(frame_top, text="修复输出目录 (保存修复后):").grid(row=1, column=0, sticky=tk.W, pady=5)
        tk.Entry(frame_top, textvariable=self.output_dir, width=70, state='readonly').grid(row=1, column=1, padx=5,
                                                                                           pady=5)
        tk.Button(frame_top, text="浏览...", command=self.browse_output).grid(row=1, column=2, padx=5, pady=5)

        # --- 设置选项区 ---
        frame_settings = tk.LabelFrame(self.root, text="修复规则设置", padx=10, pady=5)
        frame_settings.pack(fill=tk.X, padx=10, pady=5)

        row1 = tk.Frame(frame_settings)
        row1.pack(fill=tk.X, pady=2)
        tk.Checkbutton(row1, text="扫描所有子文件夹 (输出时保持目录结构)",
                       variable=self.include_subdirs, command=self.scan_files).pack(side=tk.LEFT)

        ttk.Separator(row1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=15)

        tk.Label(row1, text="修复目标文件已存在时:").pack(side=tk.LEFT, padx=(0, 5))
        tk.Radiobutton(row1, text="跳过 (忽略)", variable=self.exist_action, value="skip").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(row1, text="覆盖 (替换)", variable=self.exist_action, value="overwrite").pack(side=tk.LEFT,
                                                                                                     padx=5)

        # --- 中间表格展示区 (带分组和复选框) ---
        frame_mid = tk.Frame(self.root, padx=10)
        frame_mid.pack(fill=tk.BOTH, expand=True, pady=5)

        scroll_y = ttk.Scrollbar(frame_mid)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # 注意：这里将相对路径放在了树形结构的主列 (#0) 中
        columns = ("FileSize", "IsMeizu", "IsLive", "Status")
        self.tree = ttk.Treeview(frame_mid, columns=columns, show="tree headings", yscrollcommand=scroll_y.set)

        self.tree.heading("#0", text="☑ 文件分类与路径")
        self.tree.heading("FileSize", text="文件大小")
        self.tree.heading("IsMeizu", text="魅族拍摄")
        self.tree.heading("IsLive", text="含实况数据")
        self.tree.heading("Status", text="当前状态")

        self.tree.column("#0", width=420, anchor=tk.W)
        self.tree.column("FileSize", width=90, anchor=tk.E)
        self.tree.column("IsMeizu", width=80, anchor=tk.CENTER)
        self.tree.column("IsLive", width=90, anchor=tk.CENTER)
        self.tree.column("Status", width=260, anchor=tk.W)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.config(command=self.tree.yview)

        # 绑定点击事件，处理复选框逻辑
        self.tree.bind('<ButtonRelease-1>', self.on_tree_click)

        # --- 底部控制与进度区 ---
        frame_bottom = tk.Frame(self.root, padx=10, pady=10)
        frame_bottom.pack(fill=tk.X)

        # 左侧：进度条与状态提示
        frame_progress = tk.Frame(frame_bottom)
        frame_progress.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(frame_progress, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 15))
        self.lbl_status = tk.Label(frame_progress, text="等待导入文件夹...", width=45, anchor=tk.W)
        self.lbl_status.pack(side=tk.LEFT)

        # 右侧/下方：动作按钮
        frame_actions = tk.Frame(frame_bottom)
        frame_actions.pack(side=tk.BOTTOM, fill=tk.X)

        # 文件整理按钮区
        tk.Label(frame_actions, text="对【勾选】的文件执行:").pack(side=tk.LEFT)
        self.btn_copy = tk.Button(frame_actions, text="📁 复制到...", command=lambda: self.export_selected("copy"))
        self.btn_copy.pack(side=tk.LEFT, padx=5)
        self.btn_move = tk.Button(frame_actions, text="✂️ 移动到...", command=lambda: self.export_selected("move"))
        self.btn_move.pack(side=tk.LEFT, padx=5)

        # 修复按钮
        self.btn_start = tk.Button(frame_actions, text="开始修复【勾选】的待处理项", bg="#4CAF50", fg="black",
                                   font=("Arial", 11, "bold"), command=self.start_processing)
        self.btn_start.pack(side=tk.RIGHT, padx=5)

    # ================= 树形复选框逻辑 =================
    def on_tree_click(self, event):
        """处理点击复选框的事件"""
        if self.is_processing: return

        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item_id: return

        # 只响应点击树的主列(#0)
        if column == '#0':
            # 获取点击的 X 坐标相对项的位置，大概限制在复选框区域
            item_x, _, item_w, _ = self.tree.bbox(item_id, column)
            if event.x - item_x < 30:  # 假设复选框在最前面30像素内
                self.toggle_checkbox(item_id)

    def toggle_checkbox(self, item_id):
        """切换选中状态并级联"""
        text = self.tree.item(item_id, "text")
        is_checked = text.startswith("☑")

        new_mark = "☐" if is_checked else "☑"
        new_text = new_mark + text[1:]
        self.tree.item(item_id, text=new_text)

        # 如果是父节点，级联修改所有子节点
        children = self.tree.get_children(item_id)
        for child in children:
            child_text = self.tree.item(child, "text")
            # 只有标记不同的才修改，优化性能
            if not child_text.startswith(new_mark):
                self.tree.item(child, text=new_mark + child_text[1:])

        # 如果是子节点，更新父节点状态
        parent = self.tree.parent(item_id)
        if parent:
            self.update_parent_checkbox(parent)

    def update_parent_checkbox(self, parent_id):
        """根据子节点状态更新父节点"""
        children = self.tree.get_children(parent_id)
        if not children: return

        checked_count = sum(1 for c in children if self.tree.item(c, "text").startswith("☑"))
        parent_text = self.tree.item(parent_id, "text")

        # 如果全选了则父节点也是 ☑，否则父节点变为 ☐ (暂时不做半选☒效果以保简洁)
        new_mark = "☑" if checked_count == len(children) else "☐"
        if not parent_text.startswith(new_mark):
            self.tree.item(parent_id, text=new_mark + parent_text[1:])

    def get_checked_items(self):
        """获取所有打勾的子项 ID 列表"""
        checked_items = []
        # 遍历四个根节点
        for group in ["g_pending", "g_fixed", "g_static", "g_other"]:
            if self.tree.exists(group):
                for child in self.tree.get_children(group):
                    if self.tree.item(child, "text").startswith("☑"):
                        checked_items.append(child)
        return checked_items

    # ================= 扫描与分组逻辑 =================
    def browse_input(self):
        folder = filedialog.askdirectory(title="选择包含待修复照片的文件夹")
        if folder:
            self.input_dir.set(folder)
            self.scan_files()
            default_out = Path(folder) / "Fixed_MotionPhotos"
            self.output_dir.set(str(default_out))

    def browse_output(self):
        folder = filedialog.askdirectory(title="选择修复后输出文件夹")
        if folder:
            self.output_dir.set(folder)

    def format_size(self, size: int) -> str:
        return f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"

    def scan_files(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.file_data_map.clear()

        in_path_str = self.input_dir.get()
        if not in_path_str: return
        in_path = Path(in_path_str)
        if not in_path.is_dir(): return

        jpg_files_set = set()
        if self.include_subdirs.get():
            jpg_files_set.update(in_path.rglob("*.jpg"))
            jpg_files_set.update(in_path.rglob("*.jpeg"))
            jpg_files_set.update(in_path.rglob("*.JPG"))
            jpg_files_set.update(in_path.rglob("*.JPEG"))
        else:
            jpg_files_set.update(in_path.glob("*.jpg"))
            jpg_files_set.update(in_path.glob("*.jpeg"))
            jpg_files_set.update(in_path.glob("*.JPG"))
            jpg_files_set.update(in_path.glob("*.JPEG"))

        if not jpg_files_set:
            messagebox.showinfo("提示", "所选文件夹中未找到 JPG/JPEG 图片。")
            return

        # 创建四大分组根节点 (默认全部打勾)
        self.tree.insert("", tk.END, iid="g_pending", text="☑ 📂 等待修复的实况图", open=True)
        self.tree.insert("", tk.END, iid="g_fixed", text="☑ ✅ 已修复兼容的实况图", open=True)
        self.tree.insert("", tk.END, iid="g_static", text="☐ 📸 魅族普通静态图", open=False)  # 默认不勾选不展开
        self.tree.insert("", tk.END, iid="g_other", text="☐ ❌ 非魅族设备照片", open=False)  # 默认不勾选不展开

        scanned_data = []
        for jpg_path in jpg_files_set:
            try:
                size_str = self.format_size(jpg_path.stat().st_size)
                is_meizu, is_live, is_fixed = check_photo_type(jpg_path)
            except Exception:
                size_str, is_meizu, is_live, is_fixed = "?", False, False, False

            try:
                rel_path = jpg_path.relative_to(in_path)
            except ValueError:
                rel_path = jpg_path.name

            scanned_data.append({
                "jpg_path": jpg_path,
                "rel_path": rel_path,
                "size_str": size_str,
                "is_meizu": is_meizu,
                "is_live": is_live,
                "is_fixed": is_fixed,
                "needs_process": is_live and not is_fixed
            })

        # 对数据进行按名字排序
        scanned_data.sort(key=lambda x: str(x['rel_path']))

        # 将数据分别插入对应的分组
        for idx, data in enumerate(scanned_data):
            item_id = f"item_{idx}"

            is_meizu_str = "📸 是" if data["is_meizu"] else "❌ 否"
            is_live_str = "✅ 是" if data["is_live"] else "❌ 否"

            if data["needs_process"]:
                parent = "g_pending"
                status = "等待处理"
                mark = "☑ "
            elif data["is_fixed"]:
                parent = "g_fixed"
                status = "✅ 已修复兼容"
                mark = "☑ "
            elif not data["is_meizu"]:
                parent = "g_other"
                status = "非魅族设备照片"
                mark = "☐ "
            else:
                parent = "g_static"
                status = "魅族普通静态图"
                mark = "☐ "

            self.tree.insert(parent, tk.END, iid=item_id, text=f"{mark}{data['rel_path']}",
                             values=(data["size_str"], is_meizu_str, is_live_str, status))
            self.file_data_map[item_id] = data

        # 清理没有子节点的分组
        for group in ["g_pending", "g_fixed", "g_static", "g_other"]:
            if not self.tree.get_children(group):
                self.tree.delete(group)

        self.lbl_status.config(text=f"共扫描 {len(scanned_data)} 张图片。可点击列表框的 ☑ 进行勾选管理。")

    # ================= 导出/整理逻辑 (复制或移动) =================
    def export_selected(self, action="copy"):
        if self.is_processing: return

        checked_ids = self.get_checked_items()
        if not checked_ids:
            messagebox.showwarning("提示", "请先在上面的列表中勾选你需要操作的照片！")
            return

        target_dir = filedialog.askdirectory(title=f"选择要{'复制' if action == 'copy' else '移动'}到的目标文件夹")
        if not target_dir: return

        target_path = Path(target_dir)

        msg = f"确定要将勾选的 {len(checked_ids)} 张照片 {'复制' if action == 'copy' else '移动(剪切)'} 到以下目录吗？\n\n{target_path}"
        if not messagebox.askyesno("确认操作", msg): return

        self.is_processing = True
        self.lock_ui(True)
        threading.Thread(target=self.export_thread, args=(checked_ids, target_path, action), daemon=True).start()

    def export_thread(self, checked_ids, target_path, action):
        total = len(checked_ids)
        success = 0
        failed = 0

        for i, item_id in enumerate(checked_ids):
            data = self.file_data_map[item_id]
            src_file = data["jpg_path"]
            rel_path = data["rel_path"]

            progress_percent = ((i + 1) / total) * 100

            dest_file = target_path / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            self.root.after(0, self.lbl_status.config,
                            {"text": f"正在{'复制' if action == 'copy' else '移动'}: {rel_path.name}"})
            self.root.after(0, self.progress_var.set, progress_percent)

            try:
                if action == "copy":
                    shutil.copy2(src_file, dest_file)
                else:  # move
                    shutil.move(str(src_file), str(dest_file))
                success += 1
            except Exception as e:
                failed += 1
                print(f"Failed to {action} {src_file}: {e}")

        def finish():
            self.lock_ui(False)
            self.is_processing = False
            self.progress_var.set(100)
            self.lbl_status.config(text=f"{'复制' if action == 'copy' else '移动'}完成！成功: {success}，失败: {failed}")

            messagebox.showinfo("操作完成", f"成功{'复制' if action == 'copy' else '移动'}了 {success} 个文件。")
            # 如果是移动，原文件已经没了，需要强制刷新列表
            if action == "move" and success > 0:
                self.scan_files()

        self.root.after(0, finish)

    # ================= 修复逻辑 =================
    def start_processing(self):
        if self.is_processing: return

        # 获取所有勾选的子项
        checked_ids = self.get_checked_items()

        # 过滤出真正需要处理的 (即 data["needs_process"] 为 True 的)
        process_tasks = [item_id for item_id in checked_ids if self.file_data_map[item_id]["needs_process"]]

        if not process_tasks:
            messagebox.showwarning("提示", "你勾选的文件中，没有属于【等待修复】状态的照片！")
            return

        in_dir, out_dir = self.input_dir.get(), self.output_dir.get()
        if not in_dir or not out_dir:
            messagebox.showwarning("警告", "请先选择源文件夹和输出文件夹！")
            return

        if Path(in_dir).resolve() == Path(out_dir).resolve():
            msg = "原文件夹和输出文件夹相同，工具将直接【原地修改源文件】！\n建议先备份数据。\n\n是否确认直接修改？"
            if not messagebox.askyesno("风险提示", msg): return

        self.is_processing = True
        self.lock_ui(True)
        threading.Thread(target=self.process_files_thread, args=(process_tasks, out_dir), daemon=True).start()

    def process_files_thread(self, process_tasks, out_dir):
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        total = len(process_tasks)
        success_count = exist_skip_count = fail_count = 0

        for i, item_id in enumerate(process_tasks):
            data = self.file_data_map[item_id]
            jpg_path, rel_path = data["jpg_path"], data["rel_path"]

            progress_percent = ((i + 1) / total) * 100

            output_file = out_path / rel_path
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if output_file.exists() and output_file.resolve() != jpg_path.resolve():
                if self.exist_action.get() == "skip":
                    exist_skip_count += 1
                    self.root.after(0, self.update_ui_status, item_id, "⏭️ 跳过 (目标已存在)", progress_percent,
                                    f"进度: {i + 1}/{total}")
                    continue
                else:
                    try:
                        os.remove(output_file)
                    except OSError:
                        pass

            self.root.after(0, self.update_ui_status, item_id, "⏳ 正在修复...", progress_percent,
                            f"处理中: {rel_path.name}")

            success, msg = self.engine.fix_photo(jpg_path, output_file)

            if success:
                success_count += 1
                self.root.after(0, self.update_ui_status, item_id, "✅ 修复成功", progress_percent)
                # 修复成功后，更新本地缓存状态，防止重复处理
                self.file_data_map[item_id]["needs_process"] = False
                self.file_data_map[item_id]["is_fixed"] = True
            else:
                fail_count += 1
                self.root.after(0, self.update_ui_status, item_id, f"❌ 失败: {msg[:30]}", progress_percent)

        def finish():
            self.lock_ui(False)
            self.progress_var.set(100)
            self.lbl_status.config(
                text=f"任务完成！成功: {success_count} | 失败: {fail_count} | 冲突跳过: {exist_skip_count}")
            self.is_processing = False
            messagebox.showinfo("处理完成",
                                f"修复任务结束！\n\n✅ 成功修改并兼容: {success_count} 个\n"
                                f"⏭️ 因目标已存在跳过: {exist_skip_count} 个\n"
                                f"❌ 处理失败: {fail_count} 个\n\n照片已输出至:\n{out_path}")
            # 成功后刷新列表，让已修复的归类到正确的组
            if success_count > 0:
                self.scan_files()

        self.root.after(0, finish)

    def lock_ui(self, lock: bool):
        """处理时锁定/解锁相关按钮"""
        state = tk.DISABLED if lock else tk.NORMAL
        self.btn_start.config(state=state)
        self.btn_copy.config(state=state)
        self.btn_move.config(state=state)


if __name__ == '__main__':
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("Treeview", rowheight=25, font=('Arial', 10))
    style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))
    app = MeizuLivePhotoGUI(root)
    root.mainloop()