"""Cancelable recording/playback state machine, independent of desktop APIs."""
import math
import queue
import threading
import time
from .model import Recorder, Recording, parse_settings


def play_recording(recording, count, interval, cancel, backend, notify, *, clock=time.monotonic, wait=None):
    wait = wait or cancel.wait
    def wait_until(deadline):
        while not cancel.is_set():
            remaining = deadline - clock()
            if remaining <= 0:
                return False
            if wait(min(remaining, 60)):
                return True
        return True
    try:
        for current in range(1, count + 1):
            if cancel.is_set():
                break
            start = clock()
            notify('playing', current, count)
            for event in recording.events:
                if wait_until(start + event.at) or cancel.is_set():
                    return
                backend.send(event)
            if wait_until(start + recording.duration):
                return
            if current < count:
                notify('waiting', current, count)
                if wait_until(clock() + interval):
                    return
    finally:
        backend.release_all()


class Engine:
    def __init__(self, backend, *, countdown=3, clock=time.monotonic):
        self.backend = backend
        self.recording = Recording()
        self.state = 'empty'
        self.messages = queue.SimpleQueue()
        self.cancel = threading.Event()
        self._lock = threading.RLock()
        self._thread = None
        self._recorder = None
        self._started_at = 0
        self._stopped_at = None
        self._clock = clock
        self._countdown = countdown
        self.current = 0
        self.total = 0
        self.testing = False

    @property
    def busy(self):
        return self.state not in ('empty', 'ready')

    @property
    def elapsed(self):
        with self._lock:
            if self.state == 'recording':
                return max(0, (self._stopped_at or self._clock()) - self._started_at)
            return self.recording.duration

    def _notify(self, state, current=0, total=0):
        with self._lock:
            self.state, self.current, self.total = state, current, total
            self.messages.put(('state', state, current, total))

    def _launch(self, action, count=1, interval=0):
        with self._lock:
            if self.busy:
                raise RuntimeError('任务执行中，请先按 ESC 停止。')
            if action != 'record' and not self.recording.events:
                raise ValueError('请先录制有效操作。')
            self.cancel.clear()
            self._stopped_at = None
            self.testing = action == 'test'
            self._notify('countdown', 0, count if action != 'record' else 0)
            self._thread = threading.Thread(target=self._run, args=(action, count, interval), daemon=True)
            self._thread.start()

    def start_recording(self):
        self._launch('record')

    def start_playback(self, test=False, count=1, interval=1):
        if test:
            count, interval = 1, 0
        else:
            count, interval = parse_settings(str(count), str(interval))
        self._launch('test' if test else 'play', count, interval)

    def _run(self, action, count, interval):
        try:
            deadline = self._clock() + self._countdown
            while not self.cancel.is_set():
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                self.messages.put(('countdown', math.ceil(remaining), action))
                self.cancel.wait(min(remaining, 1))
            with self._lock:
                if self.cancel.is_set():
                    return
                if action == 'record':
                    self._recorder = Recorder()
                    self._started_at = self._clock()
                    self._notify('recording')
            if action == 'record':
                self.cancel.wait()
                with self._lock:
                    duration = max(0, (self._stopped_at or self._clock()) - self._started_at)
                    self.recording = self._recorder.finish(duration)
                    self._recorder = None
                    self.messages.put(('recorded',))
            else:
                play_recording(self.recording, count, interval, self.cancel, self, self._notify, clock=self._clock)
        except Exception as exc:
            self.messages.put(('error', f'执行失败：{exc}'))
        finally:
            self._recorder = None
            self._notify('ready' if self.recording.events else 'empty')
            self.messages.put(('finished', self.cancel.is_set()))

    def capture(self, kind, data):
        with self._lock:
            if self.state == 'recording' and self._recorder is not None and not self.cancel.is_set():
                self._recorder.add(max(0, self._clock() - self._started_at), kind, data)

    def send(self, event):
        with self._lock:
            if not self.cancel.is_set():
                self.backend.send(event)

    def release_all(self):
        try:
            self.backend.release_all()
        except Exception as exc:
            self.messages.put(('fatal', f'输入释放失败，请关闭程序重试释放：{exc}'))
            raise

    def stop(self):
        # Set the signal first: input hook callbacks must never wait for playback.
        self.cancel.set()
        with self._lock:
            if self.state == 'recording' and self._stopped_at is None:
                self._stopped_at = self._clock()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    def fail(self, message):
        self.stop()
        self.messages.put(('fatal', message))
