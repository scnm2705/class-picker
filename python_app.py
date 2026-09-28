"""班级随机点名器 Python TEST — offline Tkinter desktop app."""
from __future__ import annotations

import os
import sys
import tempfile
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from openpyxl import Workbook, load_workbook

import python_core as core
import python_maintenance as maintenance
import python_storage as storage
import python_board as board_rules
from python_board_server import BoardServer
from python_board_window import BoardWindow


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent / "班级随机点名器_V1.0"


def student_label(student: dict | None) -> str:
    if not student:
        return "已移出人员"
    return student.get("Name", "?") + (f"（{student['Number']}）" if student.get("Number") else "")


def batch_name(classroom: dict, entry: dict) -> str:
    return student_label(core.student_by_id(classroom, entry["StudentId"]))


def batch_detail_text(classroom: dict, batch: dict) -> str:
    moment = core.parse_date(batch.get("Time")) or core.now()
    lines = [f"{moment:%Y-%m-%d %H:%M:%S}  {batch.get('Mode')}第{batch.get('Round')}轮"]
    if batch.get("Cycle", 0):
        lines[0] += f"（重置后周期 {batch['Cycle']}）"
    lines.append(f"计划 {batch['Count']} 人；VIP配额 {batch.get('PlannedVip', 0)}；普通补齐 {'开' if batch.get('FillVipShortage') else '关'}")
    if batch.get("ClosedWithMissing"):
        lines.append("本批已明确结束，未补位置仍为空缺。")
    for entry in batch["Entries"]:
        lines.append(f"{entry['Position']}. {batch_name(classroom, entry)}{'（VIP）' if entry.get('Vip') else ''} · "
                     f"{entry.get('Source', '')} · {'有效' if entry.get('Valid') else '缺席无效'}")
    for event in batch.get("BoardEvents", []):
        lines.append(f"{event['Position']}. 宝箱：{event['Title']} · {'已处理' if event.get('Handled') else '待处理'}")
    if batch.get("BoardRolls"):
        lines.append("骰子点数：" + "、".join(str(r["steps"]) for r in batch["BoardRolls"]))
    return "\n".join(lines)


