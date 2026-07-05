"""RateLimiter tests using an injected fake clock — no real sleeping."""

import pytest

from jobscout.sources.throttle import RateLimiter


class FakeTime:
    """Manual clock + sleep recorder so timing is tested deterministically."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_first_call_does_not_sleep() -> None:
    fake = FakeTime()
    limiter = RateLimiter(2.0, clock=fake.clock, sleep=fake.sleep)
    await limiter.wait()
    assert fake.sleeps == []


async def test_rapid_calls_are_spaced_by_min_interval() -> None:
    fake = FakeTime()
    limiter = RateLimiter(2.0, clock=fake.clock, sleep=fake.sleep)
    await limiter.wait()
    await limiter.wait()
    await limiter.wait()
    assert fake.sleeps == [2.0, 2.0]


async def test_no_sleep_when_enough_time_already_passed() -> None:
    fake = FakeTime()
    limiter = RateLimiter(2.0, clock=fake.clock, sleep=fake.sleep)
    await limiter.wait()
    fake.now += 5.0
    await limiter.wait()
    assert fake.sleeps == []


def test_negative_interval_rejected() -> None:
    with pytest.raises(ValueError, match="min_interval"):
        RateLimiter(-1.0)
