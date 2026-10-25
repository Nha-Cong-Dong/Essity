"""The two Python services keep their own copy of the event models (`messaging/envelope.py`, no
cross-service imports, ADR-0003). This keeps the copies identical apart from the module
docstring, so a fix to what an event may carry cannot land in one service only (T4.1)."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "services/core-api/src/core_api/messaging/envelope.py"
AI = ROOT / "services/ai-service/src/ai_service/messaging/envelope.py"


def without_docstring(source: str) -> str:
    """`source` after its module docstring."""
    first = ast.parse(source).body[0]
    if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)):
        raise AssertionError("envelope.py should start with a module docstring")
    assert first.end_lineno is not None
    return "\n".join(source.splitlines()[first.end_lineno :])


class EnvelopeModulesInSync(unittest.TestCase):
    def test_copies_match_apart_from_docstring(self) -> None:
        # Red when: one service's envelope.py changes and the other's does not.
        core = without_docstring(CORE.read_text("utf-8"))
        ai = without_docstring(AI.read_text("utf-8"))
        self.assertEqual(core, ai, "envelope.py differs between core-api and ai-service")

    def test_the_comparison_sees_the_code(self) -> None:
        # Red when: stripping the docstring strips everything, so any two files would match.
        self.assertIn("def parse_event", without_docstring(CORE.read_text("utf-8")))
        self.assertEqual(without_docstring('"""a"""\nx = 1\n'), "x = 1")


if __name__ == "__main__":
    unittest.main()
