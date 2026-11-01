"""Tests for wt_remove.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import stat

from wt_remove import check_removable, sweep_leftover, unlink_links


EXT = r"\\?" + "\\"  # extended-length path prefix


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


class SweepLeftover(unittest.TestCase):
    def setUp(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.outside = base / "main-repo"
        self.outside.mkdir()
        (self.outside / "keep.txt").write_text("main repo file")
        self.tree = base / "left"
        (self.tree / "node_modules").mkdir(parents=True)

    def test_read_only_files_links_and_deep_paths_go_but_link_targets_stay(self) -> None:
        make_dir_link(self.tree / "node_modules" / "api-client", self.outside)
        locked = self.tree / "ro.txt"
        locked.write_text("x")
        os.chmod(locked, stat.S_IREAD)
        deep = self.tree / "node_modules" / "/".join(["d" * 40] * 8)
        deep_path = Path((EXT if sys.platform == "win32" else "") + str(deep))
        deep_path.mkdir(parents=True)
        self.assertIsNone(sweep_leftover(self.tree))
        self.assertFalse(self.tree.exists())
        self.assertEqual((self.outside / "keep.txt").read_text(), "main repo file")

    def test_a_folder_with_a_git_entry_is_never_swept(self) -> None:
        (self.tree / ".git").write_text("gitdir: elsewhere")
        self.assertIn(".git", sweep_leftover(self.tree) or "")
        self.assertTrue(self.tree.exists())

    def test_a_lane_folder_that_is_a_link_is_refused_and_its_target_survives(self) -> None:
        base = Path(tempfile.mkdtemp())
        repo = base / "repo"
        root = repo / ".claude" / "worktrees"
        root.mkdir(parents=True)
        target = base / "precious"
        (target / "node_modules").mkdir(parents=True)
        (target / "sentinel.txt").write_text("keep")
        make_dir_link(root / "L1", target)
        self.assertIn("link", sweep_leftover(root / "L1", repo) or "")
        self.assertIn("link", sweep_leftover(root / "L1") or "")
        with self.assertRaises(ValueError):
            check_removable(root / "L1", repo, [])
        self.assertEqual((target / "sentinel.txt").read_text(), "keep")
        self.assertTrue((target / "node_modules").exists())

    def test_a_path_outside_the_worktrees_root_is_refused(self) -> None:
        base = Path(tempfile.mkdtemp())
        repo = base / "repo"
        (repo / ".claude" / "worktrees").mkdir(parents=True)
        outside = base / "elsewhere"
        outside.mkdir()
        (outside / "f.txt").write_text("x")
        self.assertIn("refused", sweep_leftover(outside, repo) or "")
        self.assertIn("refused", sweep_leftover(repo / ".claude" / "worktrees", repo) or "")
        self.assertIn("refused", sweep_leftover(repo, repo) or "")
        self.assertTrue((outside / "f.txt").exists())

    def test_a_folder_inside_the_root_is_swept(self) -> None:
        base = Path(tempfile.mkdtemp())
        repo = base / "repo"
        left = repo / ".claude" / "worktrees" / "L1"
        left.mkdir(parents=True)
        (left / "a.txt").write_text("x")
        self.assertIsNone(sweep_leftover(left, repo))
        self.assertFalse(left.exists())

    def test_a_missing_folder_is_fine(self) -> None:
        self.assertIsNone(sweep_leftover(self.tree / "nope"))


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
