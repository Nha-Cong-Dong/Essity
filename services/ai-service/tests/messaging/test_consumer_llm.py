"""T2.11: the LlmClient the consumer builds for queued grading goes through the quota guard."""

from typing import Any, cast

from ai_service.config import Settings
from ai_service.llm.quota import DbQuotaGuard
from ai_service.messaging.consumer import build_llm


def test_consumer_llm_has_the_db_quota_guard() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    llm = build_llm(settings, cast(Any, object()))
    assert llm is not None
    assert isinstance(llm._quota_guard, DbQuotaGuard)  # pyright: ignore[reportPrivateUsage]
