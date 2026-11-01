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


INDEX = """| Task | Mốc | Mức | Trạng thái | Spec | Dòng | Tên |
|---|---|---|---|---|---|---|
| T0.1 | M0 |  | ✅ (#30; x) |  | 10 | Base |
| T1.1 | M1 |  |  |  | 20 | Plain |
| T1.2 | M1 | 🔴 |  |  | 30 | Red |
| T1.3 | M1 | 🟡 |  |  | 40 | Yellow |
| T1.4 | M1 | 🔴 |  |  | 50 | Needs T9.9 |
| T1.5 | M1 |  |  |  | 60 | Clash |
| T1.6 | M1 |  |  |  | 70 | Running |
| T0.2 | M0 |  |  |  | 80 | Early but later line |
| T1.7 | M1 | 🔴 |  |  | 90 | Migration |
| T1.8 | M1 |  | 🟦 #5 |  | 95 | Doing |
| T1.9 | M1 |  | 🔶 |  | 96 | Partial |
"""
PLAN = """### T0.1 — Base
- **Phụ thuộc:** —
### T1.1 — Plain
- **Phụ thuộc:** T0.1
- **File:** `web/a.ts`
### T1.2 — Red
- **Phụ thuộc:** T0.1
- **File:** `web/b.ts`
### T1.3 — Yellow
- **Phụ thuộc:** T0.1, T1.1
- **File:** `web/c.ts`
### T1.4 — Needs
- **Phụ thuộc:** T9.9
- **File:** `web/d.ts`
### T1.5 — Clash
- **Phụ thuộc:** —
- **File:** `core_api/x/y.py`
### T1.6 — Running
- **Phụ thuộc:** —
- **File:** `web/e.ts`
### T0.2 — Early
- **Phụ thuộc:** —
- **File:** `web/f.ts`
### T1.8 — Doing
- **Phụ thuộc:** —
- **File:** `web/g.ts`
### T1.9 — Partial
- **Phụ thuộc:** —
- **File:** `web/h.ts`
### T1.7 — Migration
- **Phụ thuộc:** —
- **File:** `core_api/db/migrations/0009.py`
"""


