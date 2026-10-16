"""The two Python services keep their own copy of logging.py and telemetry.py (no
cross-service imports, ADR-0003). This keeps the copies identical apart from the package name,
so a fix to what may be logged or traced cannot land in one service only."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "services/core-api/src/core_api"
AI = ROOT / "services/ai-service/src/ai_service"
SHARED = ("logging.py", "telemetry.py")


class LoggingModulesInSync(unittest.TestCase):
    def test_copies_match_apart_from_package_name(self) -> None:
        for name in SHARED:
            with self.subTest(name):
                core = (CORE / name).read_text("utf-8").replace("core_api", "<package>")
                ai = (AI / name).read_text("utf-8").replace("ai_service", "<package>")
                self.assertEqual(core, ai, f"{name} differs between core-api and ai-service")


if __name__ == "__main__":
    unittest.main()
