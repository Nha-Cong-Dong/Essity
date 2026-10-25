"""Client IPs for HTTP tests, fresh on every call and in every run."""

import secrets


def fresh_ip(prefix: str) -> str:
    """`prefix` ("10", "172.16"...) filled up to an IPv4 address with random octets.

    From `secrets`, not `random`: pytest-randomly reseeds `random` before each test from the run's
    seed, so a rerun with the same seed would reuse the IPs, and their rate limit counters, of the
    run before it (Redis is shared across runs and never flushed).
    """
    octets = [str(secrets.randbelow(256)) for _ in range(3 - prefix.count("."))]
    octets[-1] = str(1 + secrets.randbelow(254))
    return ".".join([prefix, *octets])