class PickerApp(tk.Tk):
    def __init__(self, data_directory=None, board_first=False):
        super().__init__()
        self.title("班级随机点名器 · 3D 棋盘 V1.0")
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1380, max(640, screen_width - 60))}x{min(860, max(480, screen_height - 110))}")
        self.minsize(min(980, max(640, screen_width - 60)), min(560, max(480, screen_height - 110)))
        self.configure(bg="#f2f6fb")
        self.option_add("*Font", ("Microsoft YaHei UI", 11))
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#f2f6fb")
        self.style.configure("TLabel", background="#f2f6fb", foreground="#19324b")
        self.style.configure("TButton", padding=(10, 7), font=("Microsoft YaHei UI", 10))
        self.style.configure("Accent.TButton", background="#2867b9", foreground="white")
        self.style.map("Accent.TButton", background=[("active", "#1a569d")])
        self.style.configure("Treeview", rowheight=30, font=("Microsoft YaHei UI", 10))
        self.style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        self.style.configure("TCombobox", padding=5)
        try:
            directory = Path(data_directory) if data_directory is not None else storage.configured_directory(app_directory())
            fresh = not any((directory / n).exists() for n in ("data_python.json", "data.json"))
            self.store = core.DataStore(directory)
            if fresh:
                sample = core.new_class("示例", "3D 示例班级")
                names = '张子辰 李明轩 王一诺 赵嘉宁 陈宇航 刘思远 周梓涵 孙雨桐 吴俊熙 郑可欣 冯浩然 褚星宇 卫安然 蒋若宁 沈亦帆 韩乐言 杨书瑶 朱景行 秦予安 尤清越 许知夏 何沐阳 吕星河 施语宁 孔文博 曹以恒 严晨曦 华锦程 金若溪 魏承宇 陶书言 姜南星 戚明哲 谢云舒 邹逸辰 喻子墨 柏初晴 水安宁 窦清扬 章致远 云泽宇 苏言希 潘奕宁 葛星野 奚嘉禾 范可然 彭书墨 郎雨泽 鲁以宁 韦景澄'.split()
                sample["Students"] = [core.new_student(name, str(i + 1)) for i, name in enumerate(names)]
                for i, student in enumerate(sample["Students"][:5]):
                    student.update(VipWaiting=True, VipOrder=i + 1)
                sample["NextVipOrder"] = 6
                self.store.data["Classes"] = [sample]
                self.store.data["LastClassId"] = sample["Id"]
                if not self.store.save():
                    raise IOError(self.store.last_error)
        except Exception as exc:
            messagebox.showerror("无法读取数据", str(exc), parent=self)
            self.destroy()
            raise
        self.maintenance = maintenance.LocalMaintenance(self.store)
        self.classroom: dict | None = None
        self.mode_var = tk.StringVar(value="不重复")
        self.class_var = tk.StringVar()
        self.count_var = tk.StringVar(value="1")
        self.progress_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self._class_order: list[dict] = []
        self._batch_items: dict[str, dict] = {}
        self._dirty = False
        self.board_server = None
        self.board_window = None
        self.primary_board = board_first
        self._page_ready = None
        self._window_check = False
        self._fullscreen = False
        self.displayed_batch_id: str | None = None
        self.history_visible = True
        self.detail_visible = True
        self.detail_mode = tk.StringVar(value="auto")
        self._history_sync = False
        self._build()
        self._build_home()
        self.refresh_classes()
        self.show_home()
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.bind("<F11>", lambda _e: self.toggle_fullscreen())
        self.bind("<Escape>", lambda _e: self.exit_fullscreen())
        self.bind("<Control-m>", lambda _e: self.open_manager())
        self.bind("<space>", self._space_draw)

    def _build(self):
        outer = ttk.Frame(self, padding=16)
        self.draw_page = outer

        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="班级").pack(side="left", padx=(0, 5))
        self.class_combo = ttk.Combobox(top, textvariable=self.class_var, state="readonly", width=28)
        self.class_combo.pack(side="left", padx=(0, 8))
        self.class_combo.bind("<<ComboboxSelected>>", self._class_changed)
        ttk.Button(top, text="新建班级", command=self.new_class).pack(side="left", padx=4)
        self.manage_button = ttk.Button(top, text="名单管理  Ctrl+M", style="Accent.TButton", command=self.open_manager)
        self.manage_button.pack(side="left", padx=8)
        self.settings_button = ttk.Button(top, text="抽取设置", command=self.open_settings)
        self.settings_button.pack(side="left", padx=4)
        ttk.Button(top, text="全屏 F11", command=self.toggle_fullscreen).pack(side="right", padx=4)

        mode_bar = ttk.Frame(outer)
        mode_bar.pack(fill="x", pady=(9, 8))
        ttk.Label(mode_bar, text="抽取模式").pack(side="left", padx=(0, 5))
        self.mode_combo = ttk.Combobox(mode_bar, textvariable=self.mode_var, values=core.MODES, state="readonly", width=10)
        self.mode_combo.pack(side="left", padx=(0, 7))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(mode_bar, text="设为默认模式", command=self.set_default_mode).pack(side="left", padx=4)
        ttk.Button(mode_bar, text="模式回默认", command=self.reset_mode).pack(side="left", padx=4)
        ttk.Separator(mode_bar, orient="vertical").pack(side="left", fill="y", padx=12)
        self.round_label = ttk.Label(mode_bar, text="第 1 轮", font=("Microsoft YaHei UI", 12, "bold"))
        self.round_label.pack(side="left", padx=6)
        ttk.Button(mode_bar, text="开始新一轮", command=self.next_round).pack(side="left", padx=4)
        ttk.Button(mode_bar, text="重置轮数", command=self.reset_round).pack(side="left", padx=4)
        self.board_button = ttk.Button(mode_bar, text="返回 3D 棋盘", style="Accent.TButton", command=self.open_board)
        self.board_button.pack(side="right", padx=4)

        heading_row = ttk.Frame(outer)
        heading_row.pack(fill="x", pady=(3, 2))
        self.heading = ttk.Label(heading_row, text="请选择班级", font=("Microsoft YaHei UI", 21, "bold"))
        self.heading.pack(side="left")
        self.detail_toggle_button = ttk.Button(heading_row, text="隐藏批次详情", command=self.toggle_detail)
        self.detail_toggle_button.pack(side="right", padx=4)
        self.history_toggle_button = ttk.Button(heading_row, text="隐藏本轮历史批次", command=self.toggle_history)
        self.history_toggle_button.pack(side="right", padx=4)
        ttk.Label(outer, textvariable=self.progress_var, foreground="#52667a").pack(anchor="w", pady=(0, 9))

        body = ttk.Panedwindow(outer, orient="horizontal")
        self.body = body
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        self.history_panel = right
        body.add(left, weight=3)
        body.add(right, weight=2)

        left_header = ttk.Frame(left)
        left_header.pack(fill="x")
        ttk.Label(left_header, text="本次抽取结果", font=("Microsoft YaHei UI", 22, "bold")).pack(pady=12)
        self.result_canvas = tk.Canvas(left, bg="white", bd=0, highlightthickness=0)
        self.result_scroll = ttk.Scrollbar(left, orient="vertical", command=self.result_canvas.yview)
        self.result_canvas.configure(yscrollcommand=self.result_scroll.set)
        self.result_scroll.pack(side="right", fill="y")
        self.result_canvas.pack(side="left", fill="both", expand=True)
        self.card_frame = tk.Frame(self.result_canvas, bg="white")
        self.canvas_window = self.result_canvas.create_window((0, 0), window=self.card_frame, anchor="nw")
        self.card_frame.bind("<Configure>", lambda _e: self.result_canvas.configure(scrollregion=self.result_canvas.bbox("all")))
        self.result_canvas.bind("<Configure>", lambda e: self.result_canvas.itemconfigure(self.canvas_window, width=e.width))
        self.result_canvas.bind("<MouseWheel>", lambda e: self.result_canvas.yview_scroll(int(-e.delta / 120), "units"))

        right_split = ttk.Panedwindow(right, orient="vertical")
        self.right_split = right_split
        right_split.pack(fill="both", expand=True)
        history_box = ttk.Frame(right_split, padding=(12, 0, 0, 0))
        self.history_section = history_box
        detail_box = ttk.Frame(right_split, padding=(12, 0, 0, 0))
        self.detail_section = detail_box
        right_split.add(history_box, weight=3)
        right_split.add(detail_box, weight=2)
        ttk.Label(history_box, text="本轮历史批次", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", pady=(4, 7))
        tree_frame = ttk.Frame(history_box)
        tree_frame.pack(fill="both", expand=True)
        self.history = ttk.Treeview(tree_frame, columns=("time", "mode", "round", "count", "preview"), show="tree headings")
        self.history.heading("#0", text="日期 / 批次")
        self.history.column("#0", width=205, stretch=False)
        for key, title, width in (("time", "时刻", 66), ("mode", "模式", 68), ("round", "轮", 48), ("count", "人数", 48), ("preview", "结果预览", 250)):
            self.history.heading(key, text=title)
            self.history.column(key, width=width, stretch=False)
        history_v = ttk.Scrollbar(tree_frame, orient="vertical", command=self.history.yview)
        history_h = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.history.xview)
        self.history.configure(yscrollcommand=history_v.set, xscrollcommand=history_h.set)
        self.history.grid(row=0, column=0, sticky="nsew")
        history_v.grid(row=0, column=1, sticky="ns")
        history_h.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.history.bind("<<TreeviewSelect>>", self.show_history_detail)
        detail_bar = ttk.Frame(detail_box)
        detail_bar.pack(fill="x", pady=(9, 3))
        ttk.Label(detail_bar, text="批次详情", font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        ttk.Radiobutton(detail_bar, text="自动显示当前批次", variable=self.detail_mode, value="auto",
                        command=self.set_detail_mode).pack(side="right", padx=3)
        ttk.Radiobutton(detail_bar, text="查看之前选中批次", variable=self.detail_mode, value="manual",
                        command=self.set_detail_mode).pack(side="right", padx=3)
        self.detail = tk.Text(detail_box, height=5, wrap="word", bg="#f8fafc", fg="#23384a", bd=0, padx=9, pady=7)
        detail_scroll = ttk.Scrollbar(detail_box, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side="right", fill="y")
        self.detail.pack(side="left", fill="both", expand=True)
        self.detail.configure(state="disabled")

        actions = ttk.Frame(outer)
        self.actions = actions
        actions.pack(side="bottom", fill="x", pady=(6, 2), before=body)
        ttk.Label(actions, text="人数").pack(side="left")
        self.count_spin = ttk.Spinbox(actions, from_=1, to=999, textvariable=self.count_var, width=5)
        self.count_spin.pack(side="left", padx=6)
        self.draw_button = ttk.Button(actions, text="抽取", style="Accent.TButton", command=self.draw_action)
        self.draw_button.pack(side="left", padx=5)
        self.draw_button.bind("<Button-1>", self._disabled_draw_hint)
        self.clear_button = ttk.Button(actions, text="清空展示", command=self.clear_result_display)
        self.clear_button.pack(side="left", padx=5)
        self.replace_button = ttk.Button(actions, text="补抽缺额", command=self.replace_action)
        self.replace_button.pack(side="left", padx=5)
        self.close_batch_button = ttk.Button(actions, text="结束本批", command=self.close_batch)
        self.close_batch_button.pack(side="left", padx=5)
        self.return_button = ttk.Button(actions, text="返回主页", command=self.show_home)
        self.return_button.pack(side="right", padx=5)
        self.retry_button = ttk.Button(actions, text="重试保存", command=self.commit)
        self.retry_button.pack(side="right")
        self.status_label = ttk.Label(outer, textvariable=self.status_var, foreground="#24784c")
        self.status_label.pack(side="bottom", anchor="w", pady=(0, 3), before=body)
        self.count_var.trace_add("write", lambda *_: self.refresh_buttons())

    def _build_home(self):
        self.home_page = ttk.Frame(self, padding=35)
        center = ttk.Frame(self.home_page)
        center.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(center, text="班级随机点名器", font=("Microsoft YaHei UI", 30, "bold")).pack(pady=(0, 10))
        ttk.Label(center, text="V1.0 · 离线运行", foreground="#60758a").pack(pady=(0, 30))
        ttk.Button(center, text="开始", style="Accent.TButton", command=self.open_start,
                   width=24).pack(pady=8, ipady=10)
        ttk.Button(center, text="设置", command=self.open_global_settings,
                   width=24).pack(pady=8, ipady=10)
        self.last_class_label = ttk.Label(center, text="上一次抽取班级：暂无点名记录", foreground="#60758a")
        self.last_class_label.pack(pady=(25, 5))
        self.last_class_button = ttk.Button(center, text="直接进入上一次抽取班级", command=self.open_last_class)
        self.last_class_button.pack(pady=4)

    def show_home(self):
        self.draw_page.pack_forget()
        last_id = self.store.data.get("LastClassId")
        last = next((c for c in self.store.data["Classes"] if c["Id"] == last_id), None)
        self.last_class_label.configure(text=(f"上一次抽取班级：{last.get('Grade', '')} · {last.get('Name', '')}"
                                              if last else "上一次抽取班级：暂无点名记录"))
        self.last_class_button.configure(state="normal" if last else "disabled")
        self.home_page.pack(fill="both", expand=True)

    def show_draw(self):
        self.home_page.pack_forget()
        self.draw_page.pack(fill="both", expand=True)

    def open_last_class(self):
        last_id = self.store.data.get("LastClassId")
        last = next((c for c in self.store.data["Classes"] if c["Id"] == last_id), None)
        if last:
            self.enter_selected_class(last)

    def open_start(self):
        StartWindow(self)

    def enter_selected_class(self, classroom):
        self.enter_class(classroom)
        if self.primary_board: self.open_board()

    def open_global_settings(self):
        GlobalSettingsWindow(self)

    def enter_class(self, classroom: dict):
        self.select_class(classroom)
        self.show_draw()

    def toggle_history(self):
        if self.history_visible:
            self.right_split.forget(self.history_section)
            self.history_visible = False
            self.history_toggle_button.configure(text="展开本轮历史批次")
        else:
            self.right_split.insert(0, self.history_section, weight=3)
            self.history_visible = True
            self.history_toggle_button.configure(text="隐藏本轮历史批次")
        self.update_right_region()

    def toggle_detail(self):
        if self.detail_visible:
            self.right_split.forget(self.detail_section)
            self.detail_visible = False
            self.detail_toggle_button.configure(text="展开批次详情")
        else:
            self.right_split.add(self.detail_section, weight=2)
            self.detail_visible = True
            self.detail_toggle_button.configure(text="隐藏批次详情")
        self.update_right_region()

    def update_right_region(self):
        present = str(self.history_panel) in self.body.panes()
        if (self.history_visible or self.detail_visible) and not present:
            self.body.add(self.history_panel, weight=2)
        elif not self.history_visible and not self.detail_visible and present:
            self.body.forget(self.history_panel)

    def clear_result_display(self):
        self.displayed_batch_id = None
        self.show_batch(None)

    def set_detail_mode(self):
        if not self.classroom or not self.can_edit():
            return
        self.classroom["AutoCurrentDetail"] = self.detail_mode.get() == "auto"
        self.commit()

    def _space_draw(self, event):
        if not self.draw_page.winfo_ismapped() or isinstance(event.widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Button, ttk.Button)):
            return
        if self.draw_button.instate(["disabled"]):
            self._disabled_draw_hint()
        else:
            self.draw_action()

    def toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)

    def exit_fullscreen(self):
        if self._fullscreen:
            self._fullscreen = False
            self.attributes("-fullscreen", False)

    def close_app(self):
        if self.primary_board and self.board_window and self.board_window.alive():
            self.withdraw()
            return
        self.finish_app()

    def finish_app(self):
        if self._dirty and not messagebox.askyesno("保存失败", "当前更改尚未保存到U盘。仍要关闭吗？", parent=self):
            self.deiconify()
            return
        if self.board_window: self.board_window.close()
        if self.board_server:
            self.board_server.stop()
        self.destroy()

    def start_board_primary(self):
        classes = self.store.data['Classes']
        classroom = next((c for c in classes if c['Id'] == self.store.data.get('LastClassId')), classes[0] if classes else None)
        if not classroom:
            self.deiconify(); self.show_home(); return
        self.enter_class(classroom)
        self.open_board()

    def show_board_window(self):
        if self.board_window is None: self.board_window = BoardWindow()
        previous = self.board_window.process
        self.board_window.open(self.board_server.url)
        if self.primary_board: self.withdraw()
        if self.board_window.process is previous: return
        process = self.board_window.process
        def monitor():
            if process.poll() is None:
                self.after(300, monitor); return
            if self._window_check: return
            if process.returncode:
                self.deiconify()
                messagebox.showerror('3D 窗口未能启动', '请检查本机 WebView2 运行环境。\n' + self.board_window.diagnostic(), parent=self)
            elif self.primary_board and self.state() == 'withdrawn':
                self.finish_app()
        self.after(300, monitor)

    def open_board(self):
        if not self.classroom or not self.can_edit():
            return
        if not any(not s.get("Archived") for s in self.classroom["Students"]):
            self.deiconify()
            messagebox.showinfo("名单为空", "请先添加学生。", parent=self)
            return
        context = (self.classroom["Id"], self.mode_var.get())
        if self.board_server and not self.board_server.stopped and self.board_context == context:
            self.show_board_window()
            return
        if self.board_server:
            self.board_server.stop()
        self.board_context = context
        assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "board_web"
        self.board_server = BoardServer(assets, self.board_dispatch)
        server = self.board_server
        def poll():
            if not server.stopped:
                server.poll()
                self.after(30, poll)
        poll()
        self._page_ready = None
        self.show_board_window()

    def board_dispatch(self, command, payload):
        class_id, mode = self.board_context
        if self._dirty:
            raise ValueError("主界面有尚未保存的更改，请先重试保存。")
        if command not in {"state", "native", "presented", "ready"} and self.grab_current() is not None:
            raise ValueError("请先关闭主程序中的管理或设置窗口，再继续棋盘操作。")
        controller = board_rules.BoardController(self.store, class_id, mode)
        if command == 'ready':
            self._page_ready = payload
            return {'ok': True}
        if command == "presented":
            if self.classroom and self.classroom["Id"] == class_id:
                batch = next((b for b in self.classroom["Batches"] if b["Id"] == payload.get("batchId")), None)
                if batch:
                    self.displayed_batch_id = batch["Id"]
                    self.refresh()
            return {"ok": True}
        if command == "native":
            if payload.get("action") == "board-fullscreen":
                if not self.board_window or not self.board_window.alive():
                    raise ValueError("3D 棋盘窗口尚未启动。")
                self.board_window.send('fullscreen')
                return {"ok": True}
            classroom = controller.classroom()
            def show():
                self.deiconify(); self.lift(); self.focus_force()
                self.enter_class(classroom); self.mode_var.set(mode)
                if payload.get("action") == "roster": self.open_manager()
                elif payload.get("action") == "settings": self.open_settings()
                elif payload.get("action") == "history": HistoryWindow(self, classroom)
                elif payload.get("action") == "original": self.refresh()
            self.after_idle(show)
            return {"ok": True}
        response = controller.dispatch(command, payload)
        if command == 'console':
            self.board_context = (class_id, controller.mode)
            if self.classroom and self.classroom['Id'] == class_id: self.mode_var.set(controller.mode)
        if command not in {"state", "draw"} and self.classroom and self.classroom["Id"] == class_id:
            self.refresh()
        return response

    def can_edit(self) -> bool:
        if not self._dirty:
            return True
        messagebox.showerror("保存失败", "当前更改尚未保存，请先重试保存。\n" + str(self.store.last_error), parent=self)
        return False

    def commit(self):
        self._dirty = not self.store.save()
        self.refresh()
        if self._dirty:
            messagebox.showerror("保存失败", "当前更改尚未保存到U盘。请检查存储设备并重试。\n" + str(self.store.last_error), parent=self)

    def after_storage_change(self):
        current_id = self.classroom["Id"] if self.classroom else None
        self.classroom = next((item for item in self.store.data["Classes"] if item["Id"] == current_id), None)
        self.displayed_batch_id = None
        self._dirty = False
        self.refresh_classes()
        if self.classroom:
            self.select_class(self.classroom)
        else:
            self.class_var.set("")
            self.show_home()

    def refresh_classes(self):
        self._class_order = sorted(self.store.data["Classes"], key=lambda c: (c.get("Grade", ""), c.get("Name", "")))
        self.class_combo["values"] = [f"{c.get('Grade', '')} · {c.get('Name', '')}" for c in self._class_order]
        if self.classroom in self._class_order:
            self.class_combo.current(self._class_order.index(self.classroom))

    def _class_changed(self, _event=None):
        index = self.class_combo.current()
        if 0 <= index < len(self._class_order):
            self.select_class(self._class_order[index])

    def select_class(self, classroom: dict):
        if not self.can_edit():
            return
        self.classroom = classroom
        self.displayed_batch_id = None
        self.detail_mode.set("auto" if classroom.get("AutoCurrentDetail", True) else "manual")
        self.mode_var.set(classroom.get("DefaultMode") if classroom.get("DefaultMode") in core.MODES else "不重复")
        if classroom in self._class_order:
            self.class_combo.current(self._class_order.index(classroom))
        self.refresh()

    def new_class(self):
        if not self.can_edit():
            return
        grade = simpledialog.askstring("新建班级", "年级：", parent=self)
        if grade is None:
            return
        name = simpledialog.askstring("新建班级", "班级名称：", parent=self)
        if name is None:
            return
        grade, name = grade.strip(), name.strip()
        if not grade or not name:
            messagebox.showwarning("新建班级", "年级和班级名称都不能为空。", parent=self)
            return
        if any(c.get("Grade") == grade and c.get("Name") == name for c in self.store.data["Classes"]):
            messagebox.showwarning("新建班级", "同年级同名班级已存在。", parent=self)
            return
        classroom = core.new_class(grade, name)
        self.store.data["Classes"].append(classroom)
        self.refresh_classes()
        self.select_class(classroom)
        self.commit()

    def set_default_mode(self):
        if not self.classroom or not self.can_edit():
            return
        self.classroom["DefaultMode"] = self.mode_var.get()
        self.commit()

    def reset_mode(self):
        if not self.classroom:
            return
        default = self.classroom.get("DefaultMode", "不重复")
        self.mode_var.set(default if default in core.MODES else "不重复")
        self.refresh()

    def _pending_batch(self) -> dict | None:
        if not self.classroom or not self.classroom["Batches"]:
            return None
        batch = self.classroom["Batches"][-1]
        return batch if core.missing_positions(batch) and not batch.get("ClosedWithMissing") else None

    def next_round(self):
        if not self.classroom or not self.can_edit():
            return
        if self._pending_batch():
            messagebox.showwarning("尚有缺额", "请先补抽或明确结束本批。", parent=self)
            return
        mode = self.mode_var.get()
        explanation = "本轮已抽学生会重新获得资格。" if mode == "不重复" else "本模式的轮内次数重新开始，历史和均衡权重保留。"
        if not messagebox.askyesno("开始新一轮", f"开始“{mode}”新一轮？\n{explanation}", parent=self):
            return
        core.new_round(self.classroom, mode)
        self.commit()

    def reset_round(self):
        if not self.classroom or not self.can_edit():
            return
        if self._pending_batch():
            messagebox.showwarning("尚有缺额", "请先补抽或明确结束本批。", parent=self)
            return
        mode = self.mode_var.get()
        explanation = "已抽资格重新开始。" if mode == "不重复" else "轮内次数重新开始，均衡权重保留。"
        if not messagebox.askyesno("重置轮数", f"将“{mode}”模式重置到第 1 轮，{explanation}\n所有历史批次保留，旧第 1 轮与新周期分开记录。确认吗？", parent=self):
            return
        core.reset_round(self.classroom, mode)
        self.commit()

    def _count(self) -> int:
        try:
            value = int(self.count_var.get())
            if value < 1:
                raise ValueError
            return value
        except ValueError:
            raise ValueError("人数必须是正整数。")

    def draw_action(self):
        if not self.classroom or not self.can_edit():
            return
        try:
            batch = core.draw(self.classroom, self.mode_var.get(), self._count())
        except ValueError as exc:
            messagebox.showinfo("无法抽取", str(exc), parent=self)
            return
        self.store.data["LastClassId"] = self.classroom["Id"]
        self.displayed_batch_id = batch["Id"]
        self.commit()

    def _disabled_draw_hint(self, _event=None):
        if not self.draw_button.instate(["disabled"]):
            return
        if not self.classroom:
            return "break"
        if not self.can_edit():
            return "break"
        if self._pending_batch():
            messagebox.showinfo("暂不能抽取", "上一批仍有缺额，请先补抽或明确结束本批。", parent=self)
            return "break"
        try:
            count = self._count()
        except ValueError as exc:
            messagebox.showinfo("暂不能抽取", str(exc), parent=self)
            return "break"
        issue = core.preview(self.classroom, self.mode_var.get(), count)
        shortage = core.vip_shortage(self.classroom, self.mode_var.get(), count)
        if issue and shortage and not self.classroom.get("FillVipShortage") and any(
                not student.get("Archived") for student in self.classroom["Students"]):
            available, planned = shortage
            if messagebox.askyesno(
                "VIP人数不足",
                f"当前可抽取VIP人数不足：可抽 {available} 人，需要 {planned} 人。\n"
                "可以前往抽取设置调整 VIP 人数，或开启普通人员补齐。\n\n现在前往抽取设置吗？",
                parent=self,
            ):
                self.open_settings()
        elif issue:
            messagebox.showinfo("暂不能抽取", issue, parent=self)
        return "break"

    def replace_action(self):
        if not self.classroom or not self.can_edit():
            return
        batch = self.classroom["Batches"][-1] if self.classroom["Batches"] else None
        if not batch:
            return
        try:
            core.replace_missing(self.classroom, batch)
        except ValueError as exc:
            messagebox.showinfo("无法补抽", str(exc), parent=self)
            return
        self.displayed_batch_id = batch["Id"]
        self.commit()

    def close_batch(self):
        if not self.classroom or not self.can_edit():
            return
        batch = self._pending_batch()
        if not batch:
            return
        slots = "、".join(str(x) for x in core.missing_positions(batch))
        if not messagebox.askyesno("结束本批", f"第 {slots} 位仍为空缺。结束后可抽下一批，空缺仍保留在历史中。确认吗？", parent=self):
            return
        batch["ClosedWithMissing"] = True
        self.commit()

    def refresh_buttons(self):
        classroom = self.classroom
        try:
            count = self._count()
        except ValueError:
            count = 0
        last = classroom["Batches"][-1] if classroom and classroom["Batches"] else None
        pending = bool(last and core.missing_positions(last) and not last.get("ClosedWithMissing"))
        issue = core.preview(classroom, self.mode_var.get(), count) if classroom and count else "人数无效"
        self.draw_button.configure(state="normal" if classroom and not self._dirty and not pending and issue is None else "disabled")
        self.replace_button.configure(state="normal" if classroom and not self._dirty and pending else "disabled")
        self.close_batch_button.configure(state="normal" if classroom and not self._dirty and pending else "disabled")
        self.manage_button.configure(state="normal" if classroom and not self._dirty else "disabled")
        self.settings_button.configure(state="normal" if classroom and not self._dirty else "disabled")
        self.retry_button.configure(state="normal" if self._dirty else "disabled")

    def refresh(self):
        classroom = self.classroom
        if classroom:
            core.expire_absence(classroom)
            mode = self.mode_var.get()
            self.heading.configure(text=f"{classroom.get('Grade', '')} · {classroom.get('Name', '')}")
            ordinary = len(core.ordinary_candidates(classroom, mode))
            vip = len(core.vip_candidates(classroom, mode))
            seen_count = sum(core.seen(classroom, mode, s["Id"]) for s in classroom["Students"])
            self.round_label.configure(text=f"{mode} 第 {core.classroom_round(classroom, mode)} 轮")
            self.progress_var.set(f"普通候选 {ordinary} 人    VIP候选 {vip} 人" + (f"    本轮已抽 {seen_count} 人" if mode == "不重复" else ""))
            displayed = next((b for b in classroom["Batches"] if b["Id"] == self.displayed_batch_id), None)
            self.show_batch(displayed)
            self.refresh_history()
        if self._dirty:
            self.status_var.set("⚠ 当前更改尚未保存到数据目录：" + str(self.store.last_error))
            self.status_label.configure(foreground="#b42318")
        elif self.store.last_saved:
            self.status_var.set(f"✓ 已保存到 {self.store.path}  ·  {self.store.last_saved:%H:%M:%S}")
            self.status_label.configure(foreground="#24784c")
        elif self.store.migrated_from_legacy:
            self.status_var.set("已读取旧版数据；首次修改将另存为 data_python.json，原 data.json 保留。")
        else:
            self.status_var.set("尚未保存数据。首次修改后将在当前数据目录创建 data_python.json。")
        self.refresh_buttons()

    def show_batch(self, batch: dict | None):
        for child in self.card_frame.winfo_children():
            child.destroy()
        if not batch or not self.classroom:
            return
        for position in range(1, batch["Count"] + 1):
            entry = next((e for e in reversed(batch["Entries"]) if e["Position"] == position and e.get("Valid")), None)
            row, col = divmod(position - 1, 3)
            if entry is None:
                event = next((e for e in batch.get("BoardEvents", []) if e["Position"] == position and not e.get("ResolvedStudentId")), None)
                text = f"宝箱事件\n{event['Title']}" if event else f"第 {position} 位\n待补抽"
                button = tk.Button(self.card_frame, text=text, width=15, height=4, relief="flat", bg="#fff0f0",
                                   fg="#b42318", font=("Microsoft YaHei UI", 16))
            else:
                student = core.student_by_id(self.classroom, entry["StudentId"])
                text = (student["Name"] if student else "已移出人员") + ("\n（VIP）" if entry.get("Vip") else "")
                if student and student.get("Number"):
                    text += "\n" + student["Number"]
                button = tk.Button(self.card_frame, text=text, width=15, height=4, relief="flat",
                                   bg="#fff1c9" if entry.get("Vip") else "#e8f2ff", fg="#17324f",
                                   font=("Microsoft YaHei UI", 17, "bold"),
                                   command=lambda student=student: self.open_absence(student) if student else None)
            button.grid(row=row, column=col, padx=10, pady=10, sticky="n")
        valid = [e for e in batch["Entries"] if e.get("Valid")]
        actual_vip = sum(bool(e.get("Vip")) for e in valid)
        fill = sum(e.get("Source") == "普通补位" for e in valid)
        summary = f"计划VIP {batch.get('PlannedVip', 0)}，实际VIP {actual_vip}，普通 {len(valid) - actual_vip}"
        if fill:
            summary += f"（补位 {fill}）"
        if batch.get("ClosedWithMissing"):
            summary += "；本批有未补缺额，已明确结束"
        ttk.Label(self.card_frame, text=summary, background="white", foreground="#52667a").grid(
            row=(batch["Count"] + 2) // 3 + 1, column=0, columnspan=3, pady=(25, 10)
        )

    def refresh_history(self):
        if not self.classroom:
            return
        selected = self.history.selection()
        selected_id = selected[0] if selected else None
        mode = self.mode_var.get()
        round_number = core.classroom_round(self.classroom, mode)
        cycle = core.classroom_cycle(self.classroom, mode)
        batches = [b for b in reversed(self.classroom["Batches"])
                   if b.get("Mode") == mode and b.get("Round", 1) == round_number
                   and b.get("Cycle", 0) == cycle]
        self._history_sync = True
        self.history.delete(*self.history.get_children())
        self._batch_items.clear()
        dates: dict[str, str] = {}
        for batch in batches:
            moment = core.parse_date(batch.get("Time")) or core.now()
            day_key = moment.strftime("%Y-%m-%d")
            if day_key not in dates:
                dates[day_key] = self.history.insert("", "end", text=f"——{moment.year % 100:02d}年{moment.month:02d}月{moment.day:02d}日——", open=True,
                                                     values=("", "", "", "", ""))
            valid = [e for e in batch["Entries"] if e.get("Valid")]
            names = [batch_name(self.classroom, e).split("（")[0] + ("★" if e.get("Vip") else "") for e in valid]
            preview = "、".join(names[:2]) + (f" 等{len(names)}人" if len(names) > 2 else "")
            item_id = "b-" + batch["Id"]
            self.history.insert(dates[day_key], "end", iid=item_id, text="批次", values=(
                moment.strftime("%H:%M"), batch.get("Mode", ""),
                f"{batch.get('Round', 1)}", f"{len(valid)}/{batch.get('Count', 0)}", preview,
            ))
            self._batch_items[item_id] = batch
        if self.detail_mode.get() == "auto":
            latest = "b-" + batches[0]["Id"] if batches else None
            if latest:
                self.history.selection_set(latest)
                self._set_detail(batch_detail_text(self.classroom, batches[0]))
            else:
                self._set_detail("本轮暂无点名记录。")
        elif selected_id and self.history.exists(selected_id) and selected_id in self._batch_items:
            self.history.selection_set(selected_id)
            self._set_detail(batch_detail_text(self.classroom, self._batch_items[selected_id]))
        else:
            self._set_detail("请选择本轮的一个批次。")
        self._history_sync = False

    def _set_detail(self, text: str):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def show_history_detail(self, _event=None):
        if not self.classroom or self._history_sync:
            return
        selected = self.history.selection()
        batch = self._batch_items.get(selected[0]) if selected else None
        if not batch:
            return
        if self.detail_mode.get() == "auto":
            current = next(iter(self._batch_items.values()), None)
            if current and batch["Id"] != current["Id"]:
                self.detail_mode.set("manual")
                self.set_detail_mode()
                return
        if self.detail_mode.get() == "manual":
            self._set_detail(batch_detail_text(self.classroom, batch))

    def open_manager(self):
        if self.classroom and self.can_edit():
            ManagerWindow(self, self.classroom)

    def open_settings(self):
        if self.classroom and self.can_edit():
            SettingsWindow(self, self.classroom)

    def open_absence(self, student: dict | None):
        if self.classroom and student and self.can_edit():
            AbsenceWindow(self, self.classroom, student)


