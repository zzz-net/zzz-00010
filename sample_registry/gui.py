"""GUI 界面 - Tkinter 实现"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date
from typing import Optional, Dict, Any
import os

from .service import SampleService, STATUS_MAP, STATUS_COLORS
from .io_handler import IOHandler


class SampleRegistryApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("实验样本接收登记系统")
        self.root.geometry("1200x700")
        self.root.minsize(1000, 600)

        self.service = SampleService()
        self.io = IOHandler(self.service)

        self.current_filters: Dict[str, Any] = {}
        self.selected_sample_id: Optional[int] = None

        self._setup_styles()
        self._build_ui()
        self._restore_filter_config()
        self._refresh_samples()

    def _restore_filter_config(self):
        filters = self.service.get_filter_config()
        if filters:
            if filters.get("status"):
                self.status_var.set(STATUS_MAP.get(filters["status"], filters["status"]))
            elif filters.get("status__in") and filters["status__in"] == ["RECEIVED", "PENDING_INFO"]:
                self.status_var.set("待处理")

            if filters.get("project"):
                self.project_var.set(filters["project"])

            if filters.get("batch_no"):
                self.batch_no_var.set(filters["batch_no"])
                self.batch_no_exact_var.set(filters.get("batch_no_exact", False))

            if filters.get("date_from"):
                self.date_from_var.set(filters["date_from"])

            if filters.get("date_to"):
                self.date_to_var.set(filters["date_to"])

            self.current_filters = filters

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Treeview", rowheight=28, font=("Microsoft YaHei", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"))
        style.configure("TLabel", font=("Microsoft YaHei", 10))
        style.configure("TButton", font=("Microsoft YaHei", 10))
        style.configure("TEntry", font=("Microsoft YaHei", 10))
        style.configure("TCombobox", font=("Microsoft YaHei", 10))
        style.configure("Status.TLabel", font=("Microsoft YaHei", 9), foreground="#666")

    def _build_ui(self):
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="操作员:").pack(side=tk.LEFT)
        self.operator_var = tk.StringVar(value=self.service.get_operator())
        operator_entry = ttk.Entry(top_frame, textvariable=self.operator_var, width=15)
        operator_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(top_frame, text="保存操作员", command=self._save_operator).pack(side=tk.LEFT, padx=5)
        ttk.Separator(top_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(top_frame, text="📝 手动录入", command=self._show_register_dialog).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_frame, text="📂 导入 CSV", command=lambda: self._import_file("csv")).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_frame, text="📂 导入 JSON", command=lambda: self._import_file("json")).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_frame, text="💾 导出数据", command=self._show_export_dialog).pack(side=tk.LEFT, padx=3)

        filter_frame = ttk.LabelFrame(self.root, text="筛选条件", padding="10")
        filter_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(filter_frame, text="状态:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.status_var = tk.StringVar(value="")
        status_values = ["", "待处理"] + list(STATUS_MAP.values())
        status_combo = ttk.Combobox(filter_frame, textvariable=self.status_var, values=status_values, width=12, state="readonly")
        status_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(filter_frame, text="项目:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(filter_frame, textvariable=self.project_var, width=20)
        self.project_combo.grid(row=0, column=3, padx=5, pady=5)
        self._refresh_projects()

        ttk.Label(filter_frame, text="批次号:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.batch_no_var = tk.StringVar()
        self.batch_no_combo = ttk.Combobox(filter_frame, textvariable=self.batch_no_var, width=15)
        self.batch_no_combo.grid(row=0, column=5, padx=5, pady=5)

        self.batch_no_exact_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_frame, text="精确匹配", variable=self.batch_no_exact_var).grid(row=0, column=6, padx=5, pady=5)

        ttk.Label(filter_frame, text="日期从:").grid(row=0, column=7, padx=5, pady=5, sticky=tk.W)
        self.date_from_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_from_var, width=12).grid(row=0, column=8, padx=5, pady=5)

        ttk.Label(filter_frame, text="到:").grid(row=0, column=9, padx=5, pady=5, sticky=tk.W)
        self.date_to_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_to_var, width=12).grid(row=0, column=10, padx=5, pady=5)

        ttk.Button(filter_frame, text="🔍 查询", command=self._apply_filters).grid(row=0, column=11, padx=10, pady=5)
        ttk.Button(filter_frame, text="🔄 重置", command=self._reset_filters).grid(row=0, column=12, padx=5, pady=5)

        list_frame = ttk.LabelFrame(self.root, text="样本列表", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("sample_no", "batch_no", "project", "quantity", "receiver", "location", "status", "created_at", "damage_note", "missing_tube_note")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")

        headings = {
            "sample_no": ("样本编号", 120),
            "batch_no": ("批次号", 120),
            "project": ("项目", 150),
            "quantity": ("数量", 70),
            "receiver": ("接收人", 100),
            "location": ("存放位置", 150),
            "status": ("状态", 100),
            "created_at": ("创建时间", 150),
            "damage_note": ("破损备注", 120),
            "missing_tube_note": ("缺管备注", 120),
        }

        for col, (text, width) in headings.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=tk.W)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("RECEIVED", background="#E8F5E9")
        self.tree.tag_configure("PENDING_INFO", background="#FFF3E0")
        self.tree.tag_configure("STORED", background="#E3F2FD")
        self.tree.tag_configure("RETURNED", background="#F3E5F5")
        self.tree.tag_configure("VOIDED", background="#FFEBEE")

        self.tree.bind("<<TreeviewSelect>>", self._on_select_sample)
        self.tree.bind("<Double-1>", self._show_timeline)

        action_frame = ttk.Frame(self.root, padding="10")
        action_frame.pack(fill=tk.X)

        ttk.Label(action_frame, text="选中样本操作:").pack(side=tk.LEFT)
        self.btn_receive = ttk.Button(action_frame, text="← 重新接收", command=lambda: self._transition_status("RECEIVED"), state=tk.DISABLED)
        self.btn_receive.pack(side=tk.LEFT, padx=3)
        self.btn_pending = ttk.Button(action_frame, text="→ 待补资料", command=lambda: self._transition_status("PENDING_INFO"), state=tk.DISABLED)
        self.btn_pending.pack(side=tk.LEFT, padx=3)
        self.btn_store = ttk.Button(action_frame, text="→ 已入库", command=lambda: self._transition_status("STORED"), state=tk.DISABLED)
        self.btn_store.pack(side=tk.LEFT, padx=3)
        self.btn_return = ttk.Button(action_frame, text="→ 已退回", command=lambda: self._transition_status("RETURNED"), state=tk.DISABLED)
        self.btn_return.pack(side=tk.LEFT, padx=3)
        self.btn_void = ttk.Button(action_frame, text="→ 已作废", command=lambda: self._transition_status("VOIDED"), state=tk.DISABLED)
        self.btn_void.pack(side=tk.LEFT, padx=3)

        ttk.Separator(action_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self.btn_notes = ttk.Button(action_frame, text="📝 编辑备注", command=self._show_notes_dialog, state=tk.DISABLED)
        self.btn_notes.pack(side=tk.LEFT, padx=3)
        self.btn_timeline = ttk.Button(action_frame, text="📋 查看时间线", command=self._show_timeline, state=tk.DISABLED)
        self.btn_timeline.pack(side=tk.LEFT, padx=3)

        self.status_var_label = ttk.Label(self.root, text="就绪", style="Status.TLabel", anchor=tk.W, padding="5 2")
        self.status_var_label.pack(fill=tk.X, side=tk.BOTTOM)

        self._update_action_buttons()

    def _refresh_projects(self):
        projects = self.service.get_all_projects()
        self.project_combo["values"] = projects

    def _refresh_batch_nos(self):
        batch_nos = self.service.get_all_batch_nos()
        self.batch_no_combo["values"] = batch_nos

    def _save_operator(self):
        operator = self.operator_var.get().strip()
        if not operator:
            messagebox.showwarning("提示", "操作员不能为空")
            return
        self.service.set_operator(operator)
        self._set_status(f"操作员已保存: {operator}")

    def _set_status(self, message: str):
        self.status_var_label.config(text=message)

    def _apply_filters(self):
        filters = {}

        status_display = self.status_var.get()
        if status_display == "待处理":
            filters["status__in"] = ["RECEIVED", "PENDING_INFO"]
        elif status_display:
            for key, value in STATUS_MAP.items():
                if value == status_display:
                    filters["status"] = key
                    break

        project = self.project_var.get().strip()
        if project:
            filters["project"] = project

        batch_no = self.batch_no_var.get().strip()
        if batch_no:
            filters["batch_no"] = batch_no
            filters["batch_no_exact"] = self.batch_no_exact_var.get()

        date_from = self.date_from_var.get().strip()
        if date_from:
            try:
                datetime.strptime(date_from, "%Y-%m-%d")
                filters["date_from"] = date_from
            except ValueError:
                messagebox.showerror("错误", "日期格式错误，请使用 YYYY-MM-DD")
                return

        date_to = self.date_to_var.get().strip()
        if date_to:
            try:
                datetime.strptime(date_to, "%Y-%m-%d")
                filters["date_to"] = date_to
            except ValueError:
                messagebox.showerror("错误", "日期格式错误，请使用 YYYY-MM-DD")
                return

        self.current_filters = filters
        self.service.save_filter_config(filters)
        self._refresh_samples()

    def _reset_filters(self):
        self.status_var.set("")
        self.project_var.set("")
        self.batch_no_var.set("")
        self.batch_no_exact_var.set(False)
        self.date_from_var.set("")
        self.date_to_var.set("")
        self.current_filters = {}
        self.service.save_filter_config({})
        self._refresh_samples()

    def _refresh_samples(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        samples = self.service.get_samples(self.current_filters)

        for s in samples:
            self.tree.insert(
                "", tk.END,
                iid=str(s["id"]),
                values=(
                    s["sample_no"],
                    s.get("batch_no", "") or "",
                    s["project"],
                    s["quantity"],
                    s["receiver"],
                    s["location"],
                    s["status_display"],
                    s["created_at"],
                    s.get("damage_note", "") or "",
                    s.get("missing_tube_note", "") or "",
                ),
                tags=(s["status"],)
            )

        self._set_status(f"共 {len(samples)} 条记录")
        self._refresh_projects()
        self._refresh_batch_nos()
        self._update_action_buttons()

    def _on_select_sample(self, event):
        selection = self.tree.selection()
        if selection:
            self.selected_sample_id = int(selection[0])
        else:
            self.selected_sample_id = None
        self._update_action_buttons()

    def _update_action_buttons(self):
        has_selection = self.selected_sample_id is not None

        sample = None
        if has_selection:
            sample = self.service.db.get_sample_by_id(self.selected_sample_id)

        for btn in [self.btn_receive, self.btn_pending, self.btn_store, self.btn_return, self.btn_void, self.btn_notes, self.btn_timeline]:
            btn.config(state=tk.NORMAL if has_selection else tk.DISABLED)

        if sample:
            status = sample["status"]
            valid_transitions = {
                "RECEIVED": ["PENDING_INFO", "STORED", "RETURNED", "VOIDED"],
                "PENDING_INFO": ["STORED", "RETURNED", "VOIDED"],
                "STORED": ["VOIDED"],
                "RETURNED": ["RECEIVED", "VOIDED"],
                "VOIDED": []
            }
            valid = valid_transitions.get(status, [])
            self.btn_receive.config(state=tk.NORMAL if "RECEIVED" in valid else tk.DISABLED)
            self.btn_pending.config(state=tk.NORMAL if "PENDING_INFO" in valid else tk.DISABLED)
            self.btn_store.config(state=tk.NORMAL if "STORED" in valid else tk.DISABLED)
            self.btn_return.config(state=tk.NORMAL if "RETURNED" in valid else tk.DISABLED)
            self.btn_void.config(state=tk.NORMAL if "VOIDED" in valid else tk.DISABLED)

    def _show_register_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("手动录入样本")
        dialog.geometry("450x400")
        dialog.transient(self.root)
        dialog.grab_set()

        fields = [
            ("样本编号 *", "sample_no", "如: TEST-001"),
            ("批次号", "batch_no", "如: BATCH-2024-001"),
            ("项目 *", "project", "如: 血液检测"),
            ("数量 *", "quantity", "1-10000"),
            ("接收人 *", "receiver", ""),
            ("存放位置 *", "location", "如: 冰箱A-第3层"),
            ("破损备注", "damage_note", ""),
            ("缺管备注", "missing_tube_note", ""),
        ]

        entries = {}
        for i, (label, key, placeholder) in enumerate(fields):
            ttk.Label(dialog, text=label).grid(row=i, column=0, padx=10, pady=8, sticky=tk.W)
            entry = ttk.Entry(dialog, width=30)
            entry.grid(row=i, column=1, padx=10, pady=8)
            if placeholder:
                entry.insert(0, placeholder)
            entries[key] = entry

        def on_submit():
            data = {}
            for key, entry in entries.items():
                value = entry.get().strip()
                if value:
                    data[key] = value

            operator = self.operator_var.get().strip()
            if not operator:
                messagebox.showwarning("提示", "请先设置操作员", parent=dialog)
                return

            ok, msg, sample_id = self.service.register_sample(data, operator)
            if ok:
                messagebox.showinfo("成功", msg, parent=dialog)
                dialog.destroy()
                self._refresh_samples()
            else:
                messagebox.showerror("失败", msg, parent=dialog)

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="确认登记", command=on_submit).pack(side=tk.LEFT, padx=10)

    def _import_file(self, file_type: str):
        operator = self.operator_var.get().strip()
        if not operator:
            messagebox.showwarning("提示", "请先设置操作员")
            return

        filetypes = []
        if file_type == "csv":
            filetypes = [("CSV 文件", "*.csv"), ("所有文件", "*.*")]
        else:
            filetypes = [("JSON 文件", "*.json"), ("所有文件", "*.*")]

        file_path = filedialog.askopenfilename(title=f"导入 {file_type.upper()} 文件", filetypes=filetypes)
        if not file_path:
            return

        skip = messagebox.askyesnocancel("导入选项", "遇到错误时是否跳过继续？\n是=跳过错误继续\n否=遇到错误即停止\n取消=取消导入")
        if skip is None:
            return

        if file_type == "csv":
            ok, msg, details = self.io.import_from_csv(file_path, operator, skip_errors=skip)
        else:
            ok, msg, details = self.io.import_from_json(file_path, operator, skip_errors=skip)

        if details.get("errors"):
            error_msg = "\n".join(details["errors"][:10])
            if len(details["errors"]) > 10:
                error_msg += f"\n... 还有 {len(details['errors']) - 10} 条错误"
            messagebox.showwarning("导入错误详情", error_msg)

        if ok:
            messagebox.showinfo("导入成功", msg)
            self._refresh_samples()
        else:
            messagebox.showerror("导入失败", msg)

    def _show_export_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("导出数据")
        dialog.geometry("500x350")
        dialog.transient(self.root)
        dialog.grab_set()

        config = self.service.get_export_config()

        ttk.Label(dialog, text="导出目录:").grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)
        dir_var = tk.StringVar(value=config.get("directory", os.path.expanduser("~")))
        dir_entry = ttk.Entry(dialog, textvariable=dir_var, width=40)
        dir_entry.grid(row=0, column=1, padx=10, pady=10)

        def browse_dir():
            path = filedialog.askdirectory(initialdir=dir_var.get(), title="选择导出目录")
            if path:
                dir_var.set(path)

        ttk.Button(dialog, text="浏览...", command=browse_dir).grid(row=0, column=2, padx=5, pady=10)

        ttk.Label(dialog, text="导出格式:").grid(row=1, column=0, padx=10, pady=10, sticky=tk.W)
        format_var = tk.StringVar(value=config.get("format", "csv"))
        ttk.Radiobutton(dialog, text="CSV", variable=format_var, value="csv").grid(row=1, column=1, padx=10, pady=10, sticky=tk.W)
        ttk.Radiobutton(dialog, text="JSON", variable=format_var, value="json").grid(row=1, column=1, padx=10, pady=10)

        ttk.Label(dialog, text="导出条件:").grid(row=2, column=0, padx=10, pady=10, sticky=tk.NW)
        filter_frame = ttk.Frame(dialog)
        filter_frame.grid(row=2, column=1, columnspan=2, padx=10, pady=10, sticky=tk.W)

        use_current_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(filter_frame, text="使用当前筛选条件", variable=use_current_var).pack(anchor=tk.W)

        include_history_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_frame, text="包含状态历史", variable=include_history_var).pack(anchor=tk.W, pady=5)

        filter_info = "无筛选（导出全部）"
        if self.current_filters:
            parts = []
            for k, v in self.current_filters.items():
                if k == "status":
                    parts.append(f"状态: {STATUS_MAP.get(v, v)}")
                elif k == "status__in":
                    parts.append(f"状态: 待处理")
                elif k == "project":
                    parts.append(f"项目: {v}")
                elif k == "batch_no":
                    exact = self.current_filters.get("batch_no_exact", False)
                    match_type = "(精确)" if exact else "(模糊)"
                    parts.append(f"批次号{match_type}: {v}")
                elif k == "date_from":
                    parts.append(f"日期从: {v}")
                elif k == "date_to":
                    parts.append(f"日期到: {v}")
            filter_info = "; ".join(parts)

        ttk.Label(dialog, text=f"当前筛选: {filter_info}", foreground="#666").grid(
            row=3, column=0, columnspan=3, padx=10, pady=5, sticky=tk.W
        )

        def on_export():
            directory = dir_var.get().strip()
            if not directory:
                messagebox.showwarning("提示", "请选择导出目录", parent=dialog)
                return

            ok, msg = self.service.validate_export_path(directory)
            if not ok:
                messagebox.showerror("错误", msg, parent=dialog)
                return

            filters = self.current_filters if use_current_var.get() else None
            export_format = format_var.get()
            include_history = include_history_var.get()

            ok, msg, file_path = self.io.export_samples(directory, export_format, filters, include_history)
            if ok:
                messagebox.showinfo("导出成功", f"{msg}\n文件: {file_path}", parent=dialog)
                dialog.destroy()
            else:
                messagebox.showerror("导出失败", msg, parent=dialog)

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=20)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="开始导出", command=on_export).pack(side=tk.LEFT, padx=10)

    def _transition_status(self, new_status: str):
        if not self.selected_sample_id:
            return

        sample = self.service.db.get_sample_by_id(self.selected_sample_id)
        if not sample:
            return

        remark = tk.simpledialog.askstring(
            "流转备注",
            f"将样本 {sample['sample_no']} 从【{STATUS_MAP[sample['status']]}】"
            f"转为【{STATUS_MAP[new_status]}】\n请输入备注（可选）:",
            parent=self.root
        )
        if remark is None:
            return

        operator = self.operator_var.get().strip()
        if not operator:
            messagebox.showwarning("提示", "请先设置操作员")
            return

        ok, msg = self.service.transition_status(
            self.selected_sample_id, new_status, operator, remark or ""
        )
        if ok:
            self._set_status(msg)
            self._refresh_samples()
        else:
            messagebox.showerror("失败", msg)

    def _show_notes_dialog(self):
        if not self.selected_sample_id:
            return

        sample = self.service.db.get_sample_by_id(self.selected_sample_id)
        if not sample:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"编辑备注 - {sample['sample_no']}")
        dialog.geometry("450x250")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="破损备注:").grid(row=0, column=0, padx=10, pady=10, sticky=tk.NW)
        damage_text = tk.Text(dialog, width=40, height=4)
        damage_text.grid(row=0, column=1, padx=10, pady=10)
        if sample.get("damage_note"):
            damage_text.insert("1.0", sample["damage_note"])

        ttk.Label(dialog, text="缺管备注:").grid(row=1, column=0, padx=10, pady=10, sticky=tk.NW)
        missing_text = tk.Text(dialog, width=40, height=4)
        missing_text.grid(row=1, column=1, padx=10, pady=10)
        if sample.get("missing_tube_note"):
            missing_text.insert("1.0", sample["missing_tube_note"])

        def on_save():
            damage_note = damage_text.get("1.0", tk.END).strip()
            missing_tube_note = missing_text.get("1.0", tk.END).strip()

            ok, msg = self.service.update_notes(
                self.selected_sample_id,
                damage_note if damage_note else None,
                missing_tube_note if missing_tube_note else None
            )
            if ok:
                messagebox.showinfo("成功", msg, parent=dialog)
                dialog.destroy()
                self._refresh_samples()
            else:
                messagebox.showerror("失败", msg, parent=dialog)

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="保存", command=on_save).pack(side=tk.LEFT, padx=10)

    def _show_timeline(self, event=None):
        if not self.selected_sample_id:
            return

        sample, history = self.service.get_sample_timeline(self.selected_sample_id)
        if not sample:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"样本时间线 - {sample['sample_no']}")
        dialog.geometry("600x500")
        dialog.transient(self.root)

        info_frame = ttk.LabelFrame(dialog, text="样本信息", padding="10")
        info_frame.pack(fill=tk.X, padx=10, pady=10)

        info_text = (
            f"样本编号: {sample['sample_no']}\n"
            f"批次号: {sample.get('batch_no', '') or '-'}\n"
            f"项目: {sample['project']}\n"
            f"数量: {sample['quantity']}\n"
            f"接收人: {sample['receiver']}\n"
            f"存放位置: {sample['location']}\n"
            f"当前状态: {sample['status_display']}\n"
        )
        if sample.get("damage_note"):
            info_text += f"破损备注: {sample['damage_note']}\n"
        if sample.get("missing_tube_note"):
            info_text += f"缺管备注: {sample['missing_tube_note']}\n"

        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).pack(anchor=tk.W)

        timeline_frame = ttk.LabelFrame(dialog, text="状态历史", padding="10")
        timeline_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("time", "from", "to", "operator", "remark", "exception")
        tree = ttk.Treeview(timeline_frame, columns=columns, show="headings")
        tree.heading("time", text="时间")
        tree.heading("from", text="原状态")
        tree.heading("to", text="新状态")
        tree.heading("operator", text="操作人")
        tree.heading("remark", text="备注")
        tree.heading("exception", text="异常")

        tree.column("time", width=150)
        tree.column("from", width=80)
        tree.column("to", width=80)
        tree.column("operator", width=80)
        tree.column("remark", width=150)
        tree.column("exception", width=80)

        scrollbar = ttk.Scrollbar(timeline_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for h in history:
            exception_display = "⚠️ " + h["exception_type"] if h.get("exception_type") else ""
            tree.insert(
                "", tk.END,
                values=(
                    h["created_at"],
                    h["from_display"],
                    h["to_display"],
                    h["operator"],
                    h.get("remark", "") or "",
                    exception_display,
                )
            )

        ttk.Button(dialog, text="关闭", command=dialog.destroy).pack(pady=10)


def main():
    root = tk.Tk()
    try:
        import tkinter.simpledialog
        app = SampleRegistryApp(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("启动错误", f"程序启动失败: {str(e)}")
        raise


if __name__ == "__main__":
    main()
