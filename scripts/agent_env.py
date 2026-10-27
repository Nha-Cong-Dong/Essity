"""Give an agent its own core-api test database and Redis db (R32), so suites do not collide.

    eval "$(python scripts/agent_env.py coder-s2)"              # bash
    python scripts/agent_env.py coder-s2 --shell powershell | iex   # PowerShell

Creates `core_test_<agent>` on the Compose Postgres if it is missing (the superuser creates it:
`core` has no CREATEDB), then prints the two variables the core-api conftest reads.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from with_lock import acquire, default_lock_dir

POSTGRES_CONTAINER = "essity-postgres-1"
DATABASE_URL = "postgresql+psycopg://core:change-me-local@127.0.0.1:5432/{name}"
REDIS_URL = "redis://127.0.0.1:6379/{db}"
PREFIX = "core_test_"


def database_name(agent: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", agent.lower()).strip("_")
    if not slug:
        raise ValueError(f"agent name {agent!r} has no letters or digits")
    return (PREFIX + slug)[:63]  # Postgres identifier limit


AGENT_DBS = range(6, 15)  # 0 local data, 1..5 lanes L1..L5 (lane.py), 15 shared test db


def _load(registry: Path) -> dict[str, int]:
    return json.loads(registry.read_text()) if registry.exists() else {}


def redis_db(agent: str, registry: Path) -> int:
    """The agent's Redis db, handed out once from 6..14 and kept in `registry`.

    A hash would let two agents share a db, and one suite's flush would break the other's (R32),
    so dbs are handed out, not computed. Give them back with `--release` when the agent is done.
    """
    with acquire("redis-registry", 1, registry.parent, timeout=10):
        given = _load(registry)
        if agent not in given:
            free = sorted(set(AGENT_DBS) - set(given.values()))
            if not free:
                raise RuntimeError(
                    f"all {len(AGENT_DBS)} agent Redis dbs are given out: run "
                    f"`python scripts/agent_env.py --release <agent>` (or `--release-all`)"
                )
            given[agent] = free[0]
            registry.write_text(json.dumps(given, indent=2, sort_keys=True))
        return given[agent]


def release(agents: list[str] | None, registry: Path) -> bool:
    """Give back the agents' dbs (all when `agents` is None); True if anything was freed."""
    with acquire("redis-registry", 1, registry.parent, timeout=10):
        given = _load(registry)
        kept = {} if agents is None else {a: db for a, db in given.items() if a not in agents}
        if kept == given:
            return False
        registry.write_text(json.dumps(kept, indent=2, sort_keys=True))
        return True


def env_lines(agent: str, shell: str, redis: int) -> list[str]:
    values = {
        "CORE_TEST_DATABASE_URL": DATABASE_URL.format(name=database_name(agent)),
        "CORE_TEST_REDIS_URL": REDIS_URL.format(db=redis),
    }
    if shell == "powershell":
        return [f"$env:{key} = '{value}'" for key, value in values.items()]
    return [f"export {key}={value}" for key, value in values.items()]


def create_database_command(name: str) -> list[str]:
    sql = f'CREATE DATABASE "{name}" OWNER core'
    return ["docker", "exec", POSTGRES_CONTAINER, "psql", "-U", "postgres", "-c", sql]


def ensure_database(name: str) -> None:
    result = subprocess.run(
        create_database_command(name), check=False, capture_output=True, text=True
    )
    if result.returncode != 0 and "already exists" not in result.stderr:
        sys.stderr.write(result.stderr)
        raise SystemExit(f"agent_env: could not create {name} (is `just up` running?)")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent_env.py")
    parser.add_argument("agent", nargs="?")
    parser.add_argument("--shell", choices=["bash", "powershell"], default="bash")
    parser.add_argument("--no-create", action="store_true", help="only print the variables")
    parser.add_argument("--release", nargs="+", metavar="AGENT", help="give back these dbs")
    parser.add_argument("--release-all", action="store_true", help="give back every db")
    args = parser.parse_args(argv)
    registry = default_lock_dir() / "redis-dbs.json"
    if args.release or args.release_all:
        freed = release(None if args.release_all else args.release, registry)
        print("agent_env: released" if freed else "agent_env: nothing to release")
        return 0
    if not args.agent:
        parser.error("agent name required")
    if not args.no_create:
        ensure_database(database_name(args.agent))
    redis = redis_db(args.agent, registry)
    print("\n".join(env_lines(args.agent, args.shell, redis)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
