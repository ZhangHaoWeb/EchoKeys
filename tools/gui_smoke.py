"""Optional desktop smoke test; uses no real input hooks or injection."""
import argparse
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from echokeys.app import App
from echokeys.storage import load_task


class PreviewBackend:
    def start(self, on_input, on_stop, on_error):
        pass
    def send(self, event):
        pass
    def release_all(self):
        pass
    def close(self):
        pass


def pump(root, condition=lambda: False, timeout=.25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        root.update()
        if condition():
            return
        time.sleep(.005)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--screenshot')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        root = tk.Tk()
        app = App(root, PreviewBackend(), Path(folder) / 'task.json')
        errors = []
        root.report_callback_exception = lambda *exc: errors.append(str(exc))
        pump(root, lambda: app._healthy)
        assert app._healthy
        assert str(app.record_button['state']) == 'normal'
        assert str(app.test_button['state']) == 'disabled'
        app.engine._countdown = 0
        app._record()
        pump(root, lambda: app.engine.state == 'recording')
        app.engine.capture('move', (20, 30))
        app.engine.capture('key_down', ('vk:65',))
        app.engine.capture('key_up', ('vk:65',))
        app.engine.stop()
        app.engine.join(1)
        pump(root)
        app.count.set('3')
        app.interval.set('0.25')
        assert app._save()
        saved = load_task(app.path)
        assert saved.count == 3 and saved.interval == .25
        assert len(saved.recording.events) == 3
        app._play(True)
        app.engine.join(1)
        pump(root)
        assert not app.engine.busy
        assert str(app.test_button['state']) == 'normal'
        root.update_idletasks()
        prompts = [widget for widget in descendants(root) if widget.winfo_class() == 'TLabel' and widget.cget('text') == '按 ESC 随时停止']
        assert len(prompts) == 1 and prompts[0].winfo_ismapped(), 'Fixed ESC hint is clipped'
        bottom = max(widget.winfo_rooty() + widget.winfo_height() for widget in descendants(root) if widget.winfo_ismapped())
        assert bottom <= root.winfo_rooty() + root.winfo_height(), f'Content clipped: {bottom} > {root.winfo_rooty() + root.winfo_height()}'
        assert not errors, errors
        if args.screenshot:
            if sys.platform == 'darwin':
                import subprocess
                root.lift()
                pump(root)
                rectangle = f'{root.winfo_rootx()},{root.winfo_rooty()},{root.winfo_width()},{root.winfo_height()}'
                subprocess.run(['screencapture', '-x', '-R', rectangle, args.screenshot], check=True)
        app._close()
        app._finish_close()
        print('GUI smoke PASS: window layout, controls, recording, test playback, local save and close; no real input injection.')


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


if __name__ == '__main__':
    main()
