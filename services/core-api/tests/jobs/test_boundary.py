import re
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE = Path(__file__).parents[2]
JOBS = SERVICE / "src" / "core_api" / "jobs"


@pytest.mark.parametrize("module", sorted(path.stem for path in JOBS.glob("*.py")))
def test_each_jobs_module_imports_on_its_own(module: str) -> None:
    # A fresh interpreter per module: in the test process, whatever was imported first would
    # hide an import cycle (handler modules import `queue`, which loads every handler).
    name = "core_api.jobs" if module == "__init__" else f"core_api.jobs.{module}"
    result = subprocess.run(
        [sys.executable, "-c", f"import {name}"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_only_the_jobs_package_imports_procrastinate() -> None:
    importers = {
        path.relative_to(SERVICE).as_posix()
        for folder in ("src", "migrations", "tests")
        for path in (SERVICE / folder).rglob("*.py")
        if JOBS not in path.parents
        and re.search(r"^\s*(import|from) procrastinate\b", path.read_text("utf-8"), re.M)
    }
    assert importers == set()
