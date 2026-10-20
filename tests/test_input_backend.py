from types import SimpleNamespace
import unittest
from echokeys.input_backend import InputBackend
from echokeys.model import Event


class Controller:
    def __init__(self):
        self.actions = []
        self.position = (0, 0)
        self.fail_release = None
    def press(self, value):
        self.actions.append(('down', value))
    def release(self, value):
        self.actions.append(('up', value))
        if value == self.fail_release:
            raise OSError('release failed')


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.kb, self.mouse = Controller(), Controller()
        self.keys = SimpleNamespace(esc='escape', ctrl_l='control')
        keyboard = SimpleNamespace(Controller=lambda: self.kb, Key=self.keys, KeyCode=SimpleNamespace(from_vk=lambda vk: vk))
        mouse = SimpleNamespace(Controller=lambda: self.mouse, Button=SimpleNamespace(left='L', right='R'))
        self.backend = InputBackend(keyboard, mouse)

    def test_key_and_absolute_click(self):
        self.backend.send(Event(0, 'key_down', ('vk:65',)))
        self.backend.send(Event(0, 'mouse_down', ('left', -10, 30)))
        self.assertEqual(self.mouse.position, (-10, 30))
        self.backend.release_all()
        self.assertEqual(self.kb.actions, [('down', 65), ('up', 65)])
        self.assertEqual(self.mouse.actions, [('down', 'L'), ('up', 'L')])

    def test_failed_release_still_releases_other_keys_and_mouse(self):
        self.backend.send(Event(0, 'key_down', ('name:ctrl_l',)))
        self.backend.send(Event(0, 'key_down', ('vk:65',)))
        self.backend.send(Event(0, 'mouse_down', ('left', 1, 2)))
        self.kb.fail_release = 65
        with self.assertRaises(RuntimeError):
            self.backend.release_all()
        self.assertIn(('up', 'control'), self.kb.actions)
        self.assertIn(('up', 'L'), self.mouse.actions)
        self.kb.fail_release = None
        self.backend.release_all()
        self.assertEqual(self.kb.actions.count(('up', 65)), 2)

    def test_failed_press_is_also_released(self):
        def broken(value):
            raise OSError('partially sent')
        self.kb.press = broken
        with self.assertRaises(OSError):
            self.backend.send(Event(0, 'key_down', ('vk:65',)))
        self.backend.release_all()
        self.assertIn(('up', 65), self.kb.actions)

    def test_escape_only_stops_never_captured(self):
        actions = []
        self.backend.on_input = lambda *args: actions.append(args)
        self.backend.on_stop = lambda: actions.append('stop')
        self.backend._key('escape', True)
        self.backend._key('escape', False)
        self.assertEqual(actions, ['stop'])

    def test_escape_during_key_press_cancels_playback_and_releases_key(self):
        import threading
        from echokeys.engine import play_recording
        from echokeys.model import Recording
        cancel = threading.Event()
        self.backend.on_stop = cancel.set
        press = self.kb.press
        def press_then_escape(key):
            press(key)
            self.backend._key('escape', True)
        self.kb.press = press_then_escape
        recording = Recording((Event(0, 'key_down', ('vk:65',)),
                               Event(1, 'key_up', ('vk:65',))), 2)
        play_recording(recording, 3, 1, cancel, self.backend, lambda *args: None)
        self.assertTrue(cancel.is_set())
        self.assertEqual(self.kb.actions, [('down', 65), ('up', 65)])
        self.backend.release_all()
        self.assertEqual(self.kb.actions, [('down', 65), ('up', 65)])

    def test_escape_during_mouse_press_cancels_playback_and_releases_button(self):
        import threading
        from echokeys.engine import play_recording
        from echokeys.model import Recording
        cancel = threading.Event()
        self.backend.on_stop = cancel.set
        press = self.mouse.press
        def press_then_escape(button):
            press(button)
            self.backend._key('escape', True)
        self.mouse.press = press_then_escape
        recording = Recording((Event(0, 'mouse_down', ('left', 10, 20)),
                               Event(1, 'mouse_up', ('left', 10, 20))), 2)
        play_recording(recording, 3, 1, cancel, self.backend, lambda *args: None)
        self.assertTrue(cancel.is_set())
        self.assertEqual(self.mouse.actions, [('down', 'L'), ('up', 'L')])
        self.backend.release_all()
        self.assertEqual(self.mouse.actions, [('down', 'L'), ('up', 'L')])


class ListenerLifecycleTests(unittest.TestCase):
    def make_backend(self, ready=True):
        import threading
        self.started = []
        self.finished = threading.Event()
        owner = self
        class Listener:
            def __init__(self, **kwargs):
                self.ready = False
            def start(self):
                owner.started.append(self)
            def wait(self):
                self.ready = ready
                if not ready:
                    owner.finished.wait(1)
            def join(self):
                owner.finished.wait(1)
            def stop(self):
                owner.finished.set()
        keyboard = SimpleNamespace(Controller=Controller, Listener=Listener)
        mouse = SimpleNamespace(Controller=Controller, Listener=Listener)
        b = InputBackend(keyboard, mouse)
        self.addCleanup(b.close)
        return b

    def test_start_waits_until_hooks_ready(self):
        b = self.make_backend()
        b.start(lambda *a: None, lambda: None, lambda *a: None)
        self.assertEqual(len(self.started), 2)
        self.assertTrue(all(listener.ready for listener in self.started))

    def test_close_before_start_does_not_open_hooks(self):
        b = self.make_backend()
        b.close()
        with self.assertRaises(RuntimeError):
            b.start(lambda *a: None, lambda: None, lambda *a: None)
        self.assertEqual(self.started, [])
