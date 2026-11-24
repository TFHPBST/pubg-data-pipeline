from rate_limit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds  # (A) 가짜 sleep은 무엇을 해야 할까요?


def make_limiter(clock):
    return RateLimiter(max_calls=10, period=60.0, clock=clock.time, sleep=clock.sleep)


def test_first_ten_calls_do_not_wait():
    clock = FakeClock()
    limiter = make_limiter(clock)
    for _ in range(10):
        limiter.wait()
    assert clock.slept == []  # (B)


def test_eleventh_call_waits_full_period():
    clock = FakeClock()
    limiter = make_limiter(clock)
    for _ in range(11):
        limiter.wait()
    assert clock.slept == [60.0]  # (C)
    assert clock.now == 60.0  # (D)


def test_waits_only_until_oldest_expires():
    clock = FakeClock()
    limiter = make_limiter(clock)
    for _ in range(10):
        limiter.wait()
        clock.now += 1  # t=0..9에 호출, 끝나면 t=10
    limiter.wait()
    assert clock.slept == [50.0]  # (E)


def test_no_wait_after_period_passes():
    clock = FakeClock()
    limiter = make_limiter(clock)
    for _ in range(10):
        limiter.wait()
    clock.now += 60
    for _ in range(10):
        limiter.wait()
    assert clock.slept == []
