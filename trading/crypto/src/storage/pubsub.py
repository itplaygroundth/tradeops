import threading
import queue
from typing import Any, List

_lock = threading.Lock()
_subscribers: List[queue.Queue] = []


def subscribe() -> queue.Queue:
    q = queue.Queue()
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def publish(event: Any) -> None:
    with _lock:
        subs = list(_subscribers)
    for q in subs:
        try:
            q.put(event, block=False)
        except Exception:
            # if queue full or fail, skip
            pass
