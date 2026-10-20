"""Input traces that are easy to miss in a manual recording session."""
import unittest
from echokeys.model import Event, Recorder, Recording


class RecordingEdgeTests(unittest.TestCase):
    def test_right_click_retains_position_and_press_duration(self):
        recorder = Recorder()
        recorder.add(.1, 'mouse_down', ('right', -120, 50))
        recorder.add(.4, 'mouse_up', ('right', -120, 50))
        self.assertEqual(recorder.finish(1).events, (
            Event(.1, 'mouse_down', ('right', -120, 50)),
            Event(.4, 'mouse_up', ('right', -120, 50))))

    def test_click_with_interleaved_keyboard_keeps_original_chronology(self):
        recorder = Recorder()
        recorder.add(.1, 'mouse_down', ('left', 10, 20))
        recorder.add(.2, 'key_down', ('vk:65',))
        recorder.add(.3, 'mouse_up', ('left', 10, 20))
        recorder.add(.4, 'key_up', ('vk:65',))
        self.assertEqual([event.kind for event in recorder.finish(1).events],
                         ['mouse_down', 'key_down', 'mouse_up', 'key_up'])

    def test_drag_does_not_discard_subsequent_valid_click(self):
        recorder = Recorder()
        recorder.add(.1, 'mouse_down', ('left', 0, 0))
        recorder.add(.2, 'move', (10, 20))
        recorder.add(.3, 'mouse_up', ('left', 10, 20))
        recorder.add(.4, 'mouse_down', ('left', 10, 20))
        recorder.add(.5, 'mouse_up', ('left', 10, 20))
        self.assertEqual(recorder.finish(1).events, (
            Event(.4, 'mouse_down', ('left', 10, 20)),
            Event(.5, 'mouse_up', ('left', 10, 20))))

    def test_auto_repeat_keydowns_remain_in_recording(self):
        recorder = Recorder()
        for at in (.1, .3, .5):
            recorder.add(at, 'key_down', ('vk:65',))
        recorder.add(.7, 'key_up', ('vk:65',))
        result = recorder.finish(1)
        self.assertEqual([event.at for event in result.events], [.1, .3, .5, .7])
        self.assertEqual([event.kind for event in result.events], ['key_down'] * 3 + ['key_up'])

    def test_stop_releases_chord_in_reverse_order(self):
        recorder = Recorder()
        recorder.add(.1, 'key_down', ('name:ctrl_l',))
        recorder.add(.2, 'key_down', ('name:shift_l',))
        recorder.add(.3, 'key_down', ('vk:65',))
        self.assertEqual(recorder.finish(1).events[-3:], (
            Event(1, 'key_up', ('vk:65',)),
            Event(1, 'key_up', ('name:shift_l',)),
            Event(1, 'key_up', ('name:ctrl_l',))))

    def test_rejects_unbalanced_or_out_of_order_recording(self):
        traces = [
            (Event(0, 'key_down', ('vk:65',)),),
            (Event(0, 'key_up', ('vk:65',)),),
            (Event(0, 'mouse_down', ('left', 0, 0)),),
            (Event(0, 'mouse_up', ('left', 0, 0)),),
            (Event(.5, 'move', (0, 0)), Event(.2, 'move', (1, 1))),
            (Event(float('nan'), 'move', (0, 0)),),
        ]
        for events in traces:
            with self.subTest(events=events), self.assertRaises(ValueError):
                Recording(events, 1)
