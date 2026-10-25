"""The client IPs tests send from must differ between runs: rate limits count per IP in a Redis
that is never flushed, so an IP reused by the next run starts it near its limit (429)."""

import random

from ips import fresh_ip


def test_fresh_ip_does_not_follow_the_random_seed() -> None:
    # Red when: the IP comes from `random`, which pytest-randomly reseeds before every test
    # from the run's seed and the test's id: a rerun with the same seed (`-p randomly
    # --randomly-seed=last`) would send from the same IPs as the run before it.
    random.seed(6)
    first = fresh_ip("10")
    random.seed(6)
    assert fresh_ip("10") != first


def test_fresh_ip_keeps_its_prefix() -> None:
    assert fresh_ip("172.16").startswith("172.16.")
    assert fresh_ip("10").count(".") == 3
