"""Open and close the fixed lanes L1..L5 of the parallel workflow.

    python scripts/lane.py up L1 t2.23-skip-unit          # new branch from origin/main, or continue
    python scripts/lane.py up L3 t3.1-grade-evals --base origin/main
    python scripts/lane.py env L3 [--shell powershell]   # the lane's test databases and Redis db
    python scripts/lane.py env --for-review <worktree>   # same, for the lane owning that worktree
    python scripts/lane.py down L3                        # removes the folder; the branch stays
    python scripts/lane.py status [--stale]               # --stale: ages, STALE, ORPHAN
    python scripts/lane.py preflight                      # Docker, containers, free RAM, encoding
    python scripts/lane.py preflight T7.4                 # card's needs_schema exists on its base
    python scripts/lane.py stop-all                       # safe stop: WIP commit + push every lane
    python scripts/lane.py gc                             # remove merged, clean worktrees (+ docs)
    python scripts/lane.py next [--all] [--limit N]       # PR caps and which task to hand out next

A lane is a git worktree at `.claude/worktrees/L<n>` with its own test databases
`core_test_l<n>` and `ai_test_l<n>` and Redis db <n>. Fixed numbers mean nothing to hand out or
give back; agents outside a lane get Redis dbs 6..14 from `agent_env.py`. L1 is the integration
lane: the only one allowed to write migrations or regenerate the api-client
(`scripts/hooks/serial_guard.py`).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import flow
from agent_env import DATABASE_URL, REDIS_URL, ensure_database
from wt_remove import check_removable, unlink_links

LANES = range(1, 6)
DOCKER_BIN = Path("E:/Docker/Docker/resources/bin")
DOCKER_APP = Path("E:/Docker/Docker/Docker Desktop.exe")
CONTAINERS = ("essity-postgres-1", "essity-redis-1")
DOCKER_WAIT_SECONDS = 180
RAM_WARN_GB, RAM_STOP_GB = 3.0, 1.5
STALE_MINUTES = 45
MAX_OPEN_PRS, MAX_OPEN_RED_PRS = 3, 2
MIGRATION_HINTS = ("migration", "alembic", "contracts", "api-client")


def parse_lane(text: str) -> int:
    found = re.fullmatch(r"[Ll]([1-5])", text)
    if not found:
        raise ValueError(f"lane must be L1..L5, not {text!r}")
    return int(found.group(1))


def lane_path(repo: Path, lane: int) -> Path:
    return repo / ".claude" / "worktrees" / f"L{lane}"


def lane_env(lane: int) -> dict[str, str]:
    return {
        "CORE_TEST_DATABASE_URL": DATABASE_URL.format(name=f"core_test_l{lane}"),
        "AI_TEST_DATABASE_URL": DATABASE_URL.format(name=f"ai_test_l{lane}"),
        "CORE_TEST_REDIS_URL": REDIS_URL.format(db=lane),
    }


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
    )


SERVICES = ("core-api", "ai-service")


def uv_sync_targets(path: Path) -> tuple[str, ...]:
    return tuple(str(path / "services" / name) for name in SERVICES)


def uv_sync(path: Path) -> list[str]:
    """`uv sync` both services, so reviewers and testers in the worktree can run pytest (31/10: a
    fresh worktree had no sqlalchemy). Returns warnings; a failed sync does not undo `up`."""
    notes = []
    for target in uv_sync_targets(path):
        if not Path(target).exists():
            continue
        result = subprocess.run(
            ["uv", "sync", "--directory", target],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            notes.append(
                f"lane: uv sync failed in {target}: {result.stderr.strip()[-300:]}"
            )
    return notes


HOOK_TEMPLATE = """#!/bin/sh
# installed by lane.py up: a lane worktree may only commit/push on its card's branch
guard="{repo}/scripts/hooks/branch_guard.py"
[ -f "$guard" ] || exit 0
exec python "$guard" "{repo}"
"""


def install_branch_guard(repo: Path) -> None:
    """pre-commit and pre-push in the shared hooks dir (all worktrees), see branch_guard.py."""
    common = _git(
        repo, "rev-parse", "--path-format=absolute", "--git-common-dir"
    ).stdout.strip()
    hooks = Path(common) / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    for name in ("pre-commit", "pre-push"):
        hook = hooks / name
        if hook.exists() and "branch_guard.py" not in hook.read_text(encoding="utf-8"):
            continue  # someone else's hook: leave it alone
        hook.write_text(
            HOOK_TEMPLATE.format(repo=repo.as_posix()), encoding="utf-8", newline="\n"
        )
        hook.chmod(0o755)


def up(
    repo: Path,
    lane: int,
    branch: str,
    base: str = "origin/main",
    create_db: bool = True,
    sync: Callable[[Path], list[str]] | None = uv_sync,
) -> Path:
    path = lane_path(repo, lane)
    if path.exists():
        current = _git(path, "branch", "--show-current").stdout.strip()
        raise RuntimeError(
            f"L{lane} is in use (branch {current or '?'}); run `lane.py down L{lane}`"
        )
    exists = (
        _git(
            repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"
        ).returncode
        == 0
    )
    args = (
        ["worktree", "add", str(path), branch]
        if exists
        else ["worktree", "add", "-b", branch, str(path), base]
    )
    result = _git(repo, *args)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    install_branch_guard(repo)
    if create_db:
        # the superuser creates them (`core` has no CREATEDB), see agent_env.ensure_database
        ensure_database(f"core_test_l{lane}")
        ensure_database(f"ai_test_l{lane}")
    for note in sync(path) if sync else []:
        print(note, file=sys.stderr)
    return path


def _inside(path: Path, parent: Path) -> bool:
    path, parent = path.resolve(), parent.resolve()
    return path == parent or parent in path.parents


def review_env(repo: Path, where: Path) -> dict[str, str]:
    """Test env of the lane that owns `where`, for a reviewer or tester working in that worktree.

    The ad-hoc pool of `agent_env.py` (Redis dbs 6..14) ran out on 31/10; the lane's own
    databases are free while its lead waits on the reviewer.
    """
    for card_file in sorted((repo / ".work").glob("*/card.yaml")):
        card = flow.load(card_file) or {}
        worktree = str(card.get("worktree") or "")
        found = re.fullmatch(r"[Ll](\d+)", str(card.get("lane") or ""))
        if worktree and found and _inside(where, Path(worktree)):
            return lane_env(int(found.group(1)))
    root = repo / ".claude" / "worktrees"
    if _inside(where, root) and where.resolve() != root.resolve():
        name = where.resolve().relative_to(root.resolve()).parts[0]
        found = re.match(r"L(\d+)(?:-|$)", name)
        if found:
            return lane_env(int(found.group(1)))
    raise ValueError(
        f"no lane owns {where} (no card with that worktree, not .claude/worktrees/L<n>)"
    )


CODE_DIRS = ("services", "apps", "packages", "tests")


def _report_path(repo: Path, task: str, card: dict[str, Any]) -> Path | None:
    for place in flow.folders(repo / ".work", task, card):
        if (place / "lane-report.yaml").exists():
            return place / "lane-report.yaml"
    return None


def stop_all(repo: Path) -> list[str]:
    """Safe stop: in every lane whose report is `in_progress`, commit code dirs as WIP and push.

    Only services/ apps/ packages/ tests/ are staged: never .plan or stray files. Before 31/10 the
    orchestrator committed each lane's WIP by hand because agents stopped without committing.
    """
    rows = []
    for card_file in sorted((repo / ".work").glob("*/card.yaml")):
        task = card_file.parent.name
        card = flow.load(card_file) or {}
        report = _report_path(repo, task, card)
        doc = flow.load(report) if report else None
        if not report or not doc or doc.get("status") != "in_progress":
            continue
        worktree = Path(str(card.get("worktree") or ""))
        if not card.get("worktree") or not worktree.exists():
            rows.append(
                f"{card.get('lane', '?')}  {task}  worktree missing: {worktree}"
            )
            continue
        present = [d for d in CODE_DIRS if (worktree / d).exists()]
        if present:
            _git(worktree, "add", "--", *present)
        committed = _git(worktree, "diff", "--cached", "--quiet").returncode != 0
        if committed:
            _git(worktree, "commit", "-q", "-m", f"{task}: WIP (safe stop)")
        pushed = _git(worktree, "push", "-q", "origin", "HEAD").returncode == 0
        head = _git(worktree, "rev-parse", "--short", "HEAD").stdout.strip()
        if "next" not in doc:
            text = report.read_text(encoding="utf-8")
            text += (
                "" if text.endswith("\n") else "\n"
            ) + f'next: "resume from {head} (safe stop)"\n'
            report.write_text(text, encoding="utf-8")
        branch = _git(worktree, "branch", "--show-current").stdout.strip()
        rows.append(
            f"{card.get('lane', '?')}  {task}  {branch}  HEAD {head}  "
            f"{'WIP commit' if committed else 'no change'}  push {'ok' if pushed else 'FAILED'}"
        )
    return rows or ["stop-all: no lane in_progress"]


def _worktrees(repo: Path) -> list[dict[str, str]]:
    """`git worktree list --porcelain` as one dict per worktree (worktree, HEAD, branch, ...)."""
    listing = _git(repo, "worktree", "list", "--porcelain").stdout
    found = []
    for block in listing.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if "worktree" in fields:
            found.append(fields)
    return found


def _pr_merged(branch: str, repo: Path) -> bool:
    out = flow._run(
        ["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "number"],
        repo,
    )
    try:
        return bool(json.loads(out or "[]"))
    except ValueError:
        return False


SCRATCH_ROOTS = [Path("E:/DevCache")]


def gc(
    repo: Path,
    merged: Callable[[str, Path], bool] = _pr_merged,
    scratch: list[Path] = SCRATCH_ROOTS,
) -> list[str]:
    """Remove clean worktrees whose PR merged, and clean detached scratch copies (mutation runs)
    whose commit is still on a branch. Dirty, locked and unmerged worktrees stay."""
    rows = []
    for fields in _worktrees(repo):
        path = Path(fields["worktree"])
        if _inside(path, repo) and path.resolve() == repo.resolve():
            continue
        if "locked" in fields or not path.exists():
            rows.append(
                f"keep     {path}  ({'locked' if 'locked' in fields else 'missing'})"
            )
            continue
        dirty = _git(path, "status", "--porcelain").stdout.splitlines()
        if dirty:
            rows.append(f"keep     {path}  (dirty, {len(dirty)} file(s))")
            continue
        branch = fields.get("branch", "").removeprefix("refs/heads/")
        if branch:
            ok = merged(branch, repo)
            why = f"{branch}: PR {'merged' if ok else 'not merged'}"
        else:
            on_branch = bool(
                _git(
                    repo, "branch", "-a", "--contains", fields.get("HEAD", "")
                ).stdout.strip()
            )
            ok = on_branch and any(_inside(path, root) for root in scratch)
            why = f"detached {fields.get('HEAD', '')[:7]}" + (
                "" if on_branch else ", commit on no branch"
            )
        if not ok:
            rows.append(f"keep     {path}  ({why})")
            continue
        try:
            check_removable(path, repo, scratch)
        except ValueError as error:
            rows.append(f"keep     {path}  ({error})")
            continue
        for card_file in sorted((repo / ".work").glob("*/card.yaml")):
            card = flow.load(card_file) or {}
            if card.get("worktree") and _inside(path, Path(str(card["worktree"]))):
                flow.bring_home(
                    repo / ".work", card_file.parent.name
                )  # .work/ is gitignored
        unlink_links(path)  # pnpm junctions point into the main repo (R45)
        result = _git(repo, "worktree", "remove", "--force", str(path))
        rows.append(
            f"{'removed' if result.returncode == 0 else 'FAILED '}  {path}  ({why})"
        )
    _git(repo, "worktree", "prune")
    return rows or ["gc: no worktree besides the main checkout"]


def down(repo: Path, lane: int, force: bool = False) -> None:
    path = lane_path(repo, lane)
    if not path.exists():
        return
    dirty = _git(path, "status", "--short").stdout.splitlines()
    if dirty and not force:
        # Removing the folder throws away what was never committed; the branch keeps the rest.
        raise RuntimeError(
            f"L{lane} has {len(dirty)} uncommitted file(s): commit and push first, "
            f"or run `lane.py down L{lane} --force` to discard them"
        )
    unlink_links(path)  # pnpm junctions point into the main repo (R45)
    result = _git(repo, "worktree", "remove", "--force", str(path))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    _git(repo, "worktree", "prune")


def _age(minutes: float | None) -> str:
    if minutes is None:
        return "?"
    return f"{minutes:.0f}m" if minutes < 120 else f"{minutes / 60:.0f}h"


def _commit_age(path: Path, now: float) -> float | None:
    stamp = _git(path, "log", "-1", "--format=%ct").stdout.strip()
    return (now - int(stamp)) / 60 if stamp.isdigit() else None


def _lane_report(repo: Path, branch: str, now: float) -> tuple[str, float | None]:
    """(status, minutes since the file changed) of the lane-report of the task on `branch`."""
    for card in sorted((repo / ".work").glob("*/card.yaml")):
        doc = flow.load(card)
        report = _report_path(repo, card.parent.name, doc) if doc else None
        if doc and doc.get("branch") == branch and report:
            found = flow.load(report) or {}
            return str(found.get("status") or "?"), (now - report.stat().st_mtime) / 60
    return "-", None


def status(repo: Path, stale: bool = False, now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    rows = []
    for lane in LANES:
        path = lane_path(repo, lane)
        if not path.exists():
            rows.append(f"L{lane}  free")
            continue
        branch = _git(path, "branch", "--show-current").stdout.strip()
        head = _git(path, "log", "-1", "--format=%h %s").stdout.strip()[:70]
        dirty = len(_git(path, "status", "--short").stdout.splitlines())
        row = f"L{lane}  {branch}  {head}  ({dirty} file(s) not committed)"
        if stale:
            state, report_age = _lane_report(repo, branch, now)
            commit_age = _commit_age(path, now)
            row += f"  commit {_age(commit_age)} ago  report {state} {_age(report_age)}"
            old = all(
                a is not None and a > STALE_MINUTES for a in (commit_age, report_age)
            )
            if state == "in_progress" and old:
                row += "  STALE"
        rows.append(row)
    if stale:
        rows += orphans(repo, now)
    return rows


def orphans(repo: Path, now: float) -> list[str]:
    """Worktrees under .claude/worktrees/ that are not a fixed lane. Read only."""
    listing = _git(repo, "worktree", "list", "--porcelain").stdout
    root = (repo / ".claude" / "worktrees").resolve()
    rows = []
    for block in listing.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if "worktree" not in fields:
            continue
        path = Path(fields["worktree"]).resolve()
        if path.parent != root or re.fullmatch(r"L[1-5]", path.name):
            continue
        branch = fields.get("branch", "").removeprefix("refs/heads/") or "?"
        dirty = len(_git(path, "status", "--short").stdout.splitlines())
        has_pr = branch != "?" and flow.open_pr(branch, repo) is not None
        rows.append(
            f"ORPHAN  {path.name}  {branch}  commit {_age(_commit_age(path, now))} ago  "
            f"({dirty} file(s) not committed)  PR {'open' if has_pr else 'none'}"
        )
    return rows


def find_docker() -> str | None:
    if shutil.which("docker"):
        return "docker"
    if DOCKER_BIN.exists():
        os.environ["PATH"] = f"{DOCKER_BIN}{os.pathsep}{os.environ.get('PATH', '')}"
        return shutil.which("docker")
    return None


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], check=False, capture_output=True, text=True
    )


def docker_running() -> bool:
    return _docker("info").returncode == 0


def start_docker(
    wait: int = DOCKER_WAIT_SECONDS, sleep: Callable[[float], None] = time.sleep
) -> bool:
    if not DOCKER_APP.exists():
        return False
    subprocess.Popen([str(DOCKER_APP)])
    for _ in range(wait // 5):
        if docker_running():
            return True
        sleep(5)
    return docker_running()


def container_healthy(name: str) -> bool:
    out = _docker("inspect", "-f", "{{.State.Health.Status}}", name)
    return out.returncode == 0 and out.stdout.strip() == "healthy"


def free_ram_gb() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found,unused-ignore]

        return float(psutil.virtual_memory().available) / 2**30
    except ImportError:
        pass
    command = "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
    )
    return (
        int(out.stdout.strip()) / 2**20 if out.stdout.strip().isdigit() else None
    )  # KiB -> GiB


def preflight(sleep: Callable[[float], None] = time.sleep) -> tuple[list[str], bool]:
    """(messages, ok). ok is False only when Docker is unusable or RAM is below the hard floor."""
    notes, ok = [], True
    if find_docker() is None:
        return [f"preflight: `docker` not found (PATH, {DOCKER_BIN})"], False
    if not docker_running():
        notes.append("preflight: Docker is not running, starting Docker Desktop...")
        if not start_docker(sleep=sleep):
            return [
                *notes,
                f"preflight: Docker did not come up in {DOCKER_WAIT_SECONDS} s",
            ], False
    for name in CONTAINERS:
        if not container_healthy(name):
            notes.append(f"preflight: {name} is not healthy: run `just up`")
    ram = free_ram_gb()
    if ram is not None and ram < RAM_STOP_GB:
        notes.append(f"preflight: only {ram:.1f} GB RAM free (< {RAM_STOP_GB}): stop")
        ok = False
    elif ram is not None and ram < RAM_WARN_GB:
        notes.append(f"preflight: warning, {ram:.1f} GB RAM free (< {RAM_WARN_GB})")
    if os.environ.get("PYTHONIOENCODING", "").lower().replace("-", "") != "utf8":
        notes.append(
            "preflight: warning, PYTHONIOENCODING is not utf-8 (Vietnamese text breaks)"
        )
    return notes or ["preflight: ok"], ok


MODELS_DIR = "services/core-api/src/core_api/db/models"


def _model_columns(repo: Path, base: str) -> dict[str, str]:
    """Table name -> source of its model class, read from `base` (not the working tree)."""
    listing = _git(
        repo, "ls-tree", "-r", "--name-only", base, "--", MODELS_DIR
    ).stdout.split()
    tables: dict[str, str] = {}
    for name in (n for n in listing if n.endswith(".py")):
        source = _git(repo, "show", f"{base}:{name}").stdout
        for block in re.split(r"^class ", source, flags=re.MULTILINE)[1:]:
            found = re.search(r"__tablename__\s*=\s*[\"']([\w.]+)[\"']", block)
            if found:
                tables[found.group(1)] = block
    return tables


def schema_check(repo: Path, task: str) -> tuple[list[str], list[str]]:
    """(missing `table.column`s, notes) for the card's `needs_schema` against its base.

    A task handed out before its migration merged wastes a lane: T7.4 (31/10) burned 17M tokens
    and wrote a stopgap migration it had to drop. No `needs_schema` field only warns.
    """
    card = flow.load(repo / ".work" / task / "card.yaml")
    if card is None:
        return [], [
            f"preflight {task}: thiếu .work/{task}/card.yaml, bỏ qua kiểm schema"
        ]
    needs = card.get("needs_schema")
    if needs is None:
        return [], [
            f"preflight {task}: card không có needs_schema, chưa kiểm schema (cảnh báo)"
        ]
    base = str(card.get("base") or "origin/main")
    tables = _model_columns(repo, base)
    missing = []
    for item in needs if isinstance(needs, list) else [needs]:
        table, _, column = str(item).partition(".")
        block = tables.get(table, "")
        pattern = rf"^\s+{re.escape(column)}\s*:|[\"']{re.escape(column)}[\"']"
        if not (block and column and re.search(pattern, block, re.MULTILINE)):
            missing.append(str(item))
    return missing, []


Row = dict[str, Any]


def _gh_open_prs() -> list[dict[str, str]] | None:
    try:
        run = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--json",
                "number,headRefName,title",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(run.stdout) if run.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return data if isinstance(data, list) else None


def _read_yaml_flat(path: Path) -> dict[str, str]:
    """Top-level `key: value` lines only; enough for card.yaml and lane-report.yaml."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        found = re.match(r"^([A-Za-z_]+):\s*(.*?)\s*$", line)
        if found:
            out[found.group(1)] = found.group(2).strip("\"'")
    return out


