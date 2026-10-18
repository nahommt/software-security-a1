import math
import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(
        self,
        ip_limit=10,
        ip_window=60,
        user_failure_limit=5,
        user_window=300,
        clock=time.monotonic,
    ):
        self._ip_limit = ip_limit
        self._ip_window = ip_window
        self._user_failure_limit = user_failure_limit
        self._user_window = user_window
        self._clock = clock
        self._ip_attempts = defaultdict(deque)
        self._user_failures = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _prune(events, now, window):
        while events and events[0] <= now - window:
            events.popleft()

    def _retry_after(self, events, now, limit, window):
        self._prune(events, now, window)
        if len(events) < limit:
            return None
        return max(1, math.ceil(events[0] + window - now))

    def acquire(self, ip, username):
        with self._lock:
            now = self._clock()
            retry = self._retry_after(self._ip_attempts[ip], now, self._ip_limit, self._ip_window)
            if retry is None:
                retry = self._retry_after(
                    self._user_failures[username], now, self._user_failure_limit, self._user_window
                )
            if retry is not None:
                return retry
            self._ip_attempts[ip].append(now)
            return None

    def record_failure(self, username):
        with self._lock:
            self._user_failures[username].append(self._clock())

    def record_success(self, username):
        with self._lock:
            self._user_failures.pop(username, None)
