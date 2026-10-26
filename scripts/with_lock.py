"""Run a heavy command only when its group has a free slot, across every worktree of the repo.

This machine has little RAM: two Vitest runs at once time out (R43), five core-api suites at once
run argon2 out of memory (R53), and agents sharing a test database see tables vanish (R32). The
limits used to live in agent prompts; this script enforces them.

    python scripts/with_lock.py web -- pnpm --filter web vitest run --maxWorkers=4
    python scripts/with_lock.py core -- uv run pytest -q

Slots are OS file locks, so a holder that crashes frees its slot. Locks live in the repo's shared
git directory, so every worktree sees the same ones. A failure that matches a known flaky pattern
is run once more before it is reported.
"""

import argparse
import re
import subprocess
import sys
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

# Group -> slots. web: next build, Vitest, Playwright. core/ai: a whole pytest suite.
GROUPS = {"web": 1, "core": 2, "ai": 2}

# Failures caused by the machine or by other agents, not by the code under test.
KNOWN_FLAKY = [
    re.compile(r'relation "\w+" does not exist'),  # R32: another agent migrated the database down
    re.compile(r"HashingError: Memory allocation error"),  # R53
    re.compile(r"Test timed out in \d+ms"),  # R43: jsdom start-up under load
]


@dataclass
class Slot:
    group: str
    index: int
    handle: IO[bytes]


def _try_lock(handle: IO[bytes]) -> bool:
    handle.seek(0)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


@contextmanager
def acquire(group: str, slots: int, lock_dir: Path, timeout: float | None = None) -> Iterator[Slot]:
    """Hold one of the group's slots; raise TimeoutError after `timeout` seconds (None: wait)."""
    lock_dir.mkdir(parents=True, exist_ok=True)
    deadline = None if timeout is None else time.monotonic() + timeout
    announced = False
    while True:
        for index in range(slots):
            handle = open(lock_dir / f"{group}.{index}.lock", "a+b")  # noqa: SIM115
            if _try_lock(handle):
                try:
                    yield Slot(group, index, handle)
                finally:
                    handle.close()  # closing releases the lock
                return
            handle.close()
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError(f"no free slot in group {group!r} after {timeout} s")
        if not announced:
            print(f"with_lock: waiting for a free {group!r} slot...", file=sys.stderr, flush=True)
            announced = True
        time.sleep(0.1)


def is_known_flaky(output: str) -> bool:
    return any(pattern.search(output) for pattern in KNOWN_FLAKY)


def _run_streaming(command: list[str]) -> tuple[int, str]:
    """Run the command, echo its output as it comes, return the exit code and the output's tail."""
    tail: deque[str] = deque(maxlen=2000)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace"
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            sys.stdout.write(line)
            tail.append(line)
        return process.wait(), "".join(tail)
    finally:
        # Interrupted (Ctrl+C) before the command ended: the slot is about to be freed, so the
        # command must not run on beside the next holder. A hard kill of this process cannot be
        # caught; that case still leaves the command running.
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def known_flaky_pattern(output: str) -> str | None:
    return next((p.pattern for p in KNOWN_FLAKY if p.search(output)), None)


def run_locked(group: str, slots: int, lock_dir: Path, command: list[str]) -> int:
    with acquire(group, slots, lock_dir):
        code, output = _run_streaming(command)
        pattern = known_flaky_pattern(output) if code != 0 else None
        if pattern:
            print(f"with_lock: known flaky failure ({pattern}), running once more", file=sys.stderr)
            code, _ = _run_streaming(command)
    return code


def default_lock_dir() -> Path:
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(common) / "essity-locks"


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print(
            "usage: with_lock.py <group> [--slots N] [--lock-dir DIR] -- <command...>",
            file=sys.stderr,
        )
        return 2
    split = argv.index("--")
    parser = argparse.ArgumentParser(prog="with_lock.py")
    parser.add_argument("group", choices=sorted(GROUPS))
    parser.add_argument("--slots", type=int)
    parser.add_argument("--lock-dir", type=Path)
    args = parser.parse_args(argv[:split])
    command = argv[split + 1 :]
    if not command:
        parser.error("no command after --")
    slots = args.slots or GROUPS[args.group]
    return run_locked(args.group, slots, args.lock_dir or default_lock_dir(), command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
