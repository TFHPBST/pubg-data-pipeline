import time
from collections import deque


class RateLimiter:
    def __init__(self, max_calls=10, period=60.0, clock=time.monotonic, sleep=time.sleep):
        self.max_calls = max_calls
        self.period = period
        self.clock = clock
        self.sleep = sleep
        self.calls = deque()

    def wait(self):
        while True:
            now = self.clock()
            while self.calls and now - self.calls[0] >= self.period:  # (F)
                self.calls.popleft()
            if len(self.calls) < self.max_calls:  # (G)
                self.calls.append(now)
                return
            self.sleep(self.period - (now - self.calls[0]))  # (H) 가장 오래된 기록