class Next(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "plan-index.md").write_text(INDEX, encoding="utf-8")
        (self.repo / "docs" / "PLAN.md").write_text(PLAN, encoding="utf-8")

    def card(self, task: str, lane: str, risk: str, branch: str, touches: str, status: str) -> None:
        folder = self.repo / ".work" / task
        folder.mkdir(parents=True)
        (folder / "card.yaml").write_text(
            f"task: {task}\nlane: {lane}\nrisk: {risk}\nbranch: {branch}\ntouches: [{touches}]\n",
            encoding="utf-8",
        )
        if status:
            (folder / "lane-report.yaml").write_text(f"status: {status}\n", encoding="utf-8")

    def run_next(self, prs: list[dict[str, str]] | None, **kwargs: object) -> list[str]:
        return lane.next_tasks(self.repo, gh=lambda: prs, **kwargs)  # type: ignore[arg-type]

    def codes(self, out: list[str]) -> list[str]:
        return [x.split(" | ")[0] for x in out[1:] if x.startswith("T")]

    def test_orders_by_milestone_then_risk_then_line(self) -> None:
        out = self.run_next([])
        self.assertEqual(self.codes(out), ["T0.2", "T1.2", "T1.7", "T1.1", "T1.5", "T1.6", "T1.9"])
        self.assertIn("được phát", out[0])

    def test_merged_cell_with_trailing_text_counts_as_merged(self) -> None:
        self.assertNotIn("T0.1", self.codes(self.run_next([])))
        self.assertIn("T1.1", self.codes(self.run_next([])))  # its dependency T0.1 is merged

    def test_missing_dependency_is_dropped_and_shown_with_all(self) -> None:
        self.assertNotIn("T1.4", self.codes(self.run_next([])))
        out = self.run_next([], show_all=True)
        self.assertIn("T1.4 | thiếu phụ thuộc T9.9", out)

    def test_running_task_and_touch_clash_are_dropped(self) -> None:
        self.card("T1.6", "L2", "yellow", "t1.6", "web/e.ts", "in_progress")
        self.card("T-X", "L3", "yellow", "tx", "core_api/x", "")
        codes = self.codes(self.run_next([]))
        self.assertNotIn("T1.6", codes)
        self.assertNotIn("T1.5", codes)
        out = self.run_next([], show_all=True)
        self.assertIn("T1.5 | trùng touches với T-X (L3)", out)

    def test_done_card_without_open_pr_does_not_block(self) -> None:
        self.card("T1.6", "L2", "yellow", "t1.6", "web/e.ts", "done")
        self.assertIn("T1.6", self.codes(self.run_next([])))

    def test_three_open_prs_stop_handing_out_but_still_list(self) -> None:
        prs = [{"headRefName": f"b{i}", "title": f"p{i}"} for i in range(3)]
        out = self.run_next(prs)
        self.assertIn("3/3", out[0])
        self.assertIn("DỪNG PHÁT", out[0])
        self.assertTrue(self.codes(out))

    def test_two_red_prs_stop_by_card_title_or_plan_index(self) -> None:
        self.card("T-R", "L2", "red", "br", "web/z", "done")
        prs = [
            {"headRefName": "br", "title": "plain title"},
            {
                "headRefName": "other",
                "title": "T1.2 something",
            },  # red through plan-index
        ]
        out = self.run_next(prs)
        self.assertIn("🔴 mở 2/2", out[0])
        self.assertIn("DỪNG PHÁT", out[0])
        one = self.run_next([{"headRefName": "o", "title": "fix 🔴"}])
        self.assertIn("được phát", one[0])

    def test_migration_file_suggests_l1(self) -> None:
        out = self.run_next([])
        self.assertTrue(next(x for x in out if x.startswith("T1.7")).split(" | ")[4] == "L1")
        self.assertTrue(next(x for x in out if x.startswith("T1.1")).split(" | ")[4] == "bất kỳ")

    def test_gh_failure_warns_without_crashing(self) -> None:
        out = self.run_next(None)
        self.assertIn("warning", out[1])
        self.assertIn("0/3", out[0])

    def test_open_pr_title_codes_are_running_without_a_card(self) -> None:
        out = self.run_next([{"headRefName": "x", "title": "T1.1 + T1.5 combined"}], show_all=True)
        self.assertNotIn("T1.1", self.codes(out))
        self.assertNotIn("T1.5", self.codes(out))

    def test_in_progress_cell_is_not_a_candidate_but_partial_is(self) -> None:
        self.assertNotIn("T1.8", self.codes(self.run_next([])))
        self.assertIn("T1.8 | đang làm", self.run_next([], show_all=True))
        out = self.run_next([])
        self.assertIn("T1.9", self.codes(out))

    def test_limit(self) -> None:
        self.assertEqual(len(self.codes(self.run_next([], limit=2))), 2)


if __name__ == "__main__":
    unittest.main()


MODELS = """from sqlalchemy.orm import Mapped, mapped_column


class DocSection(Base):
    __tablename__ = "doc_section"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]


class UserOwned:
    user_id: Mapped[int]


class Unit(UserOwned, Base):
    __tablename__ = 'unit'

    page_start: Mapped[int]
"""


