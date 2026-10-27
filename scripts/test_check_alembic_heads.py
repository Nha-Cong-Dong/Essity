"""Tests for check_alembic_heads.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import tempfile
import unittest
from pathlib import Path

from check_alembic_heads import heads


def migration(folder: Path, revision: str, down: str | None) -> None:
    down_text = "None" if down is None else f'"{down}"'
    (folder / f"{revision}_x.py").write_text(
        f'revision: str = "{revision}"\ndown_revision: str | Sequence[str] | None = {down_text}\n',
        encoding="utf-8",
    )


class Heads(unittest.TestCase):
    def setUp(self) -> None:
        self.versions = Path(tempfile.mkdtemp())

    def test_a_straight_chain_has_one_head(self) -> None:
        migration(self.versions, "0001", None)
        migration(self.versions, "0002", "0001")
        self.assertEqual(heads(self.versions), ["0002"])

    def test_two_branches_off_one_revision_are_two_heads(self) -> None:
        # What two lanes writing "0011" on top of 0010 produce (PR D and PR E, 26/10).
        migration(self.versions, "0010", None)
        migration(self.versions, "0011a", "0010")
        migration(self.versions, "0011b", "0010")
        self.assertEqual(heads(self.versions), ["0011a", "0011b"])

    def test_a_merge_revision_joins_two_heads(self) -> None:
        migration(self.versions, "0010", None)
        migration(self.versions, "0011a", "0010")
        migration(self.versions, "0011b", "0010")
        (self.versions / "0012_merge.py").write_text(
            'revision: str = "0012"\ndown_revision = ("0011a", "0011b")\n', encoding="utf-8"
        )
        self.assertEqual(heads(self.versions), ["0012"])

    def test_the_real_chains_have_one_head_each(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for service in ["core-api", "ai-service"]:
            versions = root / "services" / service / "migrations" / "versions"
            self.assertEqual(len(heads(versions)), 1, service)


if __name__ == "__main__":
    unittest.main()