def _read_cards(repo: Path) -> list[Row]:
    cards: list[Row] = []
    for card_file in sorted((repo / ".work").glob("*/card.yaml")):
        card = _read_yaml_flat(card_file)
        report_file = _report_path(repo, card_file.parent.name, dict(card))
        report = _read_yaml_flat(report_file) if report_file else {}
        touches = [
            t.strip().strip("\"'")
            for t in card.get("touches", "").strip("[]").split(",")
        ]
        cards.append(
            {
                "task": card.get("task", card_file.parent.name),
                "lane": card.get("lane", "?"),
                "risk": card.get("risk", ""),
                "branch": card.get("branch", ""),
                "touches": [t for t in touches if t],
                "done": report.get("status") == "done",
            }
        )
    return cards


def _is_red(text: str) -> bool:
    return "🔴" in text or text.strip() == "red"


def _plan_blocks(plan: str) -> dict[str, tuple[list[str], list[str]]]:
    """Task code -> (dependencies, files) from the `### T…` blocks of PLAN.md."""
    blocks: dict[str, tuple[list[str], list[str]]] = {}
    for chunk in re.split(r"^### ", plan, flags=re.MULTILINE)[1:]:
        code = re.match(r"(T[\w.-]*\d[\w.-]*)", chunk)
        if not code:
            continue
        dep = re.search(r"^- \*\*Phụ thuộc:\*\*(.*)$", chunk, re.MULTILINE)
        files = re.search(r"^- \*\*File:\*\*(.*)$", chunk, re.MULTILINE)
        deps = re.findall(r"\bT[\w.-]*\d[\w.-]*", dep.group(1)) if dep else []
        names = re.findall(r"`([^`]+)`", files.group(1)) if files else []
        blocks[code.group(1)] = ([d.rstrip(".,;") for d in deps], names)
    return blocks


