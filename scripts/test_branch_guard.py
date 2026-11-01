"""Tests for hooks/branch_guard.py and its installation by lane.py."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "hooks"))
sys.path.insert(0, str(Path(__file__).parent))

import lane
from branch_guard import refusal


def _card(root: Path, task: str, lane_name: str, branch: str) -> None:
    folder = root / ".work" / task
    folder.mkdir(parents=True)
    (folder / "card.yaml").write_text(
        f"task: {task}\nlane: {lane_name}\nbranch: {branch}\n"
    )


class Refusal(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp()).resolve() / "Essity"
        self.l2 = self.repo / ".claude" / "worktrees" / "L2"
        self.l2.mkdir(parents=True)
        _card(self.repo, "T8.4", "L2", "t8.4-x")

    def test_commit_on_another_branch_is_refused(self) -> None:
        reason = refusal(self.repo, self.l2, "t9.8-pr-branch")
        self.assertIn("lane.py up L2", reason or "")

    def test_the_cards_branch_passes(self) -> None:
        self.assertIsNone(refusal(self.repo, self.l2, "t8.4-x"))

    def test_card_inside_the_worktree_counts(self) -> None:
        _card(self.l2, "T8.5", "L2", "t8.5-y")
        self.assertIsNone(refusal(self.repo, self.l2, "t8.5-y"))

    def test_other_lanes_cards_do_not_count(self) -> None:
        _card(self.repo, "T9.1", "L3", "t9.1-z")
        self.assertIsNotNone(refusal(self.repo, self.l2, "t9.1-z"))

    def test_no_card_detached_head_or_main_checkout_pass(self) -> None:
        l3 = self.repo / ".claude" / "worktrees" / "L3"
        l3.mkdir()
        self.assertIsNone(refusal(self.repo, l3, "anything"))
        self.assertIsNone(refusal(self.repo, self.l2, ""))
        self.assertIsNone(refusal(self.repo, self.repo, "main"))


class Install(unittest.TestCase):
    def test_up_installs_hooks_in_the_shared_hooks_dir(self) -> None:
        repo = Path(tempfile.mkdtemp()) / "r"
        repo.mkdir()
        for args in (
            ["init", "-q", "-b", "main"],
            ["commit", "-q", "--allow-empty", "-m", "i"],
        ):
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=t",
                    "-c",
                    "user.email=t@t",
                    *args,
                ],
                check=True,
            )
        lane.up(repo, 1, "t-x", base="main", create_db=False, sync=None)
        for name in ("pre-commit", "pre-push"):
            hook = repo / ".git" / "hooks" / name
            self.assertIn("branch_guard.py", hook.read_text())


if __name__ == "__main__":
    unittest.main()
