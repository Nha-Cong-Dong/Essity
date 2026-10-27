"""Tests for lane.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import lane
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
        self.assertTrue(env["AI_TEST_DATABASE_URL"].endswith("/ai_test_l3"))
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

    def test_down_refuses_a_lane_with_uncommitted_work(self) -> None:
        # `worktree remove --force` would throw it away; the branch keeps only what was committed.
        path = up(self.repo, 3, "t9.6-w", base="main", create_db=False)
        (path / "draft.txt").write_text("not committed")
        with self.assertRaises(RuntimeError):
            down(self.repo, 3)
        self.assertTrue((path / "draft.txt").exists())
        down(self.repo, 3, force=True)
        self.assertFalse(path.exists())

    def test_a_lane_in_use_is_refused(self) -> None:
        up(self.repo, 1, "t9.9-x", base="main", create_db=False)
        with self.assertRaises(RuntimeError):
            up(self.repo, 1, "t9.7-z", base="main", create_db=False)
        down(self.repo, 1)


class Stale(UpDown):
    def report(self, branch: str, status: str, age_minutes: float) -> Path:
        folder = self.repo / ".work" / "T9"
        folder.mkdir(parents=True)
        (folder / "card.yaml").write_text(f"task: T9\nbranch: {branch}\n")
        file = folder / "lane-report.yaml"
        file.write_text(f"status: {status}\n")
        stamp = time.time() - age_minutes * 60
        os.utime(file, (stamp, stamp))
        return file

    def test_plain_status_has_no_ages(self) -> None:
        up(self.repo, 1, "t9.9-x", base="main", create_db=False)
        self.assertNotIn("report", lane.status(self.repo)[0])
        down(self.repo, 1)

    def test_in_progress_lane_with_old_commit_and_report_is_stale(self) -> None:
        up(self.repo, 1, "t9.9-x", base="main", create_db=False)
        self.report("t9.9-x", "in_progress", 90)
        later = time.time() + 2 * 3600  # the commit is two hours old by then
        row = lane.status(self.repo, stale=True, now=later)[0]
        self.assertIn("report in_progress", row)
        self.assertTrue(row.endswith("STALE"))
        down(self.repo, 1, force=True)

    def test_fresh_report_or_done_is_not_stale(self) -> None:
        up(self.repo, 1, "t9.9-x", base="main", create_db=False)
        report = self.report("t9.9-x", "in_progress", 5)
        later = time.time() + 2 * 3600
        os.utime(report, (later - 300, later - 300))  # report touched 5 minutes before `later`
        self.assertNotIn("STALE", lane.status(self.repo, stale=True, now=later)[0])
        report.write_text("status: done\n")
        os.utime(report, (later - 5400, later - 5400))
        self.assertNotIn("STALE", lane.status(self.repo, stale=True, now=later)[0])
        down(self.repo, 1, force=True)

    def test_orphan_worktrees_are_listed_with_dirty_files_and_pr(self) -> None:
        git(self.repo, "branch", "t9.5-v")
        orphan = self.repo / ".claude" / "worktrees" / "docs-flow"
        git(self.repo, "worktree", "add", str(orphan), "t9.5-v")
        (orphan / "x.txt").write_text("x")
        up(self.repo, 2, "t9.4-u", base="main", create_db=False)
        with mock.patch.object(lane.flow, "open_pr", return_value={"number": 1}):
            rows = lane.status(self.repo, stale=True, now=time.time())
        orphan_rows = [r for r in rows if r.startswith("ORPHAN")]
        self.assertEqual(len(orphan_rows), 1)  # L2 is a lane, not an orphan
        self.assertIn("docs-flow  t9.5-v", orphan_rows[0])
        self.assertIn("(1 file(s) not committed)", orphan_rows[0])
        self.assertTrue(orphan_rows[0].endswith("PR open"))
        self.assertTrue(orphan.exists())  # read only
        down(self.repo, 2)
        down_orphan = subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(orphan)]
        )
        self.assertEqual(down_orphan.returncode, 0)


class Preflight(unittest.TestCase):
    def run_preflight(
        self, *, running: bool = True, healthy: bool = True, ram: float | None = 8.0,
        encoding: str = "utf-8", docker: str | None = "docker", started: bool = True,
    ) -> tuple[list[str], bool]:  # fmt: skip
        with (
            mock.patch.object(lane, "find_docker", return_value=docker),
            mock.patch.object(lane, "docker_running", return_value=running),
            mock.patch.object(lane, "start_docker", return_value=started) as start,
            mock.patch.object(lane, "container_healthy", return_value=healthy),
            mock.patch.object(lane, "free_ram_gb", return_value=ram),
            mock.patch.dict(os.environ, {"PYTHONIOENCODING": encoding}),
        ):
            result = lane.preflight(sleep=lambda _s: None)
            self.started = start.called
            return result

    def test_everything_fine(self) -> None:
        self.assertEqual(self.run_preflight(), (["preflight: ok"], True))
        self.assertFalse(self.started)

    def test_no_docker_is_fatal(self) -> None:
        notes, ok = self.run_preflight(docker=None)
        self.assertFalse(ok)
        self.assertIn("not found", notes[0])

    def test_docker_is_started_when_the_daemon_is_down(self) -> None:
        notes, ok = self.run_preflight(running=False)
        self.assertTrue(ok)
        self.assertTrue(self.started)
        self.assertIn("starting Docker Desktop", notes[0])
        self.assertFalse(self.run_preflight(running=False, started=False)[1])

    def test_unhealthy_containers_say_just_up(self) -> None:
        notes, ok = self.run_preflight(healthy=False)
        self.assertTrue(ok)
        self.assertEqual(sum("just up" in n for n in notes), 2)

    def test_ram_thresholds(self) -> None:
        self.assertTrue(self.run_preflight(ram=2.0)[1])
        self.assertIn("warning", self.run_preflight(ram=2.0)[0][0])
        notes, ok = self.run_preflight(ram=1.0)
        self.assertFalse(ok)
        self.assertIn("stop", notes[0])
        self.assertEqual(self.run_preflight(ram=None), (["preflight: ok"], True))

    def test_encoding_warning(self) -> None:
        notes, ok = self.run_preflight(encoding="cp1252")
        self.assertTrue(ok)
        self.assertIn("PYTHONIOENCODING", notes[0])
        self.assertEqual(self.run_preflight(encoding="UTF8")[0], ["preflight: ok"])

    def test_start_docker_waits_until_the_daemon_answers(self) -> None:
        answers = iter([False, False, True])
        with (
            mock.patch.object(lane, "DOCKER_APP", Path(__file__)),
            mock.patch.object(lane.subprocess, "Popen") as popen,
            mock.patch.object(lane, "docker_running", side_effect=lambda: next(answers)),
        ):
            self.assertTrue(lane.start_docker(wait=180, sleep=lambda _s: None))
        popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