def _plan_index(text: str) -> list[Row]:
    rows: list[Row] = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7 or not re.fullmatch(r"T[\w.-]*\d[\w.-]*", cells[0]):
            continue
        rows.append(
            {
                "task": cells[0],
                "milestone": cells[1],
                "risk": cells[2],
                "merged": cells[3].startswith("✅"),
                "in_progress": cells[3].startswith("🟦"),
                "line": int(cells[5]) if cells[5].isdigit() else 0,
                "name": "|".join(cells[6:]),
            }
        )
    return rows


def _overlap(a: list[str], b: list[str]) -> bool:
    def norm(path: str) -> str:
        return path.strip().replace("\\", "/").rstrip("/")

    for x in map(norm, a):
        for y in map(norm, b):
            if x and y and (x == y or x.startswith(y + "/") or y.startswith(x + "/")):
                return True
    return False


def _order(row: Row) -> tuple[int, str, int, int]:
    found = re.fullmatch(r"M(\d+)", row["milestone"])
    risk = {"🔴": 0, "🟡": 1}.get(row["risk"].strip(), 2)
    return (int(found.group(1)) if found else 999, row["milestone"], risk, row["line"])


def next_tasks(
    repo: Path,
    gh: Callable[[], list[dict[str, str]] | None] = _gh_open_prs,
    limit: int = 10,
    show_all: bool = False,
) -> list[str]:
    """Cap line, then candidates by milestone, risk, PLAN line (WORKFLOW-PARALLEL scheduling)."""
    rows = _plan_index((repo / "docs" / "plan-index.md").read_text(encoding="utf-8"))
    blocks = _plan_blocks((repo / "docs" / "PLAN.md").read_text(encoding="utf-8"))
    cards = _read_cards(repo)
    prs = gh()
    red_task = {r["task"] for r in rows if _is_red(r["risk"])}
    red_branch = {c["branch"]: _is_red(c["risk"]) for c in cards if c["branch"]}
    notes = (
        ["warning: gh failed, open PRs unknown (counted as 0)"] if prs is None else []
    )
    open_branches: set[str] = set()
    open_red = 0
    pr_tasks: set[str] = set()
    for pr in prs or []:
        branch, title = pr.get("headRefName", ""), pr.get("title", "")
        open_branches.add(branch)
        codes = re.findall(r"\bT[\w.-]*\d[\w.-]*", title)
        pr_tasks.update(codes)
        if branch in red_branch:
            open_red += red_branch[branch]
        else:
            open_red += "🔴" in title or any(c in red_task for c in codes)
    open_total = len(prs or [])
    stop = []
    if open_total >= MAX_OPEN_PRS:
        stop.append(f"{open_total} PR mở, cap {MAX_OPEN_PRS}")
    if open_red >= MAX_OPEN_RED_PRS:
        stop.append(f"{open_red} PR 🔴 mở, cap {MAX_OPEN_RED_PRS}")
    verdict = f"DỪNG PHÁT ({'; '.join(stop)})" if stop else "được phát"
    lines = [
        f"PR mở {open_total}/{MAX_OPEN_PRS} · PR 🔴 mở {open_red}/{MAX_OPEN_RED_PRS} -> {verdict}",
        *notes,
    ]
    merged = {r["task"] for r in rows if r["merged"]}
    running = [c for c in cards if not c["done"] or c["branch"] in open_branches]
    running_tasks = {c["task"] for c in running} | pr_tasks
    candidates: list[tuple[Row, str]] = []
    blocked: list[str] = []
    for row in sorted(rows, key=_order):
        code = row["task"]
        if row["merged"] or code in running_tasks:
            continue
        if row["in_progress"]:
            blocked.append(f"{code} | đang làm")
            continue
        deps, files = blocks.get(code, ([], []))
        missing = [d for d in deps if d not in merged]
        clash = next((c for c in running if _overlap(files, c["touches"])), None)
        if missing:
            blocked.append(f"{code} | thiếu phụ thuộc {', '.join(missing)}")
        elif clash:
            blocked.append(
                f"{code} | trùng touches với {clash['task']} ({clash['lane']})"
            )
        else:
            hint = any(h in f.lower() for f in files for h in MIGRATION_HINTS)
            candidates.append((row, "L1" if hint else "bất kỳ"))
    for row, suggest in candidates[:limit]:
        lines.append(
            f"{row['task']} | {row['milestone']} | {row['risk'] or '-'} | "
            f"PLAN:{row['line']} | {suggest} | {row['name']}"
        )
    if not candidates:
        lines.append("(không có ứng viên)")
    if show_all:
        lines.extend(
            ["-- bị chặn --", *blocked] if blocked else ["-- bị chặn -- (không có)"]
        )
    return lines


