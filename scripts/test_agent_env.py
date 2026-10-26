"""Tests for agent_env.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import tempfile
import unittest
from pathlib import Path

from agent_env import create_database_command, database_name, env_lines, redis_db


class Names(unittest.TestCase):
    def test_the_database_is_named_after_the_agent(self) -> None:
        self.assertEqual(database_name("coder-s2"), "core_test_coder_s2")

    def test_odd_characters_and_case_are_folded(self) -> None:
        self.assertEqual(database_name("Tester T4.5"), "core_test_tester_t4_5")

    def test_a_long_name_fits_postgres(self) -> None:
        self.assertLessEqual(len(database_name("x" * 200)), 63)

    def test_an_empty_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            database_name("--")


class Redis(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = Path(tempfile.mkdtemp()) / "redis-dbs.json"

    def test_each_agent_gets_its_own_db_and_keeps_it(self) -> None:
        # A hash could give two agents the same db, and one suite's flush breaks the other (R32).
        dbs = [redis_db(f"agent-{i}", self.registry) for i in range(14)]
        self.assertEqual(len(set(dbs)), 14)
        self.assertEqual(redis_db("agent-3", self.registry), dbs[3])

    def test_dev_and_shared_test_dbs_are_never_given(self) -> None:
        # 0 holds local data, 15 is the shared test db (conftest default).
        dbs = {redis_db(f"a{i}", self.registry) for i in range(14)}
        self.assertEqual(dbs, set(range(1, 15)))

    def test_a_fifteenth_agent_is_refused(self) -> None:
        for i in range(14):
            redis_db(f"a{i}", self.registry)
        with self.assertRaises(RuntimeError):
            redis_db("one-too-many", self.registry)


class Env(unittest.TestCase):
    def test_bash_lines_export_both_urls(self) -> None:
        lines = env_lines("coder-s2", "bash", redis=3)
        self.assertIn(
            "export CORE_TEST_DATABASE_URL="
            "postgresql+psycopg://core:change-me-local@127.0.0.1:5432/core_test_coder_s2",
            lines,
        )
        self.assertIn("export CORE_TEST_REDIS_URL=redis://127.0.0.1:6379/3", lines)

    def test_powershell_lines_set_env(self) -> None:
        lines = env_lines("coder-s2", "powershell", redis=3)
        self.assertTrue(all(line.startswith("$env:") for line in lines), lines)

    def test_the_database_is_created_by_the_superuser_and_owned_by_core(self) -> None:
        # `core` has no CREATEDB (R32), so the superuser creates it.
        command = create_database_command("core_test_coder_s2")
        self.assertEqual(command[:4], ["docker", "exec", "essity-postgres-1", "psql"])
        self.assertIn('CREATE DATABASE "core_test_coder_s2" OWNER core', command[-1])


if __name__ == "__main__":
    unittest.main()
