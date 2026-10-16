"""Tests for check_licenses.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import json
import unittest

from check_licenses import Package, pnpm_packages, verdict

COPYLEFT = "copyleft (GPL/AGPL)"


def spdx(text: str) -> str | None:
    return verdict(Package("pkg", "1.0", text, spdx=True))


def free_text(text: str) -> str | None:
    return verdict(Package("pkg", "1.0", text, spdx=False))


class SpdxExpressions(unittest.TestCase):
    def test_gpl_and_agpl_are_rejected(self) -> None:
        for text in ["GPL-2.0-only", "GPL-3.0-or-later", "AGPL-3.0-only", "AGPL-3.0"]:
            self.assertEqual(spdx(text), COPYLEFT, text)

    def test_lgpl_is_allowed(self) -> None:
        for text in ["LGPL-2.1-only", "LGPL-3.0-or-later", "Apache-2.0 AND LGPL-3.0-or-later"]:
            self.assertIsNone(spdx(text), text)

    def test_or_lets_us_pick_the_permissive_option(self) -> None:
        self.assertIsNone(spdx("(MIT OR GPL-3.0-or-later)"))

    def test_and_with_gpl_is_rejected(self) -> None:
        self.assertEqual(spdx("GPL-2.0-only AND MIT"), COPYLEFT)

    def test_permissive_licenses_are_allowed(self) -> None:
        for text in ["MIT", "Apache-2.0", "BSD-3-Clause", "MPL-2.0", "ISC", "0BSD"]:
            self.assertIsNone(spdx(text), text)


class FreeText(unittest.TestCase):
    def test_pymupdf_is_rejected(self) -> None:
        # PyMuPDF 1.28.2 metadata: the reason for this check (ADR-0011).
        text = (
            "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License; "
            "GNU Affero General Public License v3"
        )
        self.assertEqual(free_text(text), COPYLEFT)

    def test_gpl_classifier_is_rejected(self) -> None:
        self.assertEqual(free_text("GNU General Public License v3 (GPLv3)"), COPYLEFT)

    def test_lgpl_classifiers_are_allowed(self) -> None:
        for text in [
            "GNU Library or Lesser General Public License (LGPL)",
            "GNU Lesser General Public License v3 (LGPLv3)",
            "GNU Lesser General Public License v3 or later (LGPLv3+)",
        ]:
            self.assertIsNone(free_text(text), text)

    def test_or_in_free_text_is_not_trusted(self) -> None:
        self.assertEqual(free_text("MIT or GPL"), COPYLEFT)


class MissingLicense(unittest.TestCase):
    def test_missing_or_unknown_is_rejected(self) -> None:
        for text in ["", "UNKNOWN", "Unknown", "SEE LICENSE IN LICENSE.md"]:
            self.assertEqual(spdx(text), "no license information", text)


class PnpmReport(unittest.TestCase):
    def test_each_version_becomes_a_package(self) -> None:
        report = json.dumps(
            {
                "MIT": [{"name": "a", "versions": ["1.0.0", "2.0.0"]}],
                "GPL-3.0": [{"name": "b", "versions": ["3.0.0"]}],
            }
        )
        packages = pnpm_packages(report)
        self.assertEqual(
            [(p.name, p.version, p.license) for p in packages],
            [("a", "1.0.0", "MIT"), ("a", "2.0.0", "MIT"), ("b", "3.0.0", "GPL-3.0")],
        )
        self.assertEqual([verdict(p) for p in packages], [None, None, COPYLEFT])


if __name__ == "__main__":
    unittest.main()