class ManagerWindow(tk.Toplevel):
    def __init__(self, app: PickerApp, classroom: dict):
        super().__init__(app)
        self.app, self.classroom = app, classroom
        self.title(f"{classroom.get('Grade')} · {classroom.get('Name')} — 名单管理")
        self.geometry("1080x760")
        self.minsize(850, 600)
        self.transient(app)
        self.grab_set()
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text="导入Excel（.xlsx）", style="Accent.TButton", command=self.import_excel).pack(side="left", padx=(0, 7))
        ttk.Button(top, text="导出Excel（.xlsx）", command=self.export_excel).pack(side="left", padx=7)
        ttk.Label(top, text="第一张表：A列姓名，B列学号；先预览再写入。", foreground="#52667a").pack(side="left", padx=13)

        grid_frame = ttk.Frame(outer)
        grid_frame.pack(fill="both", expand=True)
        self.roster = ttk.Treeview(grid_frame, columns=("name", "number", "state", "weight"), show="headings", selectmode="browse")
        for key, title, width in (("name", "姓名", 240), ("number", "学号", 210), ("state", "状态", 330), ("weight", "均衡权重", 120)):
            self.roster.heading(key, text=title)
            self.roster.column(key, width=width, stretch=True)
        y_scroll = ttk.Scrollbar(grid_frame, orient="vertical", command=self.roster.yview)
        self.roster.configure(yscrollcommand=y_scroll.set)
        self.roster.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.rowconfigure(0, weight=1)
        self.roster.tag_configure("absent", foreground="#7c8797")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=9)
        for title, callback in (("修改姓名", self.rename), ("加入 / 取消VIP", self.change_vip), ("VIP上移", lambda: self.move_vip(-1)),
                                ("VIP下移", lambda: self.move_vip(1)), ("临时缺席 / 恢复", self.set_absence),
                                ("移出 / 恢复", self.archive)):
            ttk.Button(actions, text=title, command=callback).pack(side="left", padx=4)

        ttk.Label(outer, text="也可从Excel复制姓名和学号两列，粘贴到下方：", foreground="#52667a").pack(anchor="w")
        paste_row = ttk.Frame(outer)
        paste_row.pack(fill="x", pady=(4, 0))
        self.paste = tk.Text(paste_row, height=5, wrap="none", font=("Microsoft YaHei UI", 10))
        self.paste.pack(side="left", fill="both", expand=True)
        ttk.Button(paste_row, text="从粘贴内容导入", command=self.import_paste).pack(side="left", padx=(8, 0))
        self.refresh_roster()

    def refresh_roster(self):
        selected = self.roster.selection()
        selected_id = selected[0] if selected else None
        self.roster.delete(*self.roster.get_children())
        queue_positions = core.vip_queue_positions(self.classroom)
        for student in sorted(self.classroom["Students"], key=lambda s: (s.get("Name", ""), s.get("Number", ""))):
            if student.get("Archived"):
                state = "已移出"
            elif core.is_absent(student):
                state = "临时缺席"
            elif student.get("VipWaiting"):
                state = f"VIP等待 #{queue_positions[student['Id']]}"
            elif core.vip_hold(self.classroom, student):
                state = "VIP已完成，待下轮"
            else:
                state = "普通"
            self.roster.insert("", "end", iid=student["Id"], values=(student["Name"], student.get("Number", ""), state,
                                                               f"{core.weight(self.classroom, student):.2f}"),
                               tags=("absent",) if core.is_absent(student) else ())
        if selected_id and self.roster.exists(selected_id):
            self.roster.selection_set(selected_id)

    def selected_student(self) -> dict | None:
        selected = self.roster.selection()
        if not selected:
            messagebox.showinfo("选择学生", "请先在名单中选择学生。", parent=self)
            return None
        return core.student_by_id(self.classroom, selected[0])

    def change_vip(self):
        student = self.selected_student()
        if not student or not self.app.can_edit():
            return
        try:
            if student.get("VipWaiting"):
                student["VipWaiting"] = False
            else:
                core.add_vip(self.classroom, student)
        except ValueError as exc:
            messagebox.showinfo("VIP安排", str(exc), parent=self)
            return
        self.app.commit()
        self.refresh_roster()

    def move_vip(self, direction: int):
        student = self.selected_student()
        if not student or not self.app.can_edit():
            return
        core.move_vip(self.classroom, student, direction)
        self.app.commit()
        self.refresh_roster()

    def set_absence(self):
        student = self.selected_student()
        if student and self.app.can_edit():
            AbsenceWindow(self.app, self.classroom, student, on_close=self.refresh_roster)

    def archive(self):
        student = self.selected_student()
        if not student or not self.app.can_edit():
            return
        action = "恢复" if student.get("Archived") else "移出"
        if messagebox.askyesno("确认", f"{action} {student['Name']}？历史记录保留。", parent=self):
            student["Archived"] = not student.get("Archived")
            self.app.commit()
            self.refresh_roster()

    def rename(self):
        student = self.selected_student()
        if not student or not self.app.can_edit(): return
        name = simpledialog.askstring('修改姓名', '请输入姓名（学号、VIP 与点名记录保留）：', initialvalue=student['Name'], parent=self)
        if name is None: return
        try: core.rename_student(self.classroom, student['Id'], name)
        except ValueError as exc:
            messagebox.showerror('修改姓名', str(exc), parent=self); return
        self.app.commit(); self.refresh_roster()

    def import_excel(self):
        if not self.app.can_edit():
            return
        path = filedialog.askopenfilename(parent=self, title="选择Excel名单", filetypes=[("Excel工作簿", "*.xlsx")])
        if not path:
            return
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                sheet = workbook.worksheets[0]
                rows = []
                for row_number, cells in enumerate(sheet.iter_rows(values_only=True), 1):
                    if row_number > 10000:
                        raise ValueError("名单超过10000行，请先拆分。")
                    name = cells[0] if cells else None
                    number = cells[1] if len(cells) > 1 else None
                    status = cells[2] if len(cells) > 2 else None
                    if name is None and number is None:
                        continue
                    if row_number == 1 and str(name).strip() in ("姓名", "Name") and str(number).strip() in ("学号", "ID", "Student ID"):
                        continue
                    numeric = isinstance(number, (int, float)) and not isinstance(number, bool)
                    if isinstance(number, float) and number.is_integer():
                        number = int(number)
                    rows.append((row_number, str(name or "").strip(), str(number or "").strip(), str(status or "").strip(), numeric))
            finally:
                workbook.close()
            self.apply_import(rows, Path(path).name)
        except Exception as exc:
            messagebox.showerror("Excel导入失败", str(exc), parent=self)

    def import_paste(self):
        if not self.app.can_edit():
            return
        rows = []
        for line_number, line in enumerate(self.paste.get("1.0", "end").splitlines(), 1):
            if not line.strip():
                continue
            parts = line.split("\t")
            rows.append((line_number, parts[0].strip(), parts[1].strip() if len(parts) > 1 else "", "", False))
        self.apply_import(rows, "粘贴内容")

    def apply_import(self, rows: list[tuple], source: str):
        proposed = []
        errors = []
        skipped = 0
        numeric_count = 0
        existing = self.classroom["Students"]
        for row_number, name, number, status, numeric in rows:
            if not name:
                errors.append(f"第{row_number}行没有姓名")
                continue
            numeric_count += bool(numeric)
            match = next((s for s in existing if number and s.get("Number") == number), None)
            if match:
                if match.get("Name") == name:
                    skipped += 1
                else:
                    errors.append(f"第{row_number}行学号 {number} 已属于“{match['Name']}”")
                continue
            if number and any(s["Number"] == number for s in proposed):
                errors.append(f"第{row_number}行学号重复：{number}")
                continue
            if not number and (any(s["Name"] == name for s in existing) or any(s["Name"] == name and not s["Number"] for s in proposed)):
                errors.append(f"第{row_number}行同名且无学号，无法区分：{name}")
                continue
            proposed.append(core.new_student(name, number, archived=status in ("已转出", "已移出")))
        if errors:
            messagebox.showerror("导入冲突", "\n".join(errors[:12]), parent=self)
            return
        if not proposed:
            messagebox.showinfo("导入名单", f"没有可新增的学生；跳过已存在 {skipped} 人。", parent=self)
            return
        same_name = sum(any(x["Name"] == s["Name"] for x in existing) for s in proposed)
        preview = f"来源：{source}\n新增 {len(proposed)} 人，跳过已存在 {skipped} 人。"
        if same_name:
            preview += f"\n{same_name} 人与现有名单同名，请核对学号。"
        if numeric_count:
            preview += f"\n{numeric_count} 个学号在Excel中是数字单元格，前导0可能已丢失。"
        preview += "\n\n预览前12人：\n" + "\n".join(f"{s['Name']}  {s['Number']}" for s in proposed[:12])
        if not messagebox.askyesno("确认导入", preview, parent=self):
            return
        self.classroom["Students"].extend(proposed)
        self.app.commit()
        self.refresh_roster()

    def export_excel(self):
        path = filedialog.asksaveasfilename(parent=self, title="导出Excel名单", defaultextension=".xlsx",
                                            initialfile=f"{self.classroom.get('Name', '班级')}_名单.xlsx",
                                            filetypes=[("Excel工作簿", "*.xlsx")])
        if not path:
            return
        temporary = None
        try:
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "名单"
            sheet.append(["姓名", "学号", "状态"])
            sheet.column_dimensions["A"].width = 24
            sheet.column_dimensions["B"].width = 22
            sheet.column_dimensions["C"].width = 14
            for student in self.classroom["Students"]:
                sheet.append([student["Name"], student.get("Number", ""), "已移出" if student.get("Archived") else "在册"])
                sheet.cell(sheet.max_row, 2).number_format = "@"
            target = Path(path)
            with tempfile.NamedTemporaryFile(delete=False, dir=target.parent, suffix=".xlsx") as stream:
                temporary = Path(stream.name)
            workbook.save(temporary)
            os.replace(temporary, target)
            messagebox.showinfo("导出完成", "已导出Excel名单。文件只含姓名、学号和状态，不含点名历史。", parent=self)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()


