"""Persist an API allowance earned only while Onshape is visible."""
import json
from pathlib import Path
import time
import threading
from functools import wraps


def synchronized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return call


class BudgetExhausted(RuntimeError):
    pass


class ApiBudget:
    RATE_PER_HOUR = 5
    TOTAL_LIMIT = 2000
    STARTING_CREDIT = 10

    def __init__(self, path):
        self.lock = threading.RLock()
        self.path = Path(path)
        self.last_tick = time.monotonic()
        self.last_save = self.last_tick
        self.active = False
        try:
            state = json.loads(self.path.read_text()) if self.path.exists() else {}
            self.credit = min(self.STARTING_CREDIT, max(0, float(state.get('credit', self.STARTING_CREDIT))))
            self.used = int(state.get('used', 0))
            self.active_seconds = float(state.get('active_seconds', 0))
        except (OSError, ValueError, TypeError):
            # A broken budget file must not replenish the allowance.
            self.credit, self.used, self.active_seconds = 0, self.TOTAL_LIMIT, 0

    @synchronized
    def save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'credit': self.credit, 'used': self.used,
                                        'active_seconds': self.active_seconds,
                                        'total_limit': self.TOTAL_LIMIT}), encoding='utf-8')
        temporary.replace(self.path)
        self.last_save = time.monotonic()

    @synchronized
    def tick(self, active, now=None):
        now = time.monotonic() if now is None else now
        # Do not earn a large burst when Windows resumes from sleep.
        elapsed = min(30, max(0, now - self.last_tick))
        if self.active and active:
            self.active_seconds += elapsed
            self.credit = min(self.STARTING_CREDIT, self.credit + elapsed * self.RATE_PER_HOUR / 3600)
        if self.active and not active or now - self.last_save >= 60:
            self.save()
        self.active = active
        self.last_tick = now

    @synchronized
    def available(self, calls=1):
        return self.credit + 1e-8 >= calls and self.used + calls <= self.TOTAL_LIMIT

    @synchronized
    def consume(self):
        if not self.available():
            raise BudgetExhausted('Onshape API budget is exhausted; using cached presence.')
        self.credit -= 1
        self.used += 1
        # Count attempts conservatively, even if the request fails.
        self.save()
