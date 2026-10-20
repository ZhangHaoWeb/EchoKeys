"""Immutable recordings and filtering of unsupported input."""
from dataclasses import dataclass
import math
import re


KEY_NAMES = frozenset('alt alt_l alt_r alt_gr backspace caps_lock cmd cmd_l cmd_r ctrl ctrl_l ctrl_r delete down end enter home insert left menu num_lock page_down page_up pause print_screen right scroll_lock shift shift_l shift_r space tab up'.split()) | frozenset(f'f{i}' for i in range(1, 25))


def valid_key(value):
    if not isinstance(value, str):
        return False
    if value.startswith('name:'):
        return value[5:] in KEY_NAMES
    return bool(re.fullmatch(r'vk:[0-9]{1,3}', value)) and 1 <= int(value[3:]) <= 255 and int(value[3:]) != 27


def parse_settings(count: str, interval: str) -> tuple[int, float]:
    if not re.fullmatch(r'[0-9]+', count.strip()):
        raise ValueError('循环次数必须是正整数。')
    try:
        rounds = int(count)
        seconds = float(interval)
    except (ValueError, OverflowError):
        raise ValueError('请输入有效的循环次数和间隔。') from None
    if rounds < 1:
        raise ValueError('循环次数必须大于 0。')
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError('循环间隔必须是大于或等于 0 的有限秒数。')
    return rounds, seconds


@dataclass(frozen=True)
class Event:
    at: float
    kind: str
    data: tuple


@dataclass(frozen=True)
class Recording:
    events: tuple[Event, ...] = ()
    duration: float = 0.0

    def __post_init__(self):
        if not isinstance(self.events, tuple) or not isinstance(self.duration, (int, float)) or not math.isfinite(self.duration) or self.duration < 0:
            raise ValueError('录制时长无效。')
        last = 0
        keys, buttons = set(), set()
        for e in self.events:
            if not isinstance(e, Event) or not isinstance(e.at, (int, float)) or not math.isfinite(e.at) or not last <= e.at <= self.duration or not isinstance(e.data, tuple):
                raise ValueError('录制事件时间无效。')
            last = e.at
            if e.kind == 'move':
                coords = e.data
            elif e.kind in ('mouse_down', 'mouse_up') and len(e.data) == 3 and e.data[0] in ('left', 'right'):
                coords = e.data[1:]
                if e.kind == 'mouse_down':
                    if e.data[0] in buttons:
                        raise ValueError('重复的鼠标按下。')
                    buttons.add(e.data[0])
                else:
                    if e.data[0] not in buttons:
                        raise ValueError('孤立的鼠标松开。')
                    buttons.remove(e.data[0])
            elif e.kind in ('key_down', 'key_up') and len(e.data) == 1 and valid_key(e.data[0]):
                if e.kind == 'key_down':
                    keys.add(e.data[0])
                elif e.data[0] in keys:
                    keys.remove(e.data[0])
                else:
                    raise ValueError('孤立的按键松开。')
                continue
            else:
                raise ValueError('不支持的录制事件。')
            if len(coords) != 2 or any(type(v) is not int or abs(v) > 2**31 - 1 for v in coords):
                raise ValueError('屏幕坐标无效。')
        if keys or buttons:
            raise ValueError('录制包含未释放的按键或鼠标按钮。')


class Recorder:
    def __init__(self):
        self.events = []
        self.keys = {}
        self.buttons = {}

    def add(self, at: float, kind: str, data: tuple):
        if kind.startswith('key_'):
            if not data or not valid_key(data[0]):
                return
            if kind == 'key_down':
                self.keys[data[0]] = True
            elif kind == 'key_up':
                if data[0] not in self.keys:
                    return
                del self.keys[data[0]]
            else:
                return
            self.events.append(Event(at, kind, data))
        elif kind == 'move':
            if self.buttons:
                for button, (event, moved) in list(self.buttons.items()):
                    self.buttons[button] = (event, moved or data != event.data[1:])
            else:
                self.events.append(Event(at, kind, data))
        elif kind == 'mouse_down' and data[0] in ('left', 'right'):
            self.buttons[data[0]] = (Event(at, kind, data), False)
        elif kind == 'mouse_up' and data[0] in self.buttons:
            down, moved = self.buttons.pop(data[0])
            if not moved and data[1:] == down.data[1:]:
                self.events.extend((down, Event(at, kind, data)))

    def finish(self, duration: float) -> Recording:
        events = self.events + [Event(duration, 'key_up', (key,)) for key in reversed(self.keys)]
        return Recording(tuple(sorted(events, key=lambda e: e.at)), duration)