class AbsenceWindow(tk.Toplevel):
    def __init__(self, app: PickerApp, classroom: dict, student: dict, on_close=None):
        super().__init__(app)
        self.app, self.classroom, self.student, self.on_close = app, classroom, student, on_close
        self.title("临时缺席设置")
        self.geometry("490x300")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"学生：{student_label(student)}", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(0, 16))
        self.preset_var = tk.StringVar(value="下午" if core.now().hour >= 12 else "上午")
        ttk.Label(frame, text="缺席截止时间").pack(anchor="w")
        ttk.Combobox(frame, textvariable=self.preset_var, state="readonly", values=("上午", "下午", "今天", "指定截止时间", "直到手动恢复")).pack(fill="x", pady=(5, 10))
        self.custom_var = tk.StringVar(value=(core.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(frame, textvariable=self.custom_var).pack(fill="x")
        ttk.Label(frame, text="指定截止格式：2026-09-26 18:00", foreground="#64748b").pack(anchor="w", pady=(4, 15))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="否 / 取消", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="是 / 设为缺席", style="Accent.TButton", command=self.apply).pack(side="right", padx=4)
        if core.is_absent(student):
            ttk.Button(buttons, text="恢复参与", command=self.recover).pack(side="left")

    def finish(self):
        self.app.refresh()
        if self.on_close:
            self.on_close()
        self.destroy()

    def apply(self):
        if not self.app.can_edit():
            return
        current = core.now()
        preset = self.preset_var.get()
        indefinite = preset == "直到手动恢复"
        until = None
        if preset == "上午":
            until = current.replace(hour=12, minute=0, second=0, microsecond=0)
            if until <= current:
                messagebox.showwarning("上午已过", "今天12:00已过，请选择其他时段。", parent=self)
                return
        elif preset in ("下午", "今天"):
            until = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif preset == "指定截止时间":
            try:
                until = datetime.strptime(self.custom_var.get().strip(), "%Y-%m-%d %H:%M").astimezone()
            except ValueError:
                messagebox.showwarning("截止时间", "请按 yyyy-mm-dd HH:MM 输入。", parent=self)
                return
            if until <= current:
                messagebox.showwarning("截止时间", "截止时间必须在未来。", parent=self)
                return
        last = self.classroom["Batches"][-1] if self.classroom["Batches"] else None
        affects_result = bool(last and any(e["StudentId"] == self.student["Id"] and e.get("Valid") for e in last["Entries"]))
        effect = "最新一批的有效结果将改为缺席无效，并产生补抽缺额。" if affects_result else "此后暂停参与抽取。"
        deadline = "手动恢复" if indefinite else until.strftime("%Y-%m-%d %H:%M")
        if not messagebox.askyesno("确认进行缺席操作吗？", f"学生：{student_label(self.student)}\n截止：{deadline}\n{effect}", parent=self):
            return
        core.set_absent(self.classroom, self.student, until, indefinite)
        self.app.commit()
        self.finish()

    def recover(self):
        if not self.app.can_edit():
            return
        if not messagebox.askyesno("恢复参与", "恢复参与后，原VIP任务与本轮已抽状态仍保留。确认吗？", parent=self):
            return
        self.student["AbsentUntil"] = None
        self.student["AbsentIndefinite"] = False
        self.app.commit()
        self.finish()


class StartWindow(tk.Toplevel):
    def __init__(self, app: PickerApp):
        super().__init__(app)
        self.app = app
        self.title("开始 · 选择班级")
        self.geometry("680x540")
        self.transient(app)
        self.grab_set()
        self.classes = sorted(app.store.data["Classes"], key=lambda c: (c.get("Grade", ""), c.get("Name", "")))
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        tabs = ttk.Notebook(frame)
        tabs.pack(fill="both", expand=True)
        grade_tab, all_tab, recent_tab = (ttk.Frame(tabs, padding=15) for _ in range(3))
        tabs.add(grade_tab, text="按年级选择")
        tabs.add(all_tab, text="按班级选择")
        tabs.add(recent_tab, text="上一次抽取班级")

        ttk.Label(grade_tab, text="先选择年级，再选择班级").pack(anchor="w", pady=(0, 7))
        self.grade_var = tk.StringVar()
        grades = sorted({c.get("Grade", "") for c in self.classes})
        self.grade_combo = ttk.Combobox(grade_tab, textvariable=self.grade_var, values=grades, state="readonly")
        self.grade_combo.pack(fill="x", pady=(0, 8))
        self.grade_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_grade())
        self.grade_list = tk.Listbox(grade_tab, font=("Microsoft YaHei UI", 12), activestyle="none")
        self.grade_list.pack(fill="both", expand=True)
        self.grade_list.bind("<Double-Button-1>", lambda _e: self.enter_selected(self.grade_list, self.grade_classes))
        ttk.Button(grade_tab, text="进入班级", style="Accent.TButton",
                   command=lambda: self.enter_selected(self.grade_list, self.grade_classes)).pack(anchor="e", pady=(9, 0))
        self.grade_classes: list[dict] = []
        if grades:
            self.grade_var.set(grades[0])
        self.refresh_grade()

        ttk.Label(all_tab, text="搜索年级或班级名称").pack(anchor="w")
        self.search_var = tk.StringVar()
        ttk.Entry(all_tab, textvariable=self.search_var).pack(fill="x", pady=7)
        self.search_var.trace_add("write", lambda *_: self.refresh_all())
        self.all_list = tk.Listbox(all_tab, font=("Microsoft YaHei UI", 12), activestyle="none")
        self.all_list.pack(fill="both", expand=True)
        self.all_list.bind("<Double-Button-1>", lambda _e: self.enter_selected(self.all_list, self.all_classes))
        ttk.Button(all_tab, text="进入班级", style="Accent.TButton",
                   command=lambda: self.enter_selected(self.all_list, self.all_classes)).pack(anchor="e", pady=(9, 0))
        self.all_classes: list[dict] = []
        self.refresh_all()

        last_id = app.store.data.get("LastClassId")
        last = next((c for c in self.classes if c["Id"] == last_id), None)
        label = f"{last.get('Grade', '')} · {last.get('Name', '')}" if last else "暂无点名记录"
        ttk.Label(recent_tab, text=label, font=("Microsoft YaHei UI", 16, "bold")).pack(pady=(45, 20))
        ttk.Button(recent_tab, text="进入上一次抽取班级", style="Accent.TButton",
                   state="normal" if last else "disabled",
                   command=lambda: self.enter_class(last)).pack()
        ttk.Button(frame, text="新建班级", command=self.create_class).pack(anchor="w", pady=(12, 0))

    def refresh_grade(self):
        self.grade_classes = [c for c in self.classes if c.get("Grade", "") == self.grade_var.get()]
        self.grade_list.delete(0, "end")
        for classroom in self.grade_classes:
            self.grade_list.insert("end", classroom.get("Name", ""))

    def refresh_all(self):
        query = self.search_var.get().strip().lower()
        self.all_classes = [c for c in self.classes if query in f"{c.get('Grade', '')} {c.get('Name', '')}".lower()]
        self.all_list.delete(0, "end")
        for classroom in self.all_classes:
            self.all_list.insert("end", f"{classroom.get('Grade', '')} · {classroom.get('Name', '')}")

    def enter_selected(self, listbox: tk.Listbox, classes: list[dict]):
        selected = listbox.curselection()
        if selected:
            self.enter_class(classes[selected[0]])

    def enter_class(self, classroom: dict | None):
        if classroom:
            self.destroy()
            self.app.enter_selected_class(classroom)

    def create_class(self):
        before = len(self.app.store.data["Classes"])
        self.app.new_class()
        if len(self.app.store.data["Classes"]) > before:
            self.destroy()
            self.app.show_draw()


