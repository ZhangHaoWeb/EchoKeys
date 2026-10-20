import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from echokeys.model import Event, Recording
from echokeys.storage import Task, load_task, save_task


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'nested' / 'task.json'
        self.task = Task(Recording((Event(0, 'move', (-1, 10)),), 3), 4, .25)

    def test_round_trip_recording_and_settings(self):
        save_task(self.path, self.task)
        self.assertEqual(load_task(self.path), self.task)

    def test_missing_task_is_none(self):
        self.assertIsNone(load_task(self.path))

    def test_corrupt_task_is_rejected(self):
        self.path.parent.mkdir()
        for data in ['bad json', '{"version":999}', json.dumps({'version': 1, 'count': 0, 'interval': 1, 'duration': 0, 'events': []})]:
            self.path.write_text(data)
            with self.assertRaises(ValueError):
                load_task(self.path)

    def test_failed_replace_preserves_previous_file(self):
        save_task(self.path, self.task)
        with patch('echokeys.storage.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                save_task(self.path, Task(Recording(), 1, 1))
        self.assertEqual(load_task(self.path), self.task)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_round_trip_preserves_chords_clicks_and_event_timing(self):
        recording = Recording((
            Event(.1, 'key_down', ('name:ctrl_l',)),
            Event(.2, 'key_down', ('vk:65',)),
            Event(.3, 'key_up', ('vk:65',)),
            Event(.4, 'key_up', ('name:ctrl_l',)),
            Event(.5, 'mouse_down', ('right', -100, 200)),
            Event(.6, 'mouse_up', ('right', -100, 200)),
        ), 2)
        task = Task(recording, 3, 0)
        save_task(self.path, task)
        self.assertEqual(load_task(self.path), task)

    def test_successful_save_replaces_previous_task(self):
        save_task(self.path, self.task)
        replacement = Task(Recording((Event(0, 'move', (200, 300)),), 1), 2, 0)
        save_task(self.path, replacement)
        self.assertEqual(load_task(self.path), replacement)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_partial_write_failure_preserves_original_and_removes_temp_file(self):
        save_task(self.path, self.task)
        original = self.path.read_bytes()
        def partial_write(data, stream, **kwargs):
            stream.write('{"version":')
            raise OSError('disk full')
        with patch('echokeys.storage.json.dump', side_effect=partial_write):
            with self.assertRaises(OSError):
                save_task(self.path, Task(Recording(), 1, 1))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_malformed_or_unbalanced_saved_events_are_rejected(self):
        self.path.parent.mkdir()
        invalid_traces = [
            [[0, 'key_down', ['vk:65']]],
            [[0, 'key_down', ['name:esc']]],
            [[0, 'move', [1]]],
            [[0, 'move', ['1', 2]]],
            [[0, 'move', {'x': 1, 'y': 2}]],
            [[0, 'move']],
            [[-1, 'move', [1, 2]]],
        ]
        for events in invalid_traces:
            data = {'version': 1, 'count': 1, 'interval': 1, 'duration': 1, 'events': events}
            self.path.write_text(json.dumps(data))
            with self.subTest(events=events), self.assertRaises(ValueError):
                load_task(self.path)

    def test_invalid_saved_loop_settings_are_rejected(self):
        self.path.parent.mkdir()
        for count, interval in [(True, 1), (1.5, 1), (0, 1), (1, -1), (1, float('inf')), (1, float('nan'))]:
            data = {'version': 1, 'count': count, 'interval': interval, 'duration': 0, 'events': []}
            self.path.write_text(json.dumps(data))
            with self.subTest(count=count, interval=interval), self.assertRaises(ValueError):
                load_task(self.path)