class Schema(unittest.TestCase):
    """W4: a card's `needs_schema` columns must exist in the base's core-api models."""

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp()) / "repo"
        models = self.repo / "services" / "core-api" / "src" / "core_api" / "db" / "models"
        models.mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        (models / "document.py").write_text(MODELS, encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "models")
        (self.repo / ".work" / "T7.4").mkdir(parents=True)

    def card(self, extra: str) -> None:
        text = f"task: T7.4\nbranch: t7.4-x\nbase: main\n{extra}"
        (self.repo / ".work" / "T7.4" / "card.yaml").write_text(text, encoding="utf-8")

    def test_all_columns_present(self) -> None:
        self.card("needs_schema: [doc_section.title, doc_section.id, unit.page_start]\n")
        self.assertEqual(lane.schema_check(self.repo, "T7.4"), ([], []))

    def test_missing_columns_are_listed(self) -> None:
        # page_start exists on unit, not on doc_section: the class block decides
        self.card("needs_schema:\n  - doc_section.page_start\n  - doc_section.title\n  - nope.x\n")
        missing, notes = lane.schema_check(self.repo, "T7.4")
        self.assertEqual(missing, ["doc_section.page_start", "nope.x"])
        self.assertEqual(notes, [])

    def test_columns_from_mixins_count_and_block_scope_does_not_hide_the_field(self) -> None:
        # 02/11: `scope: |` hid needs_schema; `grade_job.id` (from a mixin) read as missing
        self.card("scope: |\n  text # x\ntouches: [a]\nneeds_schema: [unit.user_id]\n")
        self.assertEqual(lane.schema_check(self.repo, "T7.4"), ([], []))
        self.card("scope: |\n  text\nneeds_schema: [doc_section.user_id]\n")
        self.assertEqual(lane.schema_check(self.repo, "T7.4")[0], ["doc_section.user_id"])

    def test_a_card_without_the_field_warns_and_passes(self) -> None:
        self.card("risk: red\n")
        missing, notes = lane.schema_check(self.repo, "T7.4")
        self.assertEqual(missing, [])
        self.assertIn("needs_schema", notes[0])

    def test_cli_exit_codes(self) -> None:
        self.card("needs_schema: [doc_section.studied_weight]\n")
        with mock.patch.object(lane, "main_repo", lambda: self.repo):
            self.assertEqual(lane.main(["preflight", "T7.4"]), 1)
            self.card("needs_schema: []\n")
            self.assertEqual(lane.main(["preflight", "T7.4"]), 0)