class HistoryWindow(tk.Toplevel):
    def __init__(self, app: PickerApp, classroom: dict):
        super().__init__(app)
        self.classroom = classroom
        self.title(f"更多历史 · {classroom.get('Grade', '')} · {classroom.get('Name', '')}")
        self.geometry("980x650")
        self.minsize(750, 480)
        self.transient(app)
        self.grab_set()
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{classroom.get('Grade', '')} · {classroom.get('Name', '')} · 全部历史",
                  font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w", pady=(0, 9))
        columns = ("time", "mode", "round", "count", "preview")
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings")
        self.tree.heading("#0", text="日期 / 批次")
        self.tree.column("#0", width=205)
        for key, title, width in (("time", "时刻", 95), ("mode", "模式", 85), ("round", "轮", 65),
                                  ("count", "人数", 65), ("preview", "结果预览", 300)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width)
        vertical = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.detail = tk.Text(frame, height=10, wrap="word", bg="#f8fafc", bd=0, padx=9, pady=7)
        self.detail.pack(fill="x", pady=(9, 0))
        self.detail.configure(state="disabled")
        self.items: dict[str, dict] = {}
        dates: dict[str, str] = {}
        for batch in reversed(classroom["Batches"]):
            moment = core.parse_date(batch.get("Time")) or core.now()
            day = moment.strftime("%Y-%m-%d")
            if day not in dates:
                dates[day] = self.tree.insert("", "end", text=f"——{moment.year % 100:02d}年{moment.month:02d}月{moment.day:02d}日——", open=True)
            valid = [e for e in batch["Entries"] if e.get("Valid")]
            names = [batch_name(classroom, e).split("（")[0] for e in valid]
            preview = "、".join(names[:2]) + (f" 等{len(names)}人" if len(names) > 2 else "")
            item = self.tree.insert(dates[day], "end", text="批次", values=(moment.strftime("%H:%M:%S"),
                                    batch.get("Mode", ""), batch.get("Round", 1),
                                    f"{len(valid)}/{batch.get('Count', 0)}", preview))
            self.items[item] = batch
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)
        if self.items:
            self.tree.selection_set(next(iter(self.items)))
            self.show_detail()
        else:
            self.set_detail("暂无点名记录。")

    def set_detail(self, value: str):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", value)
        self.detail.configure(state="disabled")

    def show_detail(self, _event=None):
        selected = self.tree.selection()
        batch = self.items.get(selected[0]) if selected else None
        if batch:
            self.set_detail(batch_detail_text(self.classroom, batch))


