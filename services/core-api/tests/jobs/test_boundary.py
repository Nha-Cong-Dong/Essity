import re
from pathlib import Path

SERVICE = Path(__file__).parents[2]
JOBS = SERVICE / "src" / "core_api" / "jobs"


def test_only_the_jobs_package_imports_procrastinate() -> None:
    importers = {
        path.relative_to(SERVICE).as_posix()
        for folder in ("src", "migrations", "tests")
        for path in (SERVICE / folder).rglob("*.py")
        if JOBS not in path.parents
        and re.search(r"^\s*(import|from) procrastinate\b", path.read_text("utf-8"), re.M)
    }
    assert importers == set()
