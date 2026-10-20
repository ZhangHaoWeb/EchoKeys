"""Chinese desktop UI. All Tk operations run on the main thread."""
import queue
import threading
from .engine import Engine
from .model import parse_settings
from .storage import Task, default_path, load_task, save_task


STATUS = {'empty': '待录制', 'ready': '待回放', 'recording': '录制中',
          'countdown': '准备开始', 'playing': '循环回放中', 'waiting': '循环等待中'}


class App:
    def __init__(self, root, backend, path=None):
        import tkinter as tk
        from tkinter import ttk, messagebox
        self.root, self.backend, self.dialogs = root, backend, messagebox
        self.engine = Engine(backend)
        self.path = path or default_path()
        self._healthy = False
        self._failed = False
        self._closing = False
        self._dirty = False
        self._load_error = None
        self.count, self.interval = tk.StringVar(value='1'), tk.StringVar(value='1')
        self.status = tk.StringVar(value='正在连接全局输入监听…')
        self.detail = tk.StringVar(value='准备好后即可录制操作')
        self.duration = tk.StringVar(value='00:00.0')
        self.progress = tk.StringVar(value='— / —')
        self.saved_text = tk.StringVar(value='当前任务尚未保存')
        self._build(tk, ttk)
        self._restore()
        self.count.trace_add('write', self._mark_dirty)
        self.interval.trace_add('write', self._mark_dirty)
        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self.root.bind('<Escape>', lambda event: self.engine.stop())
        self._update_controls()
        threading.Thread(target=self._connect, daemon=True).start()
        self.root.after(50, self._poll)

    def _build(self, tk, ttk):
        self.root.title('EchoKeys · 操作录制与回放')
        self.root.geometry('760x690')
        self.root.minsize(720, 670)
        self.root.configure(bg='#f3f5f9')
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#f3f5f9')
        style.configure('TLabel', background='#f3f5f9', foreground='#243047')
        style.configure('Muted.TLabel', foreground='#69758a')
        style.configure('Title.TLabel', font=('Segoe UI', 28, 'bold'))
        style.configure('TButton', padding=(18, 12), background='#e7ebf2', borderwidth=0)
        style.map('TButton', background=[('active', '#d9e0eb')], foreground=[('disabled', '#9ca5b4')])
        style.configure('Accent.TButton', background='#315fea', foreground='white')
        style.map('Accent.TButton', background=[('disabled', '#d8dfee'), ('active', '#244bd0')], foreground=[('disabled', '#8492b0')])
        style.configure('TEntry', padding=8, fieldbackground='white')
        outer = ttk.Frame(self.root, padding=30)
        outer.pack(fill='both', expand=True)
        header = ttk.Frame(outer)
        header.pack(fill='x')
        ttk.Label(header, text='EchoKeys', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='WINDOWS  /  v0.1', style='Muted.TLabel').pack(side='right', pady=(10, 0))
        ttk.Label(outer, text='录制一次，让重复操作自动完成。', style='Muted.TLabel').pack(anchor='w', pady=(4, 22))
        card = tk.Frame(outer, background='#15233b', padx=24, pady=20)
        card.pack(fill='x')
        tk.Label(card, text='当前状态', font=('Microsoft YaHei UI', 10), fg='#a6b5cf', bg='#15233b').pack(anchor='w')
        tk.Label(card, textvariable=self.status, font=('Microsoft YaHei UI', 23, 'bold'), fg='white', bg='#15233b').pack(anchor='w', pady=(6, 3))
        tk.Label(card, textvariable=self.detail, font=('Microsoft YaHei UI', 10), fg='#a6b5cf', bg='#15233b').pack(anchor='w')
        metrics = ttk.Frame(outer)
        metrics.pack(fill='x', pady=20)
        for title, variable in [('录制时长', self.duration), ('回放轮次', self.progress)]:
            group = ttk.Frame(metrics)
            group.pack(side='left', fill='x', expand=True)
            ttk.Label(group, text=title, style='Muted.TLabel').pack(anchor='w')
            ttk.Label(group, textvariable=variable, font=('Segoe UI', 22, 'bold')).pack(anchor='w', pady=(3, 0))
        actions = ttk.Frame(outer)
        actions.pack(fill='x')
        actions.columnconfigure((0, 1, 2), weight=1)
        self.record_button = ttk.Button(actions, text='●  开始录制', command=self._record, style='Accent.TButton')
        self.test_button = ttk.Button(actions, text='▷  单次测试回放', command=lambda: self._play(True))
        self.play_button = ttk.Button(actions, text='▶  开始循环回放', command=lambda: self._play(False), style='Accent.TButton')
        for column, button in enumerate((self.record_button, self.test_button, self.play_button)):
            button.grid(row=0, column=column, sticky='ew', padx=(0 if column == 0 else 6, 0))
        ttk.Label(outer, text='每次启动前均有 3 秒倒计时，请切换到目标窗口。', style='Muted.TLabel').pack(anchor='w', pady=(10, 18))
        settings = ttk.Frame(outer)
        settings.pack(fill='x')
        ttk.Label(settings, text='循环次数').grid(row=0, column=0, sticky='w')
        ttk.Label(settings, text='循环间隔（秒）').grid(row=0, column=1, sticky='w')
        settings.columnconfigure((0, 1), weight=1)
        self.count_entry = ttk.Entry(settings, textvariable=self.count)
        self.interval_entry = ttk.Entry(settings, textvariable=self.interval)
        self.count_entry.grid(row=1, column=0, sticky='ew', padx=(0, 12), pady=(6, 0))
        self.interval_entry.grid(row=1, column=1, sticky='ew', pady=(6, 0))
        ttk.Label(outer, text='间隔仅发生在两轮之间；最后一轮结束后直接停止。', style='Muted.TLabel').pack(anchor='w', pady=(8, 18))
        footer = ttk.Frame(outer)
        footer.pack(fill='x')
        self.save_button = ttk.Button(footer, text='保存任务', command=self._save)
        self.save_button.pack(side='left')
        self.stop_button = ttk.Button(footer, text='停止  Esc', command=self.engine.stop)
        self.stop_button.pack(side='right')
        ttk.Label(outer, textvariable=self.saved_text, style='Muted.TLabel').pack(anchor='w', pady=(8, 14))
        ttk.Separator(outer).pack(fill='x')
        ttk.Label(outer, text='按 ESC 随时停止', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', pady=(12, 5))
        ttk.Label(outer, text='回放前保持窗口位置、分辨率与缩放一致。不支持拖拽和滚轮。', style='Muted.TLabel').pack(anchor='w')
        # Font metrics differ by OS and DPI; reserve the actual requested height.
        self.root.update_idletasks()
        height = max(690, outer.winfo_reqheight())
        width = max(760, outer.winfo_reqwidth())
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(width, height)

    def _connect(self):
        try:
            self.backend.start(self.engine.capture, self.engine.stop, self.engine.fail)
            self.engine.messages.put(('backend_ready',))
        except Exception as exc:
            self.engine.fail(f'无法启动全局输入监听：{exc}')

    def _restore(self):
        try:
            task = load_task(self.path)
            if task is not None:
                self.engine.recording = task.recording
                self.engine.state = 'ready' if task.recording.events else 'empty'
                self.count.set(str(task.count))
                self.interval.set(str(task.interval))
                self.saved_text.set('已恢复本地任务 · 不会自动执行')
        except (OSError, ValueError) as exc:
            self._load_error = str(exc)
            self.saved_text.set('本地任务无法恢复，可重新录制')

    def _mark_dirty(self, *args):
        self._dirty = True
        self.saved_text.set('有未保存的修改 · 点击「保存任务」保存在本机')

    def _record(self):
        if not self._healthy or self._closing or self.engine.busy:
            return
        if self.engine.recording.events and not self.dialogs.askyesno('覆盖当前录制？', '新录制开始时将替换当前记录。\n若在倒计时期间按 ESC 取消，仍保留旧记录。', parent=self.root):
            return
        try:
            self.engine.start_recording()
        except (RuntimeError, ValueError) as exc:
            self.dialogs.showerror('无法录制', str(exc), parent=self.root)
        self._update_controls()

    def _play(self, test):
        if not self._healthy or self._closing or self.engine.busy:
            return
        try:
            if test:
                self.engine.start_playback(test=True)
            else:
                count, interval = parse_settings(self.count.get(), self.interval.get())
                self.engine.start_playback(count=count, interval=interval)
        except (RuntimeError, ValueError) as exc:
            self.dialogs.showerror('无法开始回放', str(exc), parent=self.root)
        self._update_controls()

    def _save(self):
        if self.engine.busy:
            return False
        try:
            count, interval = parse_settings(self.count.get(), self.interval.get())
            save_task(self.path, Task(self.engine.recording, count, interval))
            self._dirty = False
            self.saved_text.set('任务已保存到本机 · 下次启动自动恢复')
            return True
        except (OSError, ValueError) as exc:
            self.dialogs.showerror('保存失败', str(exc), parent=self.root)
            return False

    def _update_controls(self):
        idle = not self.engine.busy and not self._closing
        start = idle and self._healthy
        has_recording = bool(self.engine.recording.events)
        for widget, enabled in ((self.record_button, start), (self.test_button, start and has_recording),
                                (self.play_button, start and has_recording), (self.save_button, idle),
                                (self.count_entry, idle), (self.interval_entry, idle),
                                (self.stop_button, self.engine.busy and not self._closing)):
            widget.configure(state='normal' if enabled else 'disabled')

    @staticmethod
    def _format_time(seconds):
        return f'{int(seconds // 60):02d}:{seconds % 60:04.1f}'

    def _poll(self):
        try:
            while True:
                message = self.engine.messages.get_nowait()
                kind = message[0]
                if kind == 'backend_ready':
                    if self._failed:
                        continue
                    self._healthy = True
                    self.status.set(STATUS[self.engine.state])
                    self.detail.set('录制操作，测试确认，再设置循环执行')
                elif kind == 'state':
                    _, state, current, total = message
                    if self._healthy:
                        self.status.set('测试中' if state == 'playing' and self.engine.testing else STATUS[state])
                    self.progress.set(f'{current} / {total}' if total else '— / —')
                    if state == 'recording':
                        self.detail.set('正在记录鼠标与键盘操作，按 ESC 结束录制')
                    elif state == 'playing':
                        self.detail.set('正在按原始速度执行，按 ESC 可立即停止')
                    elif state == 'waiting':
                        self.detail.set('本轮已完成，等待下一轮 · 按 ESC 可停止')
                elif kind == 'countdown':
                    _, seconds, action = message
                    self.status.set(f'{seconds} 秒后开始' + ('录制' if action == 'record' else '测试' if action == 'test' else '回放'))
                    self.detail.set('请切换到目标窗口 · 按 ESC 取消')
                elif kind == 'recorded':
                    self._mark_dirty()
                elif kind == 'finished':
                    self.detail.set('已停止，录制内容已保留' if message[1] else '执行完成')
                elif kind in ('error', 'fatal'):
                    if kind == 'fatal':
                        if self._failed:
                            continue
                        self._failed = True
                        self._healthy = False
                        self.status.set('输入监听不可用')
                    self.dialogs.showerror('EchoKeys', message[1], parent=self.root)
        except queue.Empty:
            pass
        self.duration.set(self._format_time(self.engine.elapsed))
        self._update_controls()
        if self._load_error is not None:
            error, self._load_error = self._load_error, None
            self.dialogs.showwarning('本地任务未恢复', error, parent=self.root)
        if self._closing and not self.engine.busy:
            self._finish_close()
            return
        self.root.after(50, self._poll)

    def _close(self):
        self._closing = True
        self.engine.stop()
        self._update_controls()

    def _finish_close(self):
        if self._dirty:
            answer = self.dialogs.askyesnocancel('保存当前任务？', '关闭前是否保存录制内容及循环设置到本机？', parent=self.root)
            if answer is None or (answer and not self._save()):
                self._closing = False
                self.root.after(50, self._poll)
                return
        try:
            self.backend.close()
        except Exception as exc:
            self._healthy = False
            self._failed = True
            self.status.set('输入释放失败')
            self.detail.set('请再次关闭窗口重试释放输入')
            self.dialogs.showerror('输入释放失败', str(exc), parent=self.root)
            self._closing = False
            self.root.after(50, self._poll)
            return
        self.root.destroy()
