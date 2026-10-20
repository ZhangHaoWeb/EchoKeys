import threading
import time
import unittest
from echokeys.engine import Engine, play_recording
from echokeys.model import Event, Recording


class FakeTime:
    def __init__(self, stop_at=None):
        self.now = 0
        self.stop_at = stop_at
        self.cancel = threading.Event()
    def clock(self):
        return self.now
    def wait(self, delay):
        if self.stop_at is not None and self.now + delay >= self.stop_at:
            self.now = self.stop_at
            self.cancel.set()
        else:
            self.now += delay
        return self.cancel.is_set()


class Backend:
    def __init__(self):
        self.events = []
        self.releases = 0
    def send(self, event):
        self.events.append(event)
    def release_all(self):
        self.releases += 1


class PlaybackTests(unittest.TestCase):
    def test_three_rounds_take_34_seconds_no_final_wait(self):
        t, b, progress = FakeTime(), Backend(), []
        rec = Recording((Event(0, 'move', (1, 2)),), 10)
        play_recording(rec, 3, 2, t.cancel, b, lambda *v: progress.append(v), clock=t.clock, wait=t.wait)
        self.assertEqual(t.now, 34)
        self.assertEqual(len(b.events), 3)
        self.assertEqual([p[1] for p in progress if p[0] == 'playing'], [1, 2, 3])
        self.assertEqual(len([p for p in progress if p[0] == 'waiting']), 2)

    def test_stop_in_event_wait_or_loop_wait(self):
        for stop_at in (1, 11):
            t, b = FakeTime(stop_at), Backend()
            rec = Recording((Event(0, 'move', (1, 2)), Event(5, 'move', (2, 3))), 10)
            play_recording(rec, 3, 2, t.cancel, b, lambda *args: None, clock=t.clock, wait=t.wait)
            self.assertEqual(len(b.events), 1 if stop_at == 1 else 2)
            self.assertEqual(b.releases, 1)

    def test_exception_releases_inputs(self):
        class Broken(Backend):
            def send(self, e):
                raise OSError('injection failed')
        b, t = Broken(), FakeTime()
        with self.assertRaises(OSError):
            play_recording(Recording((Event(0, 'move', (0, 0)),), 1), 1, 0, t.cancel, b, lambda *a: None, clock=t.clock, wait=t.wait)
        self.assertEqual(b.releases, 1)


class EngineTests(unittest.TestCase):
    def make_engine(self, **kwargs):
        e = Engine(Backend(), **kwargs)
        self.addCleanup(lambda: (e.stop(), e.join(1)))
        return e

    def test_empty_recording_cannot_play(self):
        with self.assertRaises(ValueError):
            self.make_engine().start_playback()

    def test_cancel_countdown_keeps_old_recording_and_rejects_concurrent_start(self):
        e = self.make_engine()
        old = Recording((Event(0, 'move', (1, 1)),), 1)
        e.recording = old
        e.start_recording()
        with self.assertRaises(RuntimeError):
            e.start_recording()
        e.stop()
        e.join(1)
        self.assertIs(e.recording, old)
        self.assertEqual(e.state, 'ready')

    def test_capture_stops_and_keeps_record(self):
        e = self.make_engine(countdown=0)
        e.start_recording()
        self.wait_state(e, 'recording')
        e.capture('key_down', ('vk:65',))
        e.stop()
        e.join(1)
        self.assertEqual([v.kind for v in e.recording.events], ['key_down', 'key_up'])
        snapshot = e.recording
        e.capture('move', (7, 8))
        self.assertIs(e.recording, snapshot)

    def test_test_playback_ignores_loop_settings(self):
        e = self.make_engine(countdown=0)
        e.recording = Recording((Event(0, 'move', (1, 1)),), .001)
        e.start_playback(test=True, count=10, interval=100)
        e.join(1)
        self.assertFalse(e.busy)
        self.assertEqual(len(e.backend.events), 1)

    def test_stop_during_playback_does_not_send_next_event(self):
        e = self.make_engine(countdown=0)
        e.recording = Recording((Event(0, 'move', (1, 1)), Event(10, 'move', (2, 2))), 10)
        e.start_playback()
        self.wait_state(e, 'playing')
        e.stop()
        e.join(1)
        self.assertLessEqual(len(e.backend.events), 1)
        self.assertFalse(e.busy)

    @staticmethod
    def wait_state(e, state):
        end = time.monotonic() + 1
        while e.state != state and time.monotonic() < end:
            time.sleep(.001)
        if e.state != state:
            raise AssertionError(f'Expected {state}, got {e.state}')


class LongWaitTests(unittest.TestCase):
    def test_large_finite_interval_can_be_canceled_without_overflow(self):
        cancel, b = threading.Event(), Backend()
        def platform_wait(delay):
            if delay > threading.TIMEOUT_MAX:
                raise OverflowError('platform wait overflow')
            if delay > 0:
                cancel.set()
            return cancel.is_set()
        play_recording(Recording((Event(0, 'move', (0, 0)),), 0), 2, 1e100,
                       cancel, b, lambda *a: None, clock=lambda: 0, wait=platform_wait)
        self.assertEqual(len(b.events), 1)
        self.assertEqual(b.releases, 1)


class ReleaseFailureTests(unittest.TestCase):
    def test_release_failure_disables_further_execution_via_fatal_message(self):
        class BrokenRelease(Backend):
            def release_all(self):
                raise OSError('cannot release')
        e = Engine(BrokenRelease(), countdown=0)
        e.recording = Recording((Event(0, 'move', (0, 0)),), 0)
        e.start_playback()
        e.join(1)
        messages = []
        while not e.messages.empty():
            messages.append(e.messages.get())
        self.assertTrue(any(item[0] == 'fatal' for item in messages))
