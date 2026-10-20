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
