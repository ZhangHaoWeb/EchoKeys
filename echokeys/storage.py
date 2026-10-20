"""One local task, versioned and atomically replaced; no import feature."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from .model import Event, Recording, parse_settings


@dataclass(frozen=True)
class Task:
    recording: Recording
    count: int = 1
    interval: float = 1.0

    def __post_init__(self):
        if type(self.count) is not int or type(self.interval) not in (int, float):
            raise ValueError('任务参数类型无效。')
        parse_settings(str(self.count), str(self.interval))
        if not isinstance(self.recording, Recording):
            raise ValueError('任务记录无效。')


def default_path() -> Path:
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    return base / 'EchoKeys' / 'task.json'


def save_task(path: Path, task: Task):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {'version': 1, 'count': task.count, 'interval': task.interval,
            'duration': task.recording.duration,
            'events': [[e.at, e.kind, list(e.data)] for e in task.recording.events]}
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.tmp', dir=path.parent, delete=False) as f:
            temp_path = Path(f.name)
            json.dump(data, f, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_task(path: Path) -> Task | None:
    try:
        with Path(path).open(encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError('本地任务文件损坏。') from exc
    try:
        if type(data) is not dict or type(data['version']) is not int or data['version'] != 1 or type(data['events']) is not list:
            raise ValueError('不支持的本地任务版本。')
        events = []
        for item in data['events']:
            if type(item) is not list or len(item) != 3 or type(item[2]) is not list:
                raise ValueError('任务事件格式无效。')
            events.append(Event(item[0], item[1], tuple(item[2])))
        return Task(Recording(tuple(events), data['duration']), data['count'], data['interval'])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'无法恢复本地任务：{exc}') from exc