class Lanes(unittest.TestCase):
    """W5–W7: a repo with a bare remote and lane worktrees."""

    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.remote = root / "remote.git"
        git(root, "init", "-q", "--bare", str(self.remote))
        self.repo = root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "a.txt").write_text("a")
        (self.repo / ".gitignore").write_text(".work/\n.claude/\n")
        git(self.repo, "add", "a.txt", ".gitignore")
        git(self.repo, "commit", "-q", "-m", "a")
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-q", "origin", "main")

    def lane(self, n: int, task: str, status: str, name: str = "") -> Path:
        path = self.repo / ".claude" / "worktrees" / (name or f"L{n}")
        git(self.repo, "worktree", "add", "-q", "-b", f"{task.lower()}-x", str(path), "main")
        git(path, "push", "-q", "-u", "origin", f"{task.lower()}-x")
        card = self.repo / ".work" / task
        card.mkdir(parents=True, exist_ok=True)
        (card / "card.yaml").write_text(
            f"task: {task}\nlane: L{n}\nbranch: {task.lower()}-x\nworktree: {path.as_posix()}\n",
            encoding="utf-8",
        )
        report = path / ".work" / task
        report.mkdir(parents=True)
        (report / "lane-report.yaml").write_text(f"status: {status}\n", encoding="utf-8")
        return path

    # -- W5 stop-all
    def test_stop_all_commits_only_code_pushes_and_notes_next(self) -> None:
        busy = self.lane(3, "T7.4", "in_progress", "L3-t74")
        done = self.lane(2, "T7.2", "done")
        for rel in ["services/x.py", "tests/t.py", ".plan/p.md", "junk.txt"]:
            (busy / rel).parent.mkdir(parents=True, exist_ok=True)
            (busy / rel).write_text("x")
        (done / "apps").mkdir()
        (done / "apps" / "y.ts").write_text("y")
        rows = lane.stop_all(self.repo)
        head = git(busy, "rev-parse", "HEAD")
        self.assertEqual(git(busy, "log", "-1", "--format=%s"), "T7.4: WIP (safe stop)")
        self.assertEqual(
            sorted(git(busy, "show", "--name-only", "--format=", "HEAD").split()),
            ["services/x.py", "tests/t.py"],
        )
        self.assertEqual(git(self.repo, "ls-remote", str(self.remote), "t7.4-x").split()[0], head)
        report = (busy / ".work" / "T7.4" / "lane-report.yaml").read_text(encoding="utf-8")
        self.assertIn("next:", report)
        self.assertIn("junk.txt", git(busy, "status", "--short"))  # left alone
        self.assertEqual(git(done, "log", "-1", "--format=%s"), "a")  # done lane untouched
        self.assertTrue(any("T7.4" in r and head[:7] in r for r in rows))

    def test_stop_all_without_changes_does_not_commit_and_keeps_next(self) -> None:
        busy = self.lane(1, "T7.6", "in_progress")
        report = busy / ".work" / "T7.6" / "lane-report.yaml"
        report.write_text("status: in_progress\nnext: write test X\n", encoding="utf-8")
        lane.stop_all(self.repo)
        self.assertEqual(git(busy, "log", "-1", "--format=%s"), "a")
        self.assertEqual(report.read_text(encoding="utf-8").count("next:"), 1)

    # -- W6 gc
    def test_gc_removes_merged_clean_worktrees_and_keeps_the_rest(self) -> None:
        merged = self.lane(4, "T9.7a", "done", "L4-t97a")
        dirty = self.lane(5, "T9.8", "done")
        (dirty / "new.txt").write_text("x")
        open_pr = self.lane(1, "T7.6", "in_progress")
        scratch = self.repo.parent / "scratch" / "wt-mut"
        git(self.repo, "worktree", "add", "-q", "--detach", str(scratch), "main")
        rows = lane.gc(self.repo, merged=lambda branch, _repo: branch in ("t9.7a-x", "t9.8-x"),
                       scratch=[self.repo.parent / "scratch"])  # fmt: skip
        self.assertFalse(merged.exists())
        self.assertFalse(scratch.exists())
        self.assertTrue(dirty.exists())
        self.assertTrue(open_pr.exists())
        text = "\n".join(rows)
        self.assertIn("removed", text)
        self.assertIn("dirty", text)
        self.assertNotIn(str(self.repo) + " ", text)  # the main checkout is never listed

    def test_gc_brings_worktree_evidence_home_before_removing(self) -> None:
        # .work/ is gitignored, so a clean worktree may still hold the only copy of the evidence
        merged = self.lane(4, "T9.7a", "done", "L4-t97a")
        (merged / ".work" / "T9.7a" / "review.yaml").write_text("verdict: merge\n")
        lane.gc(self.repo, merged=lambda *_: True, scratch=[])
        self.assertFalse(merged.exists())
        home = self.repo / ".work" / "T9.7a"
        self.assertEqual(
            sorted(p.name for p in home.iterdir()), ["card.yaml", "lane-report.yaml", "review.yaml"]
        )

    def test_gc_keeps_a_detached_worktree_whose_commit_is_on_no_branch(self) -> None:
        scratch = self.repo.parent / "scratch" / "wt-mut"
        git(self.repo, "worktree", "add", "-q", "--detach", str(scratch), "main")
        (scratch / "b.txt").write_text("b")
        git(scratch, "add", "b.txt")
        git(scratch, "commit", "-q", "-m", "orphan")
        lane.gc(self.repo, merged=lambda *_: False, scratch=[self.repo.parent / "scratch"])
        self.assertTrue(scratch.exists())

    # -- W7 up + env --for-review
    def test_up_syncs_both_services(self) -> None:
        calls: list[tuple[str, ...]] = []
        lane.up(self.repo, 2, "t1-x", base="main", create_db=False,
                sync=lambda path: calls.append(lane.uv_sync_targets(path)) or [])  # fmt: skip
        self.assertEqual(len(calls), 1)
        self.assertEqual([Path(p).name for p in calls[0]], ["core-api", "ai-service"])

    def test_env_for_review_uses_the_owning_lane(self) -> None:
        busy = self.lane(3, "T7.4", "in_progress", "L3-t74")
        env = lane.review_env(self.repo, busy / "services")
        self.assertEqual(env, lane.lane_env(3))
        with self.assertRaises(ValueError):
            lane.review_env(self.repo, self.repo.parent)
