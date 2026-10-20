"""Run with python -m echokeys on Windows."""
import sys


def main():
    if sys.platform != 'win32':
        print('EchoKeys 录制与回放仅支持 Windows。请在 Windows 上运行，详见 README.md。', file=sys.stderr)
        return 1
    # Enable physical pixel coordinates before creating listeners or widgets.
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        ctypes.windll.user32.MessageBoxW(None, '请安装包含 Tcl/Tk 的 Python，然后重新启动 EchoKeys。', 'EchoKeys', 0x10)
        return 1
    root = tk.Tk()
    root.withdraw()
    try:
        from .input_backend import InputBackend
        from .app import App
        app = App(root, InputBackend())
    except Exception as exc:
        messagebox.showerror('EchoKeys 启动失败', f'{exc}\n请检查是否已安装 requirements.txt 中的依赖。', parent=root)
        root.destroy()
        return 1
    root.deiconify()
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
