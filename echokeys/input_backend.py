"""pynput bridge. Imported lazily so tests never install global hooks."""
import threading
from .model import valid_key


class InputBackend:
    def __init__(self, keyboard_module=None, mouse_module=None):
        if keyboard_module is None:
            from pynput import keyboard as keyboard_module, mouse as mouse_module
        self.keyboard_module, self.mouse_module = keyboard_module, mouse_module
        self.keyboard = keyboard_module.Controller()
        self.mouse = mouse_module.Controller()
        self._held_keys = {}
        self._held_buttons = {}
        self._lock = threading.RLock()
        self._listeners = []
        self._active = False
        self._closed = False
        self.on_input = lambda *args: None
        self.on_stop = lambda: None
        self.on_error = lambda message: None

    def start(self, on_input, on_stop, on_error):
        with self._lock:
            if self._closed or self._active:
                raise RuntimeError('输入监听已关闭或正在运行。')
            self._active = True
        self.on_input, self.on_stop, self.on_error = on_input, on_stop, on_error
        keyboard = self.keyboard_module.Listener(
            on_press=lambda key: self._safe(self._key, key, True),
            on_release=lambda key: self._safe(self._key, key, False))
        mouse = self.mouse_module.Listener(
            on_move=lambda x, y: self._safe(self.on_input, 'move', (int(x), int(y))),
            on_click=lambda x, y, button, pressed: self._safe(self._click, x, y, button, pressed))
        self._listeners = [keyboard, mouse]
        try:
            for listener in self._listeners:
                with self._lock:
                    if self._closed:
                        raise RuntimeError('输入监听已关闭。')
                    listener.start()
                threading.Thread(target=self._watch, args=(listener,), daemon=True).start()
                ready = threading.Event()
                def await_ready(current=listener, signal=ready):
                    current.wait()
                    signal.set()
                threading.Thread(target=await_ready, daemon=True).start()
                if not ready.wait(5):
                    raise RuntimeError('全局输入监听未能就绪，请重新启动 EchoKeys。')
            with self._lock:
                if self._closed or not self._active:
                    raise RuntimeError('输入监听已关闭或中断。')
        except Exception:
            self.close()
            raise

    def _watch(self, listener):
        try:
            listener.join()
            detail = '全局输入监听已中断，请重新启动 EchoKeys。'
        except Exception as exc:
            detail = f'全局输入监听失败：{exc}'
        if self._active:
            self.on_error(detail)

    def _safe(self, callback, *args):
        try:
            callback(*args)
        except Exception as exc:
            self.on_error(f'输入监听失败：{exc}')

    def _key(self, key, pressed):
        if key == self.keyboard_module.Key.esc:
            if pressed:
                self.on_stop()
            return
        name = getattr(key, 'name', None)
        vk = getattr(key, 'vk', None)
        value = f'name:{name}' if name else f'vk:{vk}'
        if valid_key(value):
            self.on_input('key_down' if pressed else 'key_up', (value,))

    def _click(self, x, y, button, pressed):
        if button in (self.mouse_module.Button.left, self.mouse_module.Button.right):
            name = 'left' if button == self.mouse_module.Button.left else 'right'
            self.on_input('mouse_down' if pressed else 'mouse_up', (name, int(x), int(y)))

    def _decode_key(self, value):
        if value.startswith('name:'):
            return getattr(self.keyboard_module.Key, value[5:])
        return self.keyboard_module.KeyCode.from_vk(int(value[3:]))

    def send(self, event):
        with self._lock:
            kind, data = event.kind, event.data
            if kind == 'move':
                self.mouse.position = data
            elif kind in ('key_down', 'key_up'):
                key = self._decode_key(data[0])
                if kind == 'key_down':
                    self._held_keys[data[0]] = key
                    self.keyboard.press(key)
                else:
                    self.keyboard.release(key)
                    self._held_keys.pop(data[0], None)
            elif kind in ('mouse_down', 'mouse_up'):
                button = getattr(self.mouse_module.Button, data[0])
                self.mouse.position = data[1:]
                if kind == 'mouse_down':
                    self._held_buttons[data[0]] = button
                    self.mouse.press(button)
                else:
                    self.mouse.release(button)
                    self._held_buttons.pop(data[0], None)

    def release_all(self):
        errors = []
        with self._lock:
            for held, controller in ((self._held_keys, self.keyboard), (self._held_buttons, self.mouse)):
                for name, value in reversed(list(held.items())):
                    try:
                        controller.release(value)
                        del held[name]
                    except Exception as exc:
                        errors.append(f'{name}: {exc}')
        if errors:
            raise RuntimeError('无法释放部分输入，请重试停止或退出：' + '；'.join(errors))

    def close(self):
        with self._lock:
            self._active = False
            self._closed = True
        try:
            self.release_all()
        finally:
            for listener in self._listeners:
                listener.stop()
