"""Tests for scripts/gen_api_client.py (subprocess mocked)."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import gen_api_client as g  # noqa: E402


def _make_repo(base: Path, *, with_modules: bool = True) -> Path:
    api = base / "packages" / "api-client"
    api.mkdir(parents=True)
    generate = "openapi-typescript openapi.json --output src/schema.d.ts"
    (api / "package.json").write_text(json.dumps({"scripts": {"generate": generate}}))
    (base / "apps" / "web").mkdir(parents=True)
    if with_modules:
        ots = api / "node_modules" / "openapi-typescript"
        (ots / "bin").mkdir(parents=True)
        (ots / "bin" / "cli.js").write_text("")
        (ots / "package.json").write_text(json.dumps({"bin": {"openapi-typescript": "bin/cli.js"}}))
        web = base / "apps" / "web" / "node_modules"
        (web / "next" / "dist" / "bin").mkdir(parents=True)
        (web / "next" / "dist" / "bin" / "next").write_text("")
        (web / "next" / "package.json").write_text(json.dumps({"bin": {"next": "dist/bin/next"}}))
        (web / "typescript" / "bin").mkdir(parents=True)
        (web / "typescript" / "bin" / "tsc").write_text("")
        (web / "typescript" / "package.json").write_text(json.dumps({"bin": {"tsc": "bin/tsc"}}))
    return base


class Recorder:
    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, cmd: list[str], cwd: Path | None = None) -> int:
        self.calls.append((cmd, cwd))
        return self.code


class GenApiClient(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def test_generate_command_read_from_package_json(self) -> None:
        root = _make_repo(self.base)
        self.assertEqual(g.generate_args(root), ["openapi.json", "--output", "src/schema.d.ts"])

    def test_resolve_bin(self) -> None:
        root = _make_repo(self.base)
        api = root / "packages" / "api-client"
        with contextlib.redirect_stderr(io.StringIO()):
            got = g.resolve_bin(api, "openapi-typescript", "openapi-typescript", root)
        self.assertEqual(got.name, "cli.js")
        self.assertTrue(got.is_file())

    def test_resolve_bin_reports_chosen_root(self) -> None:
        root = _make_repo(self.base)
        api = root / "packages" / "api-client"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            g.resolve_bin(api, "openapi-typescript", "openapi-typescript", root)
        self.assertIn(str(api), err.getvalue())

    def test_resolve_bin_missing_raises(self) -> None:
        root = _make_repo(self.base, with_modules=False)
        api = root / "packages" / "api-client"
        with self.assertRaises(g.GenError):
            g.resolve_bin(api, "openapi-typescript", "openapi-typescript", root)

    def test_generate_steps(self) -> None:
        root = _make_repo(self.base)
        run = Recorder()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(g.generate(root, run=run), 0)
        self.assertEqual(len(run.calls), 2)
        dump = run.calls[0][0]
        core = str(root / "services" / "core-api")
        self.assertEqual(dump[:6], ["uv", "run", "--directory", core, "--no-sync", "python"])
        self.assertEqual(dump[-1], str(root / "packages" / "api-client" / "openapi.json"))
        node, cwd = run.calls[1]
        self.assertEqual(node[0], "node")
        self.assertTrue(node[1].endswith("cli.js"))
        self.assertEqual(node[2:], ["openapi.json", "--output", "src/schema.d.ts"])
        self.assertEqual(cwd, root / "packages" / "api-client")

    def test_generate_stops_on_dump_failure(self) -> None:
        root = _make_repo(self.base)
        run = Recorder(3)
        self.assertEqual(g.generate(root, run=run), 3)
        self.assertEqual(len(run.calls), 1)

    def test_typecheck_steps_use_with_lock_web(self) -> None:
        root = _make_repo(self.base)
        run = Recorder()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(g.typecheck(root, run=run), 0)
        self.assertEqual(len(run.calls), 2)
        for cmd, cwd in run.calls:
            self.assertTrue(cmd[1].endswith("with_lock.py"))
            self.assertEqual(cmd[2:5], ["web", "--", "node"])
            self.assertEqual(cwd, root / "apps" / "web")
        self.assertTrue(run.calls[0][0][5].endswith("next"))
        self.assertEqual(run.calls[0][0][6:], ["typegen"])
        self.assertTrue(run.calls[1][0][5].endswith("tsc"))
        self.assertEqual(run.calls[1][0][6:], ["--noEmit"])

    def test_typecheck_returns_first_failure(self) -> None:
        root = _make_repo(self.base)
        run = Recorder(1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(g.typecheck(root, run=run), 1)
        self.assertEqual(len(run.calls), 1)

    def test_main_flag_runs_both(self) -> None:
        root = _make_repo(self.base)
        with (
            mock.patch.object(g, "generate", return_value=0) as gen,
            mock.patch.object(g, "typecheck", return_value=0) as tc,
        ):
            self.assertEqual(g.main(["--typecheck"], root=root), 0)
            gen.assert_called_once()
            tc.assert_called_once()
            gen.reset_mock()
            tc.reset_mock()
            self.assertEqual(g.main([], root=root), 0)
            gen.assert_called_once()
            tc.assert_not_called()

    def test_main_gen_failure_skips_typecheck(self) -> None:
        root = _make_repo(self.base)
        with (
            mock.patch.object(g, "generate", return_value=4),
            mock.patch.object(g, "typecheck") as tc,
        ):
            self.assertEqual(g.main(["--typecheck"], root=root), 4)
            tc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
