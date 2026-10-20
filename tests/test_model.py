import unittest
from echokeys.model import Event, Recording, Recorder, parse_settings


class ModelTests(unittest.TestCase):
    def test_settings(self):
        self.assertEqual(parse_settings('1', '0.25'), (1, .25))
        self.assertEqual(parse_settings('3', '0'), (3, 0))
        for count, interval in [('0', '1'), ('-1', '1'), ('1.5', '1'), ('', '1'), ('1', '-1'), ('1', 'nan'), ('1', 'inf')]:
            with self.subTest(count=count, interval=interval), self.assertRaises(ValueError):
                parse_settings(count, interval)

    def test_record_paths_clicks_chords_and_tail(self):
        r = Recorder()
        r.add(.1, 'move', (12, 20))
        r.add(.2, 'mouse_down', ('left', 12, 20))
        r.add(.3, 'mouse_up', ('left', 12, 20))
        r.add(.4, 'mouse_down', ('left', 12, 20))
        r.add(.5, 'mouse_up', ('left', 12, 20))
        r.add(.6, 'key_down', ('name:ctrl_l',))
        r.add(.7, 'key_down', ('vk:65',))
        r.add(.8, 'key_up', ('vk:65',))
        r.add(.9, 'key_up', ('name:ctrl_l',))
        result = r.finish(2)
        self.assertEqual(result.duration, 2)
        self.assertEqual(len(result.events), 9)
        self.assertEqual([e.at for e in result.events], [.1, .2, .3, .4, .5, .6, .7, .8, .9])

    def test_drag_scroll_escape_and_orphan_release_ignored(self):
        r = Recorder()
        for at, kind, data in [(.1, 'mouse_down', ('left', 1, 1)), (.2, 'move', (2, 1)), (.3, 'move', (1, 1)), (.4, 'mouse_up', ('left', 1, 1)), (.5, 'scroll', (1,)), (.6, 'key_down', ('name:esc',)), (.7, 'key_up', ('name:esc',)), (.8, 'key_up', ('vk:65',))]:
            r.add(at, kind, data)
        self.assertFalse(r.finish(1).events)

    def test_finish_closes_held_keys_and_drops_pending_click(self):
        r = Recorder()
        r.add(.1, 'key_down', ('vk:65',))
        r.add(.2, 'mouse_down', ('left', 1, 1))
        result = r.finish(1)
        self.assertEqual(result.events, (Event(.1, 'key_down', ('vk:65',)), Event(1, 'key_up', ('vk:65',))))

    def test_recording_rejects_invalid_data(self):
        for events, duration in [((Event(2, 'move', (1, 2)),), 1), ((Event(0, 'scroll', (1,)),), 1), ((Event(0, 'key_down', ('name:esc',)),), 1), ((), float('inf'))]:
            with self.assertRaises(ValueError):
                Recording(events, duration)