class GlobalSettingsWindow(tk.Toplevel):
    def __init__(self, app: PickerApp):
        super().__init__(app)
        self.app = app
        self.title("设置 · 选择班级")
        self.geometry("620x480")
        self.transient(app)
        self.grab_set()
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="选择要管理的班级", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(0, 8))
        self.classes = sorted(app.store.data["Classes"], key=lambda c: (c.get("Grade", ""), c.get("Name", "")))
        self.class_var = tk.StringVar()
        self.combo = ttk.Combobox(frame, textvariable=self.class_var,
                                  values=[f"{c.get('Grade', '')} · {c.get('Name', '')}" for c in self.classes],
                                  state="readonly")
        self.combo.pack(fill="x", pady=(0, 18))
        if self.classes:
            self.combo.current(self.classes.index(app.classroom) if app.classroom in self.classes else 0)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="抽取设置", command=lambda: self.open_target(SettingsWindow)).pack(side="left", padx=3)
        ttk.Button(row, text="名单管理", command=lambda: self.open_target(ManagerWindow)).pack(side="left", padx=3)
        ttk.Button(row, text="查看更多历史", command=lambda: self.open_target(HistoryWindow)).pack(side="left", padx=3)
        ttk.Button(frame, text="新建班级", command=self.create_class).pack(anchor="w", pady=(18, 0))
        ttk.Separator(frame).pack(fill="x", pady=16)
        ttk.Label(frame, text="本地数据保护", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", pady=(0, 8))
        protected = ttk.Frame(frame)
        protected.pack(fill="x")
        ttk.Button(protected, text="一键重置…", command=self.open_reset).pack(side="left", padx=(0, 7))
        ttk.Button(protected, text="修改保护密码", command=self.open_password_change).pack(side="left", padx=7)
        ttk.Button(protected, text="恢复本地备份", command=self.open_restore).pack(side="left", padx=7)
        ttk.Label(frame, text="密码初始为 admin；密码和备份保存在当前数据目录。",
                  foreground="#52667a").pack(anchor="w", pady=(10, 0))
        ttk.Separator(frame).pack(fill="x", pady=13)
        ttk.Label(frame, text="数据保存位置", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        self.location = ttk.Label(frame, text=str(app.store.path.parent), wraplength=570)
        self.location.pack(anchor="w", fill="x", pady=(5, 8))
        ttk.Button(frame, text="更改保存位置…", command=self.change_location).pack(anchor="w")

    def selected_class(self) -> dict | None:
        index = self.combo.current()
        return self.classes[index] if 0 <= index < len(self.classes) else None

    def open_target(self, window_type):
        classroom = self.selected_class()
        if classroom and self.app.can_edit():
            self.destroy()
            window_type(self.app, classroom)

    def create_class(self):
        before = len(self.app.store.data["Classes"])
        self.app.new_class()
        if len(self.app.store.data["Classes"]) > before:
            self.destroy()
            self.app.show_draw()

    def open_reset(self):
        classroom = self.selected_class()
        self.destroy()
        ResetWindow(self.app, classroom)

    def open_password_change(self):
        self.destroy()
        ChangePasswordWindow(self.app)

    def open_restore(self):
        self.destroy()
        RestoreBackupWindow(self.app)

    def change_location(self):
        if not self.app.can_edit():
            return
        selected = filedialog.askdirectory(parent=self, title="选择新的空数据文件夹", mustexist=True)
        if not selected:
            return
        target = Path(selected).resolve()
        source = self.app.store.path.parent.resolve()
        if target == source:
            messagebox.showinfo("保存位置未改变", "所选文件夹已经是当前数据目录。", parent=self)
            return
        if not messagebox.askyesno(
            "确认更改保存位置",
            f"将当前数据、保护密码和本地备份复制到：\n{target}\n\n"
            f"原文件夹 {source} 会保留。新位置须为空文件夹；以后程序将从新位置读取。确认继续吗？",
            parent=self,
        ):
            return
        if not self.app.store.save():
            messagebox.showerror("保存失败", "当前数据无法写入原位置，迁移已取消。\n" + str(self.app.store.last_error), parent=self)
            return
        try:
            storage.migrate_directory(app_directory(), source, target)
            self.app.store = core.DataStore(target)
            self.app.maintenance = maintenance.LocalMaintenance(self.app.store)
            self.app.after_storage_change()
        except Exception as exc:
            messagebox.showerror("更改保存位置失败", f"{exc}\n\n原位置的数据仍保留。", parent=self)
            return
        self.location.configure(text=str(target))
        messagebox.showinfo("保存位置已更改", f"以后数据保存在：\n{target}\n\n原文件夹仍保留，可自行核对。", parent=self)


class SettingsWindow(tk.Toplevel):
    def __init__(self, app: PickerApp, classroom: dict):
        super().__init__(app)
        self.app, self.classroom = app, classroom
        self.title(f"{classroom.get('Name')} — 抽取设置")
        self.geometry("620x600")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        self.vip = tk.BooleanVar(value=classroom.get("VipEnabled", False))
        self.fill = tk.BooleanVar(value=classroom.get("FillVipShortage", True))
        self.random_vip = tk.BooleanVar(value=classroom.get("VipRandomForGroups", False))
        self.keep = tk.BooleanVar(value=classroom.get("KeepAbsenceOnRestart", True))
        self.quota = tk.StringVar(value=str(classroom.get("VipPerBatch", 1)))
        self.base = tk.StringVar(value=str(classroom.get("BaseWeight", 1)))
        self.growth = tk.StringVar(value=str(classroom.get("Growth", 0.05)))
        self.max_weight = tk.StringVar(value=str(classroom.get("MaxWeight", 2)))
        self.add_toggle(frame, "启用VIP安排", self.vip)
        quota_row = ttk.Frame(frame)
        quota_row.pack(fill="x", pady=5)
        ttk.Label(quota_row, text="每批VIP人数").pack(side="left")
        ttk.Spinbox(quota_row, from_=0, to=999, textvariable=self.quota, width=8).pack(side="left", padx=12)
        self.add_toggle(frame, "VIP不足时用普通人员补齐", self.fill)
        ttk.Button(frame, text="ⓘ 查看补齐规则", command=self.show_fill_info).pack(anchor="w", pady=(1, 7))
        self.add_toggle(frame, "多人VIP随机抽取（关闭则按队列）", self.random_vip)
        self.add_toggle(frame, "重开后保留临时缺席", self.keep)
        ttk.Separator(frame).pack(fill="x", pady=13)
        ttk.Label(frame, text="均衡模式权重", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        for title, variable in (("基础权重", self.base), ("每批未中增长", self.growth), ("权重上限", self.max_weight)):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=title, width=16).pack(side="left")
            ttk.Entry(row, textvariable=variable, width=12).pack(side="left")
        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=18)
        ttk.Button(footer, text="查看更多历史", command=self.open_history).pack(side="left")
        ttk.Button(footer, text="一键重置…", command=self.open_reset).pack(side="left", padx=8)
        ttk.Button(footer, text="预览并保存", style="Accent.TButton", command=self.save).pack(side="right")

    def add_toggle(self, parent, label: str, variable: tk.BooleanVar):
        button = ttk.Button(parent)
        def redraw(*_):
            button.configure(text=("✔  " if variable.get() else "□  ") + label)
        button.configure(command=lambda: variable.set(not variable.get()))
        variable.trace_add("write", redraw)
        redraw()
        button.pack(anchor="w", pady=3)

    def open_history(self):
        window = HistoryWindow(self.app, self.classroom)
        self.wait_window(window)
        if self.winfo_exists():
            self.grab_set()

    def open_reset(self):
        self.destroy()
        ResetWindow(self.app, self.classroom)

    def show_fill_info(self):
        messagebox.showinfo("VIP不足时用普通人员补齐",
                            "关闭：多人抽取时VIP人数须达到设置值，不足则提示处理。\n"
                            "开启：先抽可参与VIP，缺少名额由普通池补齐。补位者仍是普通身份，不完成VIP任务。\n"
                            "合格总人数不足时仍不可抽取；缺席后的补抽沿用本批开关。单人始终按队列优先。", parent=self)

    def save(self):
        if not self.app.can_edit():
            return
        try:
            quota = int(self.quota.get())
            base, growth, maximum = float(self.base.get()), float(self.growth.get()), float(self.max_weight.get())
            if quota < 0 or not all(math.isfinite(x) for x in (base, growth, maximum)) or base <= 0 or growth < 0 or maximum < base:
                raise ValueError
        except ValueError:
            messagebox.showwarning("设置无效", "VIP人数须非负；基础权重大于0，增长非负，上限不低于基础。", parent=self)
            return
        classroom = self.classroom
        changed = any((classroom.get("BaseWeight", 1) != base, classroom.get("Growth", 0.05) != growth,
                       classroom.get("MaxWeight", 2) != maximum))
        if changed:
            preview = []
            for student in classroom["Students"][:12]:
                old = core.weight(classroom, student)
                new = min(maximum, base + growth * student.get("WaitCount", 0))
                preview.append(f"{student['Name']}：{old:.2f} → {new:.2f}" + ("（缺席中）" if core.is_absent(student) else ""))
            message = "按有效等待次数重算权重，历史结果不变。缺席学生也按新参数重算。\n\n" + "\n".join(preview)
            if not messagebox.askyesno("确认权重变化", message, parent=self):
                return
        classroom.update({"VipEnabled": self.vip.get(), "VipPerBatch": quota, "FillVipShortage": self.fill.get(),
                          "VipRandomForGroups": self.random_vip.get(), "KeepAbsenceOnRestart": self.keep.get(),
                          "BaseWeight": base, "Growth": growth, "MaxWeight": maximum})
        self.app.commit()
        self.destroy()


class ResetWindow(tk.Toplevel):
    def __init__(self, app: PickerApp, preferred_classroom: dict | None = None):
        super().__init__(app)
        self.app = app
        self.title("一键重置 · 选择范围和内容")
        self.geometry("630x520")
        self.minsize(520, 360)
        self.transient(app)
        self.grab_set()
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        footer = ttk.Frame(outer)
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)
        canvas = tk.Canvas(content, bg="#f2f6fb", bd=0, highlightthickness=0)
        scroll = ttk.Scrollbar(content, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        frame = ttk.Frame(canvas, padding=(6, 4, 12, 4))
        canvas_window = canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(canvas_window, width=e.width))
        ttk.Label(frame, text="一键重置", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Label(frame, text="先选择范围与内容；下一步会显示影响、要求确认并输入保护密码。",
                  foreground="#52667a").pack(anchor="w", pady=(0, 17))
        self.scope = tk.StringVar(value="class")
        scope_row = ttk.Frame(frame)
        scope_row.pack(fill="x")
        ttk.Radiobutton(scope_row, text="选中的班级", variable=self.scope, value="class",
                        command=self.scope_changed).pack(side="left", padx=(0, 18))
        ttk.Radiobutton(scope_row, text="全部班级", variable=self.scope, value="all",
                        command=self.scope_changed).pack(side="left")
        self.classes = sorted(app.store.data["Classes"], key=lambda c: (c.get("Grade", ""), c.get("Name", "")))
        self.class_var = tk.StringVar()
        self.combo = ttk.Combobox(frame, textvariable=self.class_var, state="readonly",
                                  values=[f"{c.get('Grade', '')} · {c.get('Name', '')}" for c in self.classes])
        self.combo.pack(fill="x", pady=(8, 20))
        if self.classes:
            index = self.classes.index(preferred_classroom) if preferred_classroom in self.classes else 0
            self.combo.current(index)
        ttk.Label(frame, text="选择要清除的内容", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", pady=(0, 8))
        self.options: dict[str, tk.BooleanVar] = {}
        for key, label in maintenance.OPTION_NAMES.items():
            variable = tk.BooleanVar(value=False)
            self.options[key] = variable
            self.add_toggle(frame, label, variable)
        ttk.Label(frame, text="清人员名单会连带清历史和进度；清历史会连带清进度。",
                  foreground="#a34b20").pack(anchor="w", pady=(14, 5))
        ttk.Label(frame, text="执行前自动留下完整本地备份；不上传、不联网。",
                  foreground="#52667a").pack(anchor="w")
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        self.next_button = ttk.Button(footer, text="下一步：确认清除", style="Accent.TButton",
                                      command=self.open_confirmation)
        self.next_button.pack(side="right")

    def add_toggle(self, parent, label: str, variable: tk.BooleanVar):
        button = ttk.Button(parent)
        def redraw(*_):
            button.configure(text=("✔  " if variable.get() else "□  ") + label)
        button.configure(command=lambda: variable.set(not variable.get()))
        variable.trace_add("write", redraw)
        redraw()
        button.pack(anchor="w", pady=3)

    def scope_changed(self):
        self.combo.configure(state="readonly" if self.scope.get() == "class" else "disabled")

    def open_confirmation(self):
        if not self.app.can_edit():
            return
        selected = self.combo.current()
        class_id = self.classes[selected]["Id"] if self.scope.get() == "class" and selected >= 0 else None
        options = {key for key, variable in self.options.items() if variable.get()}
        try:
            preview = maintenance.reset_preview(self.app.store.data, self.scope.get(), class_id, options)
        except ValueError as exc:
            messagebox.showwarning("无法继续", str(exc), parent=self)
            return
        dialog = ResetConfirmWindow(self, self.app, self.scope.get(), class_id, options, preview)
        self.wait_window(dialog)
        if self.winfo_exists():
            self.grab_set()


class ResetConfirmWindow(tk.Toplevel):
    def __init__(self, parent: ResetWindow, app: PickerApp, scope: str, class_id: str | None,
                 options: set[str], preview: str):
        super().__init__(parent)
        self.app, self.scope, self.class_id, self.options = app, scope, class_id, options
        self.title("二次确认 · 重置风险")
        self.geometry("650x500")
        self.minsize(550, 390)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="请核对重置范围和风险", font=("Microsoft YaHei UI", 16, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10))
        risk_frame = ttk.Frame(frame)
        risk_frame.grid(row=1, column=0, sticky="nsew")
        risk_frame.columnconfigure(0, weight=1)
        risk_frame.rowconfigure(0, weight=1)
        risk = tk.Text(risk_frame, height=5, wrap="word", bg="#fff8ef", fg="#793a19", bd=0, padx=12, pady=10)
        risk_scroll = ttk.Scrollbar(risk_frame, orient="vertical", command=risk.yview)
        risk.configure(yscrollcommand=risk_scroll.set)
        risk.grid(row=0, column=0, sticky="nsew")
        risk_scroll.grid(row=0, column=1, sticky="ns")
        risk.insert("1.0", preview)
        risk.configure(state="disabled")
        self.accept = tk.BooleanVar(value=False)
        accept_button = ttk.Button(frame)
        def redraw_accept(*_):
            accept_button.configure(text=("✔  " if self.accept.get() else "□  ") +
                                    "我已核对范围，并理解清除后需用本地备份恢复")
        accept_button.configure(command=lambda: self.accept.set(not self.accept.get()))
        self.accept.trace_add("write", redraw_accept)
        redraw_accept()
        accept_button.grid(row=2, column=0, sticky="w", pady=(13, 7))
        password_row = ttk.Frame(frame)
        password_row.grid(row=3, column=0, sticky="w")
        ttk.Label(password_row, text="保护密码").pack(side="left")
        self.password = ttk.Entry(password_row, show="*", width=25)
        self.password.pack(side="left", padx=10)
        ttk.Button(password_row, text="忘记密码", command=self.open_forgot).pack(side="left")
        ttk.Label(frame, text="首次使用的初始密码为 admin；修改后请输入新密码。",
                  foreground="#52667a").grid(row=4, column=0, sticky="w", pady=(7, 0))
        footer = ttk.Frame(frame)
        footer.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(footer, text="返回", command=self.destroy).pack(side="right", padx=(8, 0))
        self.confirm_button = ttk.Button(footer, text="确认清除", style="Accent.TButton", command=self.execute)
        self.confirm_button.pack(side="right")

    def execute(self):
        if not self.accept.get():
            messagebox.showwarning("请先确认", "请先勾选已核对范围和风险。", parent=self)
            return
        if not self.app.can_edit():
            return
        try:
            backup = self.app.maintenance.reset(self.scope, self.class_id, self.options,
                                                self.password.get())
        except Exception as exc:
            messagebox.showerror("重置未完成", str(exc), parent=self)
            return
        self.app.after_storage_change()
        self.master.destroy()
        messagebox.showinfo("重置完成", f"已完成重置。完整本地备份：\n{backup}", parent=self.app)

    def open_forgot(self):
        dialog = ForgotPasswordWindow(self, self.app, on_success=self.master.destroy)
        self.wait_window(dialog)
        if self.winfo_exists():
            self.grab_set()


class ForgotPasswordWindow(tk.Toplevel):
    PHRASE = "重置全部数据"

    def __init__(self, parent: tk.Toplevel, app: PickerApp, on_success):
        super().__init__(parent)
        self.app, self.on_success = app, on_success
        self.title("忘记密码 · 本地恢复")
        self.geometry("590x420")
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="忘记保护密码", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, text="此操作会先将全部班级数据写入当前数据目录的 backups，随后清空当前数据，"
                  "并把保护密码恢复为 admin。", wraplength=530,
                  foreground="#a12d20").pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, text="之后可以使用 admin，在“恢复本地备份”中取回数据。"
                  "恢复会覆盖恢复时的当前数据；请保管当前数据目录。",
                  wraplength=530).pack(anchor="w", pady=(0, 17))
        ttk.Label(frame, text=f"请输入“{self.PHRASE}”以继续：").pack(anchor="w")
        self.phrase = ttk.Entry(frame, width=30)
        self.phrase.pack(anchor="w", pady=(5, 15))
        footer = ttk.Frame(frame)
        footer.pack(fill="x")
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="备份后重置全部数据", command=self.execute).pack(side="right")

    def execute(self):
        if self.phrase.get().strip() != self.PHRASE:
            messagebox.showwarning("文字不匹配", "请输入完整的确认文字。", parent=self)
            return
        if not self.app.can_edit():
            return
        if not messagebox.askyesno("最后确认", "将备份全部当前数据，然后清空全部班级并重设保护密码。确认执行吗？", parent=self):
            return
        try:
            backup = self.app.maintenance.forget_password()
        except Exception as exc:
            messagebox.showerror("恢复失败", str(exc), parent=self)
            return
        self.app.after_storage_change()
        self.on_success()
        if self.winfo_exists():
            self.destroy()
        messagebox.showinfo("本地恢复完成", f"当前数据已清空，保护密码已恢复为 admin。\n完整备份：\n{backup}",
                            parent=self.app)


