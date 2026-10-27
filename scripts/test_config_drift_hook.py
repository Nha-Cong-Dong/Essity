"""Tests for hooks/config_drift.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "hooks"))

from config_drift import main_checkout, run


class MainCheckout(unittest.TestCase):
    def test_lane_worktree_resolves_to_the_checkout_holding_it(self) -> None:
        root = Path(tempfile.mkdtemp()) / "Essity"
        lane = root / ".claude" / "worktrees" / "L1" / "apps"
        lane.mkdir(parents=True)
        self.assertEqual(main_checkout(lane), root.resolve())

    def test_main_checkout_is_itself(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.assertEqual(main_checkout(root), root.resolve())


class Run(unittest.TestCase):
    def test_without_private_docs_the_hook_is_silent(self) -> None:
        # CI and other clones have no docs/ (a separate private repository).
        self.assertEqual(run(Path(tempfile.mkdtemp())), "")

    def test_delegates_to_the_docs_tool(self) -> None:
        root = Path(tempfile.mkdtemp())
        tool = root / "docs" / "_tools" / "config_drift.py"
        tool.parent.mkdir(parents=True)
        tool.write_text(
            "import sys\nprint('drift', ' '.join(sys.argv[1:]))\n", encoding="utf-8"
        )
        out = run(root)
        self.assertIn("drift", out)
        self.assertIn("--hook", out)
        self.assertIn(str(root), out)

    def test_broken_tool_output_does_not_raise(self) -> None:
        root = Path(tempfile.mkdtemp())
        tool = root / "docs" / "_tools" / "config_drift.py"
        tool.parent.mkdir(parents=True)
        tool.write_text(
            "import sys\nsys.stdout.buffer.write(b'bad \\xff byte')\nsys.exit(3)\n",
            encoding="utf-8",
        )
        self.assertIn("bad", run(root))


if __name__ == "__main__":
    unittest.main()
