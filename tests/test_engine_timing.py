"""Deterministic timing checks: no real sleep, hooks, or desktop access."""
import unittest

from echokeys.engine import Engine, play_recording
from echokeys.model import Event, Recording


class VirtualClock:
    def __init__(self, stop_at=None):
        self.now = 0.0
        self.stop_at = stop_at
        self.signal = VirtualSignal(self)

    def __call__(self):
        return self.now


class VirtualSignal:
    def __init__(self, clock):
        self.clock = clock
        self.stopped = False

    def set(self):
        self.stopped = True

    def clear(self):
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        if not self.stopped:
            end = self.clock.now + seconds
            if self.clock.stop_at is not None and end >= self.clock.stop_at:
                self.clock.now = self.clock.stop_at
                self.set()
            else:
                self.clock.now = end
        return self.stopped


class TimedBackend:
    def __init__(self, clock, latency=0):
        self.clock = clock
        self.latency = latency
        self.sent = []
        self.releases = 0

    def send(self, event):
        self.sent.append((self.clock(), event))
        self.clock.now += self.latency

    def release_all(self):
        self.releases += 1


class PlaybackTimingTests(unittest.TestCase):
    def run_playback(self, recording, *, count=1, interval=0, clock=None, latency=0):
        clock = clock or VirtualClock()
        backend = TimedBackend(clock, latency)
        states = []
        play_recording(recording, count, interval, clock.signal, backend,
                       lambda *args: states.append((clock(), args)),
                       clock=clock, wait=clock.signal.wait)
        return clock, backend, states

    def test_preserves_leading_pause_event_spacing_and_trailing_pause(self):
        rec = Recording((Event(1, 'move', (10, 20)), Event(2.5, 'move', (30, 40))), 4)
        clock, backend, _ = self.run_playback(rec)
        self.assertEqual([at for at, _ in backend.sent], [1, 2.5])
        self.assertEqual(clock(), 4)
        self.assertEqual(backend.releases, 1)

    def test_input_injection_latency_does_not_accumulate_timing_drift(self):
        rec = Recording(tuple(Event(at, 'move', (0, 0)) for at in (.5, 1, 1.5)), 2)
        clock, backend, _ = self.run_playback(rec, latency=.4)
        self.assertEqual([at for at, _ in backend.sent], [.5, 1, 1.5])
        self.assertEqual(clock(), 2)

    def test_fractional_interval_starts_only_after_full_recording_duration(self):
        rec = Recording((Event(.5, 'move', (0, 0)),), 2)
        clock, backend, states = self.run_playback(rec, count=3, interval=.25)
        self.assertEqual([at for at, _ in backend.sent], [.5, 2.75, 5])
        self.assertEqual([at for at, state in states if state[0] == 'waiting'], [2, 4.25])
        self.assertEqual(clock(), 6.5)

    def test_zero_interval_and_zero_duration_still_execute_exact_round_count(self):
        rec = Recording((Event(0, 'move', (0, 0)),), 0)
        clock, backend, states = self.run_playback(rec, count=4)
        self.assertEqual(len(backend.sent), 4)
        self.assertEqual(clock(), 0)
        self.assertEqual([state[1] for _, state in states if state[0] == 'playing'], [1, 2, 3, 4])

    def test_cancel_before_first_event_emits_nothing(self):
        rec = Recording((Event(1, 'move', (0, 0)),), 2)
        _, backend, states = self.run_playback(rec, count=3, clock=VirtualClock(stop_at=.5))
        self.assertEqual(backend.sent, [])
        self.assertEqual(backend.releases, 1)
        self.assertFalse(any(state[0] == 'waiting' for _, state in states))

    def test_cancel_in_trailing_pause_prevents_next_round(self):
        rec = Recording((Event(0, 'move', (0, 0)),), 5)
        _, backend, states = self.run_playback(rec, count=3, clock=VirtualClock(stop_at=2))
        self.assertEqual(len(backend.sent), 1)
        self.assertFalse(any(state[0] == 'waiting' for _, state in states))

    def test_already_canceled_playback_sends_no_events_or_progress(self):
        clock = VirtualClock()
        clock.signal.set()
        _, backend, states = self.run_playback(Recording((Event(0, 'move', (0, 0)),), 0), clock=clock)
        self.assertEqual(backend.sent, [])
        self.assertEqual(states, [])
        self.assertEqual(backend.releases, 1)


class CountdownTests(unittest.TestCase):
    def test_test_and_loop_start_after_exactly_three_seconds(self):
        for testing in (False, True):
            with self.subTest(testing=testing):
                clock = VirtualClock()
                backend = TimedBackend(clock)
                engine = Engine(backend, clock=clock)
                engine.cancel = clock.signal
                engine.recording = Recording((Event(.25, 'move', (0, 0)),), 1)
                engine.start_playback(test=testing)
                engine.join(1)
                self.assertFalse(engine.busy)
                self.assertEqual(backend.sent, [(3.25, engine.recording.events[0])])
                self.assertEqual(clock(), 4)
                messages = []
                while not engine.messages.empty():
                    messages.append(engine.messages.get())
                self.assertEqual([item[1] for item in messages if item[0] == 'countdown'], [3, 2, 1])

    def test_cancel_each_countdown_keeps_old_recording_and_sends_nothing(self):
        for action in ('record', 'test', 'loop'):
            with self.subTest(action=action):
                clock = VirtualClock(stop_at=2)
                backend = TimedBackend(clock)
                engine = Engine(backend, clock=clock)
                engine.cancel = clock.signal
                old = Recording((Event(0, 'move', (0, 0)),), 1)
                engine.recording = old
                if action == 'record':
                    engine.start_recording()
                else:
                    engine.start_playback(test=action == 'test', count=3)
                engine.join(1)
                self.assertFalse(engine.busy)
                self.assertIs(engine.recording, old)
                self.assertEqual(backend.sent, [])
                self.assertEqual(clock(), 2)
