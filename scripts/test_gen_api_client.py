"""Tests for scripts/gen_api_client.py (subprocess mocked)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import gen_api_client as g  # noqa: E402


def _make_repo(tmp_path: Path, *, with_modules: bool = True) -> Path:
    api = tmp_path / "packages" / "api-client"
    api.mkdir(parents=True)
    (api / "package.json").write_text(
        json.dumps(
            {"scripts": {"generate": "openapi-typescript openapi.json --output src/schema.d.ts"}}
        )
    )
    (tmp_path / "apps" / "web").mkdir(parents=True)
    if with_modules:
        cli = api / "node_modules" / "openapi-typescript" / "bin"
        cli.mkdir(parents=True)
        (cli / "cli.js").write_text("")
        (api / "node_modules" / "openapi-typescript" / "package.json").write_text(
            json.dumps({"bin": {"openapi-typescript": "bin/cli.js"}})
        )
        web = tmp_path / "apps" / "web" / "node_modules"
        (web / "next" / "dist" / "bin").mkdir(parents=True)
        (web / "next" / "dist" / "bin" / "next").write_text("")
        (web / "next" / "package.json").write_text(json.dumps({"bin": {"next": "dist/bin/next"}}))
        (web / "typescript" / "bin").mkdir(parents=True)
        (web / "typescript" / "bin" / "tsc").write_text("")
        (web / "typescript" / "package.json").write_text(json.dumps({"bin": {"tsc": "bin/tsc"}}))
    return tmp_path


def test_generate_command_read_from_package_json(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    assert g.generate_args(root) == ["openapi.json", "--output", "src/schema.d.ts"]


def test_resolve_bin(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    got = g.resolve_bin(
        root / "packages" / "api-client", "openapi-typescript", "openapi-typescript", root
    )
    assert got.name == "cli.js" and got.is_file()


def test_resolve_bin_reports_chosen_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _make_repo(tmp_path)
    api = root / "packages" / "api-client"
    g.resolve_bin(api, "openapi-typescript", "openapi-typescript", root)
    assert str(api) in capsys.readouterr().err


def test_resolve_bin_missing_raises(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, with_modules=False)
    with pytest.raises(g.GenError):
        g.resolve_bin(
            root / "packages" / "api-client", "openapi-typescript", "openapi-typescript", root
        )


def test_generate_steps(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    calls: list[tuple[list[str], Path | None]] = []

    def fake(cmd: list[str], cwd: Path | None = None) -> int:
        calls.append((cmd, cwd))
        return 0

    assert g.generate(root, run=fake) == 0
    assert len(calls) == 2
    dump = calls[0][0]
    assert dump[:6] == [
        "uv",
        "run",
        "--directory",
        str(root / "services" / "core-api"),
        "--no-sync",
        "python",
    ]
    assert dump[-1] == str(root / "packages" / "api-client" / "openapi.json")
    assert calls[1][0][0] == "node"
    assert calls[1][0][1].endswith("cli.js")
    assert calls[1][0][2:] == ["openapi.json", "--output", "src/schema.d.ts"]
    assert calls[1][1] == root / "packages" / "api-client"


def test_generate_stops_on_dump_failure(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake(cmd: list[str], cwd: Path | None = None) -> int:
        calls.append(cmd)
        return 3

    assert g.generate(root, run=fake) == 3
    assert len(calls) == 1


def test_typecheck_steps_use_with_lock_web(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    calls: list[tuple[list[str], Path | None]] = []

    def fake(cmd: list[str], cwd: Path | None = None) -> int:
        calls.append((cmd, cwd))
        return 0

    assert g.typecheck(root, run=fake) == 0
    assert len(calls) == 2
    for cmd, cwd in calls:
        assert cmd[1].endswith("with_lock.py") and cmd[2:5] == ["web", "--", "node"]
        assert cwd == root / "apps" / "web"
    assert calls[0][0][5].endswith("next") and calls[0][0][6:] == ["typegen"]
    assert calls[1][0][5].endswith("tsc") and calls[1][0][6:] == ["--noEmit"]


def test_typecheck_returns_first_failure(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    calls: list[list[str]] = []

    def fake(cmd: list[str], cwd: Path | None = None) -> int:
        calls.append(cmd)
        return 1

    assert g.typecheck(root, run=fake) == 1
    assert len(calls) == 1


def test_main_flag_runs_both(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_repo(tmp_path)
    seen: list[str] = []
    monkeypatch.setattr(g, "generate", lambda r: seen.append("gen") or 0)
    monkeypatch.setattr(g, "typecheck", lambda r: seen.append("tc") or 0)
    assert g.main(["--typecheck"], root=root) == 0
    assert seen == ["gen", "tc"]
    seen.clear()
    assert g.main([], root=root) == 0
    assert seen == ["gen"]


def test_main_gen_failure_skips_typecheck(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_repo(tmp_path)
    monkeypatch.setattr(g, "generate", lambda r: 4)
    monkeypatch.setattr(g, "typecheck", lambda r: pytest.fail("must not run"))
    assert g.main(["--typecheck"], root=root) == 4
