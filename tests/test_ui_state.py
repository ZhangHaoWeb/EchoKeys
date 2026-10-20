import unittest
from unittest.mock import Mock
from echokeys.app import App
from echokeys.engine import Engine
from echokeys.model import Recording, Event


class Variable:
    def __init__(self, value=''):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class UITests(unittest.TestCase):
    def setUp(self):
        self.app = App.__new__(App)
        self.app.engine = Engine(Mock())
        self.app.count = Variable('1')
        self.app.interval = Variable('1')
        self.app.dialogs = Mock()
        self.app.root = Mock()
        self.app._healthy = True
        self.app._closing = False
        self.app._dirty = False
        self.app.saved_text = Variable()
        for name in ('record_button', 'test_button', 'play_button', 'save_button', 'stop_button', 'count_entry', 'interval_entry'):
            setattr(self.app, name, Mock())
        self.addCleanup(lambda: (self.app.engine.stop(), self.app.engine.join(1)))

    def test_empty_disables_replay_but_allows_record(self):
        self.app._update_controls()
        self.app.record_button.configure.assert_called_with(state='normal')
        self.app.test_button.configure.assert_called_with(state='disabled')
        self.app.play_button.configure.assert_called_with(state='disabled')

    def test_busy_disables_start_and_parameters(self):
        self.app.engine.start_recording()
        self.app._update_controls()
        for button in (self.app.record_button, self.app.test_button, self.app.play_button, self.app.save_button, self.app.count_entry, self.app.interval_entry):
            button.configure.assert_called_with(state='disabled')
        self.app.stop_button.configure.assert_called_with(state='normal')

    def test_declining_overwrite_does_not_start(self):
        self.app.engine.recording = Recording((Event(0, 'move', (0, 0)),), 1)
        self.app.dialogs.askyesno.return_value = False
        self.app._record()
        self.assertFalse(self.app.engine.busy)
        self.assertEqual(len(self.app.engine.recording.events), 1)

    def test_invalid_parameters_do_not_start_loop(self):
        self.app.count.set('1.2')
        self.app._play(False)
        self.assertFalse(self.app.engine.busy)
        self.app.dialogs.showerror.assert_called_once()

    def test_test_ignores_invalid_loop_fields(self):
        self.app.engine.recording = Recording((Event(0, 'move', (0, 0)),), 1)
        self.app.count.set('invalid')
        self.app.interval.set('invalid')
        self.app._play(True)
        self.assertTrue(self.app.engine.busy)
        self.assertEqual(self.app.engine.total, 1)

    def test_late_ready_message_does_not_reenable_failed_listener(self):
        self.app._failed = False
        self.app._load_error = None
        self.app.status = Variable()
        self.app.detail = Variable()
        self.app.progress = Variable()
        self.app.duration = Variable()
        self.app.engine.messages.put(('fatal', 'listener failed'))
        self.app.engine.messages.put(('backend_ready',))
        self.app._poll()
        self.assertFalse(self.app._healthy)
        self.app.record_button.configure.assert_called_with(state='disabled')

    def test_failed_close_cannot_restart_without_working_listener(self):
        self.app.backend = Mock()
        self.app.backend.close.side_effect = OSError('release failed')
        self.app.status = Variable()
        self.app.detail = Variable()
        self.app._closing = True
        self.app._finish_close()
        self.assertFalse(self.app._healthy)
        self.app.root.destroy.assert_not_called()