class ChangePasswordWindow(tk.Toplevel):
    def __init__(self, app: PickerApp):
        super().__init__(app)
        self.app = app
        self.title("修改本地保护密码")
        self.geometry("490x330")
        self.transient(app)
        self.grab_set()
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="修改保护密码", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w", pady=(0, 14))
        for label, attr in (("当前密码", "current"), ("新密码", "new"), ("再次输入新密码", "repeat")):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=label, width=17).pack(side="left")
            entry = ttk.Entry(row, show="*", width=28)
            entry.pack(side="left")
            setattr(self, attr, entry)
        ttk.Label(frame, text="密码仅在本地保存为加盐哈希；初始密码 admin。", foreground="#52667a").pack(anchor="w", pady=(12, 0))
        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=(13, 0))
        ttk.Button(footer, text="忘记密码", command=self.open_forgot).pack(side="left")
        ttk.Button(footer, text="保存新密码", style="Accent.TButton", command=self.save).pack(side="right")
        self.current.focus_set()

    def save(self):
        if self.new.get() != self.repeat.get():
            messagebox.showwarning("密码不一致", "两次输入的新密码不一致。", parent=self)
            return
        try:
            self.app.maintenance.protection.change_password(self.current.get(), self.new.get())
        except Exception as exc:
            messagebox.showerror("无法修改密码", str(exc), parent=self)
            return
        self.destroy()
        messagebox.showinfo("密码已更新", f"新保护密码已保存到：\n{self.app.store.path.parent}", parent=self.app)

    def open_forgot(self):
        dialog = ForgotPasswordWindow(self, self.app, on_success=self.destroy)
        self.wait_window(dialog)
        if self.winfo_exists():
            self.grab_set()


