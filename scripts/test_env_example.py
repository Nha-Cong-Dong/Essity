"""R04 (T1.21): what `just up` reads from .env is all in .env.example, and no image decides
which environment it runs in (R33: that is set by Compose locally and by the deploy, T0.13)."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "infra/docker-compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"
DOCKERFILES = [
    ROOT / "services/core-api/Dockerfile",
    ROOT / "services/ai-service/Dockerfile",
    ROOT / "apps/web/Dockerfile",
]


def compose_variables() -> set[str]:
    """Every ${NAME...} Compose fills in from .env."""
    return set(re.findall(r"\$\{([A-Z0-9_]+)", COMPOSE.read_text("utf-8")))


def example_variables() -> set[str]:
    return set(re.findall(r"^([A-Z0-9_]+)=", ENV_EXAMPLE.read_text("utf-8"), re.MULTILINE))


class EnvExample(unittest.TestCase):
    def test_r04_env_example_has_every_variable_compose_reads(self) -> None:
        # Red when: Compose reads a variable .env.example lacks, so a fresh `just env && just up`
        # starts a service with an empty value.
        missing = compose_variables() - example_variables()
        self.assertEqual(missing, set(), f"add to .env.example: {sorted(missing)}")

    def test_ai_service_gets_the_quota_and_provider_url(self) -> None:
        # Red when: the AI cost quota or the provider URL set in .env never reaches the
        # ai-service container, so it spends against the code defaults or the wrong endpoint.
        block = COMPOSE.read_text("utf-8").split("\n  ai-service:\n", 1)[1].split("\n  web:\n")[0]
        for name in (
            "AI_QUOTA_DAILY_USD",
            "AI_QUOTA_MONTHLY_USD",
            "AI_QUOTA_HARD_CAP_FACTOR",
            "ANTHROPIC_BASE_URL",
        ):
            with self.subTest(name):
                self.assertRegex(block, rf"\n      {name}: \$\{{{name}")

    def test_r33_no_dockerfile_sets_the_environment(self) -> None:
        # Red when: an image bakes in CORE_/AI_ENVIRONMENT, so a deploy that forgets to set it
        # runs with that value instead of refusing to start.
        for dockerfile in DOCKERFILES:
            with self.subTest(dockerfile.name):
                self.assertNotRegex(dockerfile.read_text("utf-8"), r"(CORE|AI)_ENVIRONMENT")

    def test_r33_compose_marks_its_local_environment_as_dev_only(self) -> None:
        # The two hard-coded `local` lines must say why, so nobody reuses the file to deploy.
        text = COMPOSE.read_text("utf-8")
        for name in ("CORE_ENVIRONMENT", "AI_ENVIRONMENT"):
            with self.subTest(name):
                found = re.search(rf"{name}: local  # .*dev", text)
                self.assertIsNotNone(found, f"{name}: local needs a '# ... dev only' comment")


if __name__ == "__main__":
    unittest.main()
