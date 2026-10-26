"""Tests for with_lock.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from with_lock import Slot, acquire, is_known_flaky, run_locked


class Slots(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())

    def test_a_one_slot_group_refuses_a_second_holder(self) -> None:
        held = acquire("web", 1, self.dir, timeout=1)
        with held, self.assertRaises(TimeoutError), acquire("web", 1, self.dir, timeout=0.3):
            pass

    def test_a_two_slot_group_takes_two_holders_and_refuses_a_third(self) -> None:
        first = acquire("core", 2, self.dir, timeout=1)
        second = acquire("core", 2, self.dir, timeout=1)
        with first, second, self.assertRaises(TimeoutError), acquire("core", 2, self.dir, 0.3):
            pass

    def test_groups_do_not_share_slots(self) -> None:
        with acquire("web", 1, self.dir, timeout=1), acquire("core", 1, self.dir, 0.3) as slot:
            self.assertIsInstance(slot, Slot)

    def test_a_slot_is_free_again_after_release(self) -> None:
        with acquire("web", 1, self.dir, timeout=1):
            pass
        with acquire("web", 1, self.dir, timeout=0.3):
            pass

    def test_a_holder_that_dies_frees_its_slot(self) -> None:
        # A crashed agent must not leave the group locked forever (no stale lock files to clean).
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                textwrap.dedent(
                    f"""
                    import sys, time
                    sys.path.insert(0, {str(Path(__file__).parent)!r})
                    from pathlib import Path
                    from with_lock import acquire
                    with acquire("web", 1, Path({str(self.dir)!r}), timeout=5):
                        print("held", flush=True)
                        time.sleep(60)
                    """
                ),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert holder.stdout is not None
        self.assertEqual(holder.stdout.readline().strip(), "held")
        with self.assertRaises(TimeoutError), acquire("web", 1, self.dir, timeout=0.3):
            pass
        holder.kill()
        holder.wait()
        holder.stdout.close()
        with acquire("web", 1, self.dir, timeout=2):
            pass


class KnownFlaky(unittest.TestCase):
    def test_shared_database_and_memory_failures_are_known(self) -> None:
        for line in [
            'psycopg.errors.UndefinedTable: relation "user" does not exist',
            "argon2.exceptions.HashingError: Memory allocation error",
            "Error: Test timed out in 5000ms.",
        ]:
            self.assertTrue(is_known_flaky(line), line)

    def test_an_ordinary_assertion_is_not_flaky(self) -> None:
        self.assertFalse(is_known_flaky("AssertionError: assert 1 == 2"))


class RunLocked(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.counter = self.dir / "runs"

    def command(self, message: str, fail_first: bool) -> list[str]:
        """A command that prints `message` and fails on its first run only (if `fail_first`)."""
        script = textwrap.dedent(
            f"""
            from pathlib import Path
            p = Path({str(self.counter)!r})
            n = int(p.read_text()) if p.exists() else 0
            p.write_text(str(n + 1))
            print({message!r})
            raise SystemExit(1 if {fail_first} and n == 0 else 0)
            """
        )
        return [sys.executable, "-c", script]

    def runs(self) -> int:
        return int(self.counter.read_text())

    def test_a_known_flaky_failure_is_run_once_more(self) -> None:
        code = run_locked(
            "core", 1, self.dir, self.command("HashingError: Memory allocation error", True)
        )
        self.assertEqual((code, self.runs()), (0, 2))

    def test_a_real_failure_is_not_retried(self) -> None:
        code = run_locked("core", 1, self.dir, self.command("AssertionError", True))
        self.assertEqual((code, self.runs()), (1, 1))

    def test_a_pass_runs_once(self) -> None:
        code = run_locked("core", 1, self.dir, self.command("ok", False))
        self.assertEqual((code, self.runs()), (0, 1))

    def test_the_lock_is_held_while_the_command_runs(self) -> None:
        started = time.monotonic()
        sleeper = [sys.executable, "-c", "import time; time.sleep(0.8)"]
        other = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).parent / "with_lock.py"),
                "web",
                "--lock-dir",
                str(self.dir),
                "--",
                *sleeper,
            ]
        )
        time.sleep(0.3)
        self.assertEqual(run_locked("web", 1, self.dir, [sys.executable, "-c", "pass"]), 0)
        other.wait()
        self.assertGreaterEqual(time.monotonic() - started, 0.8)


if __name__ == "__main__":
    unittest.main()
