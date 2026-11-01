"""T9.8b / US-13 AC2, AC3: the PPTX outline entry point binds the titles call to LlmClient
(task syllabus_toc, its own prompt version and sha in the audit row), one call for a deck
without sections, none otherwise; a model failure leaves a flat temporary outline."""

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.client import LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import LlmRequest
from ai_service.tasks import outline_pptx
from ai_service.tasks.outline_pptx import fake_titles, outline_pptx_file
from ai_service.tasks.syllabus import load_prompt
from tests.llm.helpers import NoQuota
from tests.office.helpers import make_pptx

MODEL = "claude-haiku-5-5"
SLIDES = [("Intro", "SECRET body 1"), ("Goals", "SECRET body 2"), ("Cells", "x"), ("DNA", "y")]


class Responder:
    def __init__(self) -> None:
        self.requests: list[LlmRequest] = []

    def __call__(self, request: LlmRequest) -> str:
        self.requests.append(request)
        return fake_titles(request)


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def _llm(sessions: sessionmaker[Session], responder: Responder, quota: object = None) -> LlmClient:
    return LlmClient(
        FakeAdapter({"syllabus_toc": responder}),
        sessions,
        models={"syllabus_toc": MODEL},
        quota_guard=quota or NoQuota(),  # type: ignore[arg-type]
    )


def _run(
    sessions: sessionmaker[Session], llm: LlmClient, data: bytes
) -> tuple[dict[str, Any], uuid.UUID, uuid.UUID]:
    user, subject = uuid.uuid4(), uuid.uuid4()
    return outline_pptx_file(data, llm, sessions, user_id=user, subject_id=subject), user, subject


def test_us13_ac2_fake_titles_groups_end_to_end(
    sessions: sessionmaker[Session], engine: Engine
) -> None:
    responder = Responder()
    before = _count(engine)
    outline, user, subject = _run(sessions, _llm(sessions, responder), make_pptx(SLIDES))
    assert len(responder.requests) == 1
    request = responder.requests[0]
    assert request.task == "syllabus_toc"
    assert (request.user_id, request.subject_id) == (user, subject)
    assert "SECRET" not in request.system + request.user  # titles only
    assert outline["unit"] == "slide"
    nodes = outline["nodes"]
    assert {n["source"] for n in nodes} == {"llm_toc"}
    assert [n["parent"] for n in nodes] == [None, 0, 0, None, 3, 3]
    assert [(n["page_start"], n["page_end"], n["weight"]) for n in nodes[:2]] == [
        (1, 2, 2),
        (1, 1, 1),
    ]
    assert _count(engine) == before + 1
    assert "note" not in outline


def test_us13_ac2_audit_row_has_titles_prompt_version_and_sha(
    sessions: sessionmaker[Session], engine: Engine
) -> None:
    responder = Responder()
    _run(sessions, _llm(sessions, responder), make_pptx(SLIDES))
    request = responder.requests[0]
    assert request.prompt_version == outline_pptx.PROMPT_VERSION
    with Session(engine) as session:
        run = session.scalars(
            select(PipelineRun).where(PipelineRun.id == request.pipeline_run_id)
        ).one()
    assert run.task == "syllabus_toc" and run.status == "succeeded"
    assert run.prompt_sha256 == outline_pptx.prompt_sha256()
    assert run.prompt_sha256 != load_prompt().sha256


def test_us13_ac2_deck_with_sections_makes_zero_calls(
    sessions: sessionmaker[Session], engine: Engine
) -> None:
    responder = Responder()
    before = _count(engine)
    outline, _, _ = _run(
        sessions,
        _llm(sessions, responder),
        make_pptx(SLIDES, [("Part A", [1, 2]), ("Part B", [3, 4])]),
    )
    assert responder.requests == [] and _count(engine) == before
    assert {n["source"] for n in outline["nodes"]} == {"sections"}


def test_us13_ac3_cap_reached_gives_flat_outline_and_neutral_note(
    sessions: sessionmaker[Session],
) -> None:
    class Capped:
        def reserve(self, request: LlmRequest, estimate: Decimal):
            raise QuotaExceededError(hard="task", window="day")  # type: ignore[call-arg]

        def release(self, *a: object, **k: object) -> None:
            raise AssertionError

    responder = Responder()
    outline, _, _ = _run(sessions, _llm(sessions, responder, Capped()), make_pptx(SLIDES))
    assert responder.requests == []
    assert {n["source"] for n in outline["nodes"]} == {"slides"}
    assert [n["parent"] for n in outline["nodes"]] == [None] * 4
    assert outline["note"] == "ai_unavailable"
    json.dumps(outline)


def test_us13_ac3_no_model_gives_flat_without_note(sessions: sessionmaker[Session]) -> None:
    user, subject = uuid.uuid4(), uuid.uuid4()
    outline = outline_pptx_file(make_pptx(SLIDES), None, sessions, user_id=user, subject_id=subject)
    assert {n["source"] for n in outline["nodes"]} == {"slides"}


def _count(engine: Engine) -> int:
    with Session(engine) as session:
        return len(list(session.scalars(select(LlmCall))))
