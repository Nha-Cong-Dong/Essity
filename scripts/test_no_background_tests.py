"""Tests for the background-test guard in hooks/serial_guard.py (retro 02/11)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "hooks"))

from serial_guard import background_test_reason


class BackgroundTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp()) / "Essity"
        self.lane = root / ".claude" / "worktrees" / "L3"
        self.lane.mkdir(parents=True)
        self.main = root

    def reason(self, command: str, cwd: Path | None = None, bg: object = True) -> str | None:
        return background_test_reason(
            "Bash", {"command": command, "run_in_background": bg}, cwd or self.lane
        )

    def test_denies_test_runners_in_lane_cwd(self) -> None:
        for command in [
            "uv run pytest -q",
            "python -m pytest services/core-api",
            "cd services/web && pnpm vitest run",
            "pnpm --filter web test",
            "pnpm run test:unit",
            "pnpm e2e",
            "npx playwright test",
            "python scripts/with_lock.py core -- uv run pytest",
            "python scripts/with_lock.py web -- pnpm test",
            "bash -c 'uv run pytest'",
            "FOO=1 pytest",
        ]:
            with self.subTest(command=command):
                reason = self.reason(command)
                self.assertIsNotNone(reason)
                assert reason is not None
                self.assertIn("foreground", reason)
                self.assertIn("600000", reason)

    def test_foreground_or_other_commands_pass(self) -> None:
        self.assertIsNone(self.reason("uv run pytest", bg=False))
        self.assertIsNone(self.reason("uv run pytest", bg=None))
        self.assertIsNone(self.reason("docker compose up -d"))
        self.assertIsNone(self.reason("echo pytest"))
        self.assertIsNone(self.reason("grep -r vitest ."))
        self.assertIsNone(self.reason("pnpm install"))
        self.assertIsNone(self.reason("pnpm dev"))
        self.assertIsNone(self.reason("ruff check ."))

    def test_main_session_may_background(self) -> None:
        self.assertIsNone(self.reason("uv run pytest", cwd=self.main))

    def test_absolute_lane_path_in_command_counts(self) -> None:
        lane = self.lane.as_posix()
        self.assertIsNotNone(self.reason(f"pytest {lane}/services", cwd=self.main))

    def test_other_tools_and_bad_input_fail_open(self) -> None:
        self.assertIsNone(background_test_reason("Edit", {"file_path": "x"}, self.lane))
        self.assertIsNone(background_test_reason("Bash", {}, self.lane))
        self.assertIsNone(
            background_test_reason("Bash", {"command": None, "run_in_background": True}, self.lane)
        )
        broken = {"command": "pytest 'unterminated", "run_in_background": "yes"}
        self.assertIsNone(background_test_reason("Bash", broken, Path(".")))


if __name__ == "__main__":
    unittest.main()