class RestoreBackupWindow(tk.Toplevel):
    def __init__(self, app: PickerApp):
        super().__init__(app)
        self.app = app
        self.title("恢复本地备份")
        self.geometry("680x470")
        self.transient(app)
        self.grab_set()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="恢复本地备份", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text="只读取当前数据目录 backups 中的备份。恢复前也会自动备份当前数据。",
                  foreground="#52667a").pack(anchor="w", pady=(0, 12))
        self.backups = app.maintenance.list_backups()
        self.listbox = tk.Listbox(frame, font=("Microsoft YaHei UI", 10), activestyle="none")
        self.listbox.pack(fill="both", expand=True)
        for path in self.backups:
            self.listbox.insert("end", path.name)
        if self.backups:
            self.listbox.selection_set(0)
        else:
            self.listbox.insert("end", "暂无本地备份")
        password_row = ttk.Frame(frame)
        password_row.pack(fill="x", pady=(12, 5))
        ttk.Label(password_row, text="保护密码").pack(side="left")
        self.password = ttk.Entry(password_row, show="*", width=25)
        self.password.pack(side="left", padx=9)
        ttk.Button(password_row, text="忘记密码", command=self.open_forgot).pack(side="left")
        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="确认恢复所选备份", style="Accent.TButton", command=self.restore).pack(side="right")

    def restore(self):
        selected = self.listbox.curselection()
        if not self.backups or not selected:
            messagebox.showwarning("没有备份", "请先选择一个本地备份。", parent=self)
            return
        if not self.app.can_edit():
            return
        backup = self.backups[selected[0]]
        if not messagebox.askyesno("确认恢复", f"将用以下备份覆盖当前全部班级数据：\n{backup.name}\n\n当前数据会先另存一份本地备份。确认继续吗？",
                                   parent=self):
            return
        try:
            previous = self.app.maintenance.restore(backup, self.password.get())
        except Exception as exc:
            messagebox.showerror("恢复未完成", str(exc), parent=self)
            return
        self.app.after_storage_change()
        self.destroy()
        messagebox.showinfo("恢复完成", f"数据已从本地备份恢复。恢复前的数据保存在：\n{previous}", parent=self.app)

    def open_forgot(self):
        dialog = ForgotPasswordWindow(self, self.app, on_success=self.destroy)
        self.wait_window(dialog)
        if self.winfo_exists():
            self.grab_set()


def main():
    if '--board-window' in sys.argv:
        from python_board_window import run_window
        index = sys.argv.index('--board-window')
        run_window(sys.argv[index + 1], sys.argv[index + 2])
        return
    checking = '--health-check' in sys.argv or '--window-health-check' in sys.argv
    temporary = tempfile.TemporaryDirectory(prefix="picker-health-") if checking else None
    app = PickerApp(Path(temporary.name) if temporary else None, board_first=not checking)
    if '--window-health-check' in sys.argv:
        import json
        app.primary_board = True; app._window_check = True
        try:
            sample_size = int(sys.argv[sys.argv.index('--sample-size') + 1]) if '--sample-size' in sys.argv else 50
            app.store.data['Classes'][0]['Students'] = app.store.data['Classes'][0]['Students'][:sample_size]
            app.update()
            assert app.home_page.winfo_ismapped() and app.board_window is None
            selector = StartWindow(app)
            selector.enter_class(app.store.data['Classes'][0])
            deadline = time.monotonic() + 40
            while app._page_ready is None and time.monotonic() < deadline:
                app.update(); time.sleep(.03)
                if app.board_window.process.poll() is not None:
                    raise RuntimeError(app.board_window.diagnostic())
            assert app._page_ready, f'3D page not ready: {app.board_server.last_rejection}; {app.board_window.diagnostic()}'
            assert app._page_ready['students'] == sample_size and app._page_ready['slots'] == sample_size + math.ceil(sample_size / 5)
            assert app._page_ready['backgroundLoaded'] and app._page_ready['backgroundTransparent'], 'Background must load behind the transparent 3D scene'
            assert app.state() == 'withdrawn'
            app.board_dispatch('native', {'action': 'board-fullscreen'})
            until = time.monotonic() + .35
            while time.monotonic() < until: app.update(); time.sleep(.02)
            assert app.board_window.alive()
            app.board_dispatch('native', {'action': 'board-fullscreen'})
            until = time.monotonic() + .35
            while time.monotonic() < until: app.update(); time.sleep(.02)
            assert app.board_window.alive()
            app.board_dispatch('native', {'action': 'original'}); app.update()
            assert app.state() != 'withdrawn'
            pid = app.board_window.process.pid
            app.open_board(); app.update()
            assert app.state() == 'withdrawn' and app.board_window.process.pid == pid
            report = {'ready': app._page_ready, 'request': app.board_server.last_request,
                      'startBeforeClassSelection': True, 'nativeFullscreenToggle': True,
                      'originalInterfaceEntry': True, 'returnToBoard': True, 'showPreservesWindowState': True}
            if '--report' in sys.argv:
                Path(sys.argv[sys.argv.index('--report') + 1]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            if app.board_window:
                app.board_window.close()
                app.board_window.process.wait(timeout=15)
            if app.board_server: app.board_server.stop()
            app.destroy(); temporary.cleanup()
        return
    if "--health-check" in sys.argv:
        app.withdraw()
        app.update_idletasks()
        assert app.bind("<Escape>")
        app.toggle_fullscreen()
        app.exit_fullscreen()
        assert not app._fullscreen
        StartWindow(app).destroy()
        GlobalSettingsWindow(app).destroy()
        reset_window = ResetWindow(app, app.store.data["Classes"][0] if app.store.data["Classes"] else None)
        confirm_window = ResetConfirmWindow(reset_window, app, "all", None, {"results"}, "只读界面检查")
        ForgotPasswordWindow(confirm_window, app, on_success=lambda: None).destroy()
        confirm_window.destroy()
        reset_window.destroy()
        password_window = ChangePasswordWindow(app)
        for entry in (password_window.current, password_window.new, password_window.repeat):
            assert entry.master is not password_window
            entry.insert(0, "test")
            assert entry.get() == "test"
        password_window.destroy()
        RestoreBackupWindow(app).destroy()
        if app.store.data["Classes"]:
            app.enter_class(app.store.data["Classes"][0])
            assert app.displayed_batch_id is None
            with patch.object(app, "show_board_window"):
                app.open_board()
            from urllib.request import urlopen
            with urlopen(app.board_server.url, timeout=5) as response:
                assert "V1.0" in response.read().decode("utf-8")
            state = app.board_dispatch("state", {})
            assert state["total"] == 50 and len(state["slots"]) == 60
            drawn = app.board_dispatch("draw", {"layoutId": state["layoutId"], "position": state["position"], "count": 1})
            assert 1 <= drawn["batch"]["BoardRolls"][0]["steps"] <= 6
            assert drawn["batch"]["BoardRolls"][0]["kind"] == "chest"
            assert not core.missing_positions(drawn["batch"])
            assert app.displayed_batch_id is None
            app.board_dispatch("presented", {"batchId": drawn["batch"]["Id"]})
            assert app.displayed_batch_id == drawn["batch"]["Id"]
            app.board_server.stop()
            ManagerWindow(app, app.classroom).destroy()
            SettingsWindow(app, app.classroom).destroy()
            HistoryWindow(app, app.classroom).destroy()
            for heading in app.history.get_children():
                assert app.history.item(heading, "text").startswith("——")
            app.toggle_history()
            assert not app.history_visible and app.detail_visible
            assert str(app.detail_section) in app.right_split.panes()
            app.toggle_history()
            app.toggle_detail()
            assert app.history_visible and not app.detail_visible
            assert str(app.history_section) in app.right_split.panes()
            app.toggle_history()
            assert str(app.history_panel) not in app.body.panes()
            app.toggle_detail()
            assert str(app.history_panel) in app.body.panes()
            app.toggle_history()
            app.clear_result_display()
            app.geometry("980x560")
            app.attributes("-alpha", 0)
            app.deiconify()
            app.update()
            assert app.actions.winfo_ismapped()
            assert app.actions.winfo_rooty() + app.actions.winfo_height() <= app.winfo_rooty() + app.winfo_height()
            assert app.actions.winfo_rooty() >= app.body.winfo_rooty() + app.body.winfo_height()
            assert len(app.right_split.panes()) == 2
            assert 0 < app.right_split.sashpos(0) < app.right_split.winfo_height()
            for button in (app.draw_button, app.clear_button, app.replace_button, app.close_batch_button, app.return_button):
                assert button.winfo_ismapped()
                assert button.winfo_rootx() + button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
            assert app.board_button.winfo_ismapped()
            assert app.board_button.winfo_rootx() + app.board_button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
            app.return_button.invoke()
            app.update_idletasks()
            assert app.home_page.winfo_ismapped() and not app.draw_page.winfo_ismapped()
            reset_layout = ResetWindow(app, app.store.data["Classes"][0])
            reset_layout.attributes("-alpha", 0)
            reset_layout.update()
            assert reset_layout.next_button.winfo_ismapped()
            assert (reset_layout.next_button.winfo_rooty() + reset_layout.next_button.winfo_height()
                    <= reset_layout.winfo_rooty() + reset_layout.winfo_height())
            confirm_layout = ResetConfirmWindow(reset_layout, app, "all", None, {"results"}, "只读布局检查")
            confirm_layout.attributes("-alpha", 0)
            confirm_layout.update()
            assert confirm_layout.confirm_button.winfo_ismapped()
            assert (confirm_layout.confirm_button.winfo_rooty() + confirm_layout.confirm_button.winfo_height()
                    <= confirm_layout.winfo_rooty() + confirm_layout.winfo_height())
            confirm_layout.destroy()
            reset_layout.destroy()
        sample = core.new_class("健康检查", "临时班")
        sample["Students"] = [core.new_student("甲"), core.new_student("乙")]
        app.classroom = sample
        app.mode_var.set("普通")
        app.count_var.set("2")
        app.show_draw()
        app.refresh_buttons()
        app.update()
        assert app.draw_button.instate(["!disabled"])
        sample["FillVipShortage"] = False
        app.refresh_buttons()
        assert app.draw_button.instate(["disabled"])
        with patch.object(messagebox, "askyesno", return_value=True) as ask, \
                patch.object(app, "open_settings") as open_settings:
            app.draw_button.event_generate("<Button-1>")
            ask.assert_called_once()
            open_settings.assert_called_once()
        with patch.object(messagebox, "askyesno", return_value=False) as ask, \
                patch.object(app, "open_settings") as open_settings:
            app.draw_button.event_generate("<Button-1>")
            ask.assert_called_once()
            open_settings.assert_not_called()
        app.destroy()
        temporary.cleanup()
        return
    app.mainloop()


if __name__ == "__main__":
    main()
