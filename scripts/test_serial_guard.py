"""Tests for hooks/serial_guard.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "hooks"))

from serial_guard import blocked_reason, owner_path, serial_target


class FastPath(unittest.TestCase):
    # Every Bash/Edit/Write runs the hook: calls that cannot touch a serial resource must be
    # answered before the ~90 ms `git rev-parse` that finds the repository.
    def test_ordinary_calls_have_no_serial_target(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        self.assertIsNone(serial_target("Bash", {"command": "uv run pytest -q"}, cwd))
        self.assertIsNone(serial_target("Edit", {"file_path": str(cwd / "app.py")}, cwd))
        self.assertIsNone(serial_target("Read", {"file_path": "x"}, cwd))

    def test_serial_calls_name_where_they_act(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        self.assertEqual(serial_target("Bash", {"command": "just gen-api"}, cwd), cwd.resolve())
        migration = cwd / "services" / "core-api" / "migrations" / "versions" / "0012_x.py"
        self.assertEqual(
            serial_target("Write", {"file_path": str(migration)}, cwd),
            migration.resolve(),
        )


class Guard(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp()) / "Essity"
        self.l1 = self.repo / ".claude" / "worktrees" / "L1"
        self.l2 = self.repo / ".claude" / "worktrees" / "L2"
        for path in [self.l1, self.l2]:
            path.mkdir(parents=True)

    def bash(self, command: str, cwd: Path) -> str | None:
        return blocked_reason("Bash", {"command": command}, cwd, self.repo)

    def edit(self, file_path: Path, cwd: Path) -> str | None:
        return blocked_reason("Write", {"file_path": str(file_path)}, cwd, self.repo)

    def test_the_default_owner_is_lane_1(self) -> None:
        self.assertEqual(owner_path(self.repo), self.l1.resolve())

    def test_a_new_migration_outside_the_owner_is_blocked(self) -> None:
        reason = self.bash("cd services/core-api && uv run alembic revision -m x", self.l2)
        self.assertIsNotNone(reason)
        self.assertIn("L1", reason or "")

    def test_the_owner_may_create_a_migration(self) -> None:
        self.assertIsNone(self.bash("uv run alembic revision --autogenerate -m x", self.l1))

    def test_regenerating_the_api_client_outside_the_owner_is_blocked(self) -> None:
        self.assertIsNotNone(self.bash("bash scripts/gen_api_client.sh", self.l2))

    def test_other_ways_to_regenerate_the_client_are_blocked(self) -> None:
        for command in [
            "just gen-api",
            "cd packages/api-client && pnpm generate",
            "pnpm --filter api-client generate",
            "npx openapi-typescript openapi.json --output src/schema.d.ts",
        ]:
            self.assertIsNotNone(self.bash(command, self.l2), command)

    def test_writing_the_exported_openapi_outside_the_owner_is_blocked(self) -> None:
        self.assertIsNotNone(
            self.edit(self.l2 / "packages" / "api-client" / "openapi.json", self.l2)
        )

    def test_ordinary_commands_pass_anywhere(self) -> None:
        for command in [
            "uv run alembic upgrade head",
            "uv run pytest -q",
            "git status",
            "pnpm --filter web test",
            "git log --grep revision",
        ]:
            self.assertIsNone(self.bash(command, self.l2), command)

    def test_writing_a_migration_file_outside_the_owner_is_blocked(self) -> None:
        target = self.l2 / "services" / "core-api" / "migrations" / "versions" / "0012_x.py"
        self.assertIsNotNone(self.edit(target, self.l2))

    def test_writing_the_generated_client_outside_the_owner_is_blocked(self) -> None:
        target = self.l2 / "packages" / "api-client" / "src" / "schema.ts"
        self.assertIsNotNone(self.edit(target, self.l2))

    def test_writing_ordinary_files_passes(self) -> None:
        self.assertIsNone(self.edit(self.l2 / "apps" / "web" / "page.tsx", self.l2))

    # RETRO-FIX1: decide from what the command runs and where it acts, not from its text.
    def test_commands_that_only_mention_a_protected_one_pass(self) -> None:
        for command in [
            'echo "run just gen-api later"',
            "grep -rn 'alembic revision' docs",
            "cat <<'EOF' > .work/T1/card.yaml\nscope: just gen-api, alembic revision\nEOF",
            'git commit -m "document alembic revision rules"',
            "ls packages/api-client/src",
        ]:
            self.assertIsNone(self.bash(command, self.repo), command)

    def test_writes_under_dot_work_are_never_blocked(self) -> None:
        target = self.repo / ".work" / "T1" / "services" / "core-api" / "migrations" / "versions"
        self.assertIsNone(self.edit(target / "x.md", self.l2))
        self.assertIsNone(self.bash("echo hi > .work/T1/notes.md", self.l2))

    def test_the_worktree_comes_from_the_command_not_the_process_cwd(self) -> None:
        # agents run from the main checkout
        self.assertIsNone(
            self.bash(
                f"git -C {self.l1} status && cd {self.l1} && alembic revision -m x",
                self.repo,
            )
        )
        self.assertIsNotNone(self.bash(f"cd {self.l2} && uv run alembic revision -m x", self.l1))
        self.assertIsNotNone(self.bash(f"git -C {self.l2} rev-parse && just gen-api", self.l2))
        self.assertIsNotNone(self.bash(f"cd {self.l2} && uv run alembic revision -m x", self.repo))

    def test_redirect_into_a_protected_path_is_blocked(self) -> None:
        self.assertIsNotNone(
            self.bash("echo x > services/core-api/migrations/versions/0099_x.py", self.l2)
        )

    def test_chained_real_command_after_a_harmless_one_is_blocked(self) -> None:
        self.assertIsNotNone(self.bash("echo hi && uv run alembic revision -m x", self.l2))

    def test_readers_cannot_hide_a_protected_command(self) -> None:
        for command in [
            "echo $(alembic revision -m x)",
            "echo `alembic revision -m x`",
            "cat <(alembic revision -m x)",
            "find . -exec alembic revision {} +",
            "git -c alias.x='!alembic revision' x",
            'bash -c "alembic revision -m x"',
        ]:
            self.assertIsNotNone(self.bash(command, self.l2), command)

    def test_readers_with_substitutions_of_harmless_commands_pass(self) -> None:
        self.assertIsNone(self.bash("echo $(git rev-parse HEAD) `date`", self.l2))

    def test_writers_and_glued_redirects_into_protected_paths_are_blocked(self) -> None:
        versions = "services/core-api/migrations/versions/0030_a.py"
        for command in [
            f"echo x>{versions}",
            f"echo x | tee {versions}",
            f"cp /tmp/a.py {versions}",
            f"sed -i s/a/b/ {versions}",
        ]:
            self.assertIsNotNone(self.bash(command, self.l2), command)

    def test_the_orchestrator_can_hand_the_lock_to_another_checkout(self) -> None:
        # PR D lives in the main checkout: the orchestrator writes .work/serial-owner to let it
        # fix its own migration without moving the branch to L1.
        (self.repo / ".work").mkdir()
        (self.repo / ".work" / "serial-owner").write_text(str(self.repo), encoding="utf-8")
        self.assertIsNone(self.bash("uv run alembic revision -m x", self.repo))
        self.assertIsNotNone(self.bash("uv run alembic revision -m x", self.l1))


if __name__ == "__main__":
    unittest.main()
