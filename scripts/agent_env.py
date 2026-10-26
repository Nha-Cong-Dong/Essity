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


def redis_db(agent: str, registry: Path) -> int:
    """The agent's Redis db, handed out once from 1..14 and kept in `registry`.

    db 0 holds local data, 15 is the shared test db. A hash would let two agents share a db, and
    one suite's flush would break the other's (R32), so dbs are handed out, not computed.
    """
    with acquire("redis-registry", 1, registry.parent, timeout=10):
        given: dict[str, int] = json.loads(registry.read_text()) if registry.exists() else {}
        if agent not in given:
            free = sorted(set(range(1, 15)) - set(given.values()))
            if not free:
                raise RuntimeError(f"all 14 Redis test dbs are given out; free some in {registry}")
            given[agent] = free[0]
            registry.write_text(json.dumps(given, indent=2, sort_keys=True))
        return given[agent]


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
    parser.add_argument("agent")
    parser.add_argument("--shell", choices=["bash", "powershell"], default="bash")
    parser.add_argument("--no-create", action="store_true", help="only print the variables")
    args = parser.parse_args(argv)
    if not args.no_create:
        ensure_database(database_name(args.agent))
    redis = redis_db(args.agent, default_lock_dir() / "redis-dbs.json")
    print("\n".join(env_lines(args.agent, args.shell, redis)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
