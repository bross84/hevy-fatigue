"""Short-lived Hevy history cache for live stress previews; no persistence/migrations."""
from collections import OrderedDict
from threading import Lock
from time import monotonic

TTL_SECONDS = 60
_history = OrderedDict()
_lock = Lock()


def history(template_id, loader):
    with _lock:
        cached = _history.get(template_id)
        if cached and monotonic() - cached[0] < TTL_SECONDS:
            _history.move_to_end(template_id)
            return cached[1]
    entries = loader()
    with _lock:
        _history[template_id] = (monotonic(), entries)
        _history.move_to_end(template_id)
        while len(_history) > 128:
            _history.popitem(last=False)
    return entries


def invalidate(template_ids=None):
    with _lock:
        if template_ids is None:
            _history.clear()
        else:
            for template_id in template_ids:
                _history.pop(template_id, None)
