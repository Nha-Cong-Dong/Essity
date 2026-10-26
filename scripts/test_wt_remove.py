"""Tests for wt_remove.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from wt_remove import check_removable, unlink_links


def make_dir_link(link: Path, target: Path) -> None:
    """A junction on Windows (what pnpm makes), a symlink elsewhere."""
    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True
        )
    else:
        os.symlink(target, link, target_is_directory=True)


class UnlinkLinks(unittest.TestCase):
    def setUp(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.outside = base / "main-repo"
        self.outside.mkdir()
        (self.outside / "keep.txt").write_text("main repo file")
        self.tree = base / "wt"
        (self.tree / "node_modules" / ".pnpm").mkdir(parents=True)
        (self.tree / "src.py").write_text("x")

    def test_links_go_and_what_they_point_at_stays(self) -> None:
        # R45: following a junction deleted packages/api-client in the main repo.
        make_dir_link(self.tree / "node_modules" / "api-client", self.outside)
        make_dir_link(self.tree / "root_modules", self.outside)
        removed = unlink_links(self.tree)
        self.assertEqual(len(removed), 2)
        self.assertFalse((self.tree / "root_modules").exists())
        self.assertTrue((self.outside / "keep.txt").exists())
        self.assertTrue((self.tree / "src.py").exists())

    def test_a_tree_without_links_is_untouched(self) -> None:
        self.assertEqual(unlink_links(self.tree), [])
        self.assertTrue((self.tree / "src.py").exists())


class CheckRemovable(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp()) / "Essity"
        (self.repo / ".claude" / "worktrees" / "agent-1").mkdir(parents=True)

    def test_a_worktree_under_claude_worktrees_may_go(self) -> None:
        check_removable(self.repo / ".claude" / "worktrees" / "agent-1", self.repo, [])

    def test_a_worktree_in_an_allowed_scratch_root_may_go(self) -> None:
        scratch = Path(tempfile.mkdtemp())
        (scratch / "wt-mut").mkdir()
        check_removable(scratch / "wt-mut", self.repo, [scratch])

    def test_the_main_repo_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            check_removable(self.repo, self.repo, [])

    def test_a_folder_inside_the_main_repo_is_refused(self) -> None:
        (self.repo / "packages").mkdir()
        with self.assertRaises(ValueError):
            check_removable(self.repo / "packages", self.repo, [])

    def test_the_worktrees_folder_itself_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            check_removable(self.repo / ".claude" / "worktrees", self.repo, [])


if __name__ == "__main__":
    unittest.main()