def main_repo() -> Path:
    common = _git(Path.cwd(), "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common.stdout.strip()).parent


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lane.py")
    sub = parser.add_subparsers(dest="action", required=True)
    p_up = sub.add_parser("up")
    p_up.add_argument("lane")
    p_up.add_argument("branch")
    p_up.add_argument("--base", default="origin/main")
    p_up.add_argument("--no-db", action="store_true")
    p_up.add_argument("--no-preflight", action="store_true")
    p_up.add_argument(
        "--no-sync", action="store_true", help="skip `uv sync` of the services"
    )
    p_env = sub.add_parser("env")
    p_env.add_argument("lane", nargs="?")
    p_env.add_argument(
        "--for-review", type=Path, help="worktree: env of the lane that owns it"
    )
    p_env.add_argument("--shell", choices=["bash", "powershell"], default="bash")
    sub.add_parser("stop-all")
    sub.add_parser("gc")
    p_down = sub.add_parser("down")
    p_down.add_argument("lane")
    p_down.add_argument(
        "--force", action="store_true", help="discard uncommitted files"
    )
    p_status = sub.add_parser("status")
    p_status.add_argument(
        "--stale", action="store_true", help="ages, STALE and ORPHAN worktrees"
    )
    p_pre = sub.add_parser("preflight")
    p_pre.add_argument(
        "task", nargs="?", help="check the card's needs_schema instead of Docker"
    )
    p_next = sub.add_parser("next")
    p_next.add_argument(
        "--all", action="store_true", help="also list blocked tasks and why"
    )
    p_next.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    repo = main_repo()
    try:
        if args.action == "preflight" and args.task:
            missing, notes = schema_check(repo, args.task)
            print("\n".join(notes or [f"preflight {args.task}: schema ok"]))
            if missing:
                print(
                    f"preflight {args.task}: thiếu cột trên base: {', '.join(missing)}"
                )
                return 1
            return 0
        if args.action == "preflight":
            notes, ok = preflight()
            print("\n".join(notes))
            return 0 if ok else 1
        if args.action == "next":
            print("\n".join(next_tasks(repo, limit=args.limit, show_all=args.all)))
            return 0
        if args.action == "up":
            if not args.no_preflight and not args.no_db:
                notes, ok = preflight()
                print("\n".join(notes))
                if not ok:
                    return 1
            sync = None if args.no_sync else uv_sync
            print(
                up(
                    repo,
                    parse_lane(args.lane),
                    args.branch,
                    args.base,
                    not args.no_db,
                    sync,
                )
            )
        elif args.action == "stop-all":
            print("\n".join(stop_all(repo)))
        elif args.action == "gc":
            rows = gc(repo)
            docs = repo / "docs"
            if (
                docs / ".git"
            ).exists():  # the private docs repo has worktrees of its own
                rows += [
                    f"docs: {row}"
                    for row in gc(
                        docs, scratch=[*SCRATCH_ROOTS, repo / ".claude" / "worktrees"]
                    )
                ]
            print("\n".join(rows))
        elif args.action == "env":
            if args.for_review:
                env = review_env(repo, args.for_review)
            elif args.lane:
                env = lane_env(parse_lane(args.lane))
            else:
                raise ValueError("env needs a lane (L1..L5) or --for-review <worktree>")
            for key, value in env.items():
                print(
                    f"$env:{key} = '{value}'"
                    if args.shell == "powershell"
                    else f"export {key}={value}"
                )
        elif args.action == "down":
            down(repo, parse_lane(args.lane), args.force)
        else:
            print("\n".join(status(repo, args.stale)))
    except (ValueError, RuntimeError) as error:
        print(f"lane: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
