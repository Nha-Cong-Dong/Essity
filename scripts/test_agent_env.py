"""Tests for agent_env.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import unittest

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
    def test_redis_db_is_stable_and_leaves_dev_and_shared_test_dbs_alone(self) -> None:
        # 0 holds local data, 15 is the shared test db (conftest default).
        for agent in ["coder-s1", "coder-s2", "tester-t2.13", "reviewer-s5", "a"]:
            db = redis_db(agent)
            self.assertEqual(db, redis_db(agent))
            self.assertIn(db, range(1, 15))


class Env(unittest.TestCase):
    def test_bash_lines_export_both_urls(self) -> None:
        lines = env_lines("coder-s2", "bash")
        self.assertIn(
            "export CORE_TEST_DATABASE_URL="
            "postgresql+psycopg://core:change-me-local@127.0.0.1:5432/core_test_coder_s2",
            lines,
        )
        self.assertIn(
            f"export CORE_TEST_REDIS_URL=redis://127.0.0.1:6379/{redis_db('coder-s2')}", lines
        )

    def test_powershell_lines_set_env(self) -> None:
        lines = env_lines("coder-s2", "powershell")
        self.assertTrue(all(line.startswith("$env:") for line in lines), lines)

    def test_the_database_is_created_by_the_superuser_and_owned_by_core(self) -> None:
        # `core` has no CREATEDB (R32), so the superuser creates it.
        command = create_database_command("core_test_coder_s2")
        self.assertEqual(command[:4], ["docker", "exec", "essity-postgres-1", "psql"])
        self.assertIn('CREATE DATABASE "core_test_coder_s2" OWNER core', command[-1])


if __name__ == "__main__":
    unittest.main()
