"""Tests for lane.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from lane import down, lane_env, lane_path, parse_lane, up


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


class Names(unittest.TestCase):
    def test_lanes_are_l1_to_l5(self) -> None:
        self.assertEqual(parse_lane("l3"), 3)
        for bad in ["L0", "L6", "lane1", "3"]:
            with self.assertRaises(ValueError):
                parse_lane(bad)

    def test_each_lane_has_its_own_database_and_redis_db(self) -> None:
        # Fixed per lane, so nothing to hand out or give back; ad-hoc agents use 6..14.
        env = lane_env(3)
        self.assertTrue(env["CORE_TEST_DATABASE_URL"].endswith("/core_test_l3"))
        self.assertTrue(env["CORE_TEST_REDIS_URL"].endswith("/3"))

    def test_the_lane_folder_is_under_claude_worktrees(self) -> None:
        repo = Path("D:/Essity")
        self.assertEqual(lane_path(repo, 2), repo / ".claude" / "worktrees" / "L2")


class UpDown(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp()) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "a.txt").write_text("a")
        git(self.repo, "add", "a.txt")
        git(self.repo, "commit", "-q", "-m", "a")

    def test_up_makes_the_branch_in_the_lane_folder_and_down_removes_it(self) -> None:
        path = up(self.repo, 1, "t9.9-x", base="main", create_db=False)
        self.assertEqual(git(path, "branch", "--show-current"), "t9.9-x")
        self.assertTrue((path / "a.txt").exists())
        down(self.repo, 1)
        self.assertFalse(path.exists())
        self.assertIn("t9.9-x", git(self.repo, "branch", "--list", "t9.9-x"))  # branch kept

    def test_up_continues_an_existing_branch(self) -> None:
        git(self.repo, "branch", "t9.8-y")
        path = up(self.repo, 2, "t9.8-y", base="main", create_db=False)
        self.assertEqual(git(path, "branch", "--show-current"), "t9.8-y")
        down(self.repo, 2)

    def test_a_lane_in_use_is_refused(self) -> None:
        up(self.repo, 1, "t9.9-x", base="main", create_db=False)
        with self.assertRaises(RuntimeError):
            up(self.repo, 1, "t9.7-z", base="main", create_db=False)
        down(self.repo, 1)


if __name__ == "__main__":
    unittest.main()
