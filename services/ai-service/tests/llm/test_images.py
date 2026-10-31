"""T7.7: images in an LlmRequest (vision). The bytes reach the provider, never the audit row."""

import base64
import time
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.anthropic_adapter import AnthropicAdapter
from ai_service.llm.client import LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.pricing import price_for
from ai_service.llm.quota import IMAGE_TOKENS, estimate_cost
from ai_service.llm.types import ImagePart
from tests.llm.helpers import FAKE_KEY, NoQuota, answering, make_request

MODEL = "claude-haiku-5-5"
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 40


def test_us02_ac8_image_part_has_sha_and_rejects_other_media_types() -> None:
    # Red when: an image of an unlisted type (svg, gif) can reach the provider.
    part = ImagePart(data=PNG, media_type="image/png")
    assert len(part.sha256) == 64
    with pytest.raises(ValidationError):
        ImagePart(data=PNG, media_type="image/svg+xml")  # type: ignore[arg-type]


def test_us02_ac8_adapter_sends_image_blocks_before_the_text() -> None:
    # Red when: the images are dropped or put after the instructions' data block.
    api = answering()
    adapter = AnthropicAdapter(api_key=FAKE_KEY, http_client=api.client())
    request = make_request(images=(ImagePart(data=PNG, media_type="image/png"),))
    adapter.complete(request, model=MODEL, timeout=5)
    content = api.body()["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(PNG).decode(),
    }
    assert content[-1] == {"type": "text", "text": request.user}


def test_without_images_the_user_message_stays_a_string() -> None:
    # Red when: text-only tasks change shape on the wire.
    api = answering()
    AnthropicAdapter(api_key=FAKE_KEY, http_client=api.client()).complete(
        make_request(), model=MODEL, timeout=5
    )
    assert isinstance(api.body()["messages"][0]["content"], str)


def test_us02_ac8_estimate_counts_every_image_at_the_worst_case() -> None:
    # Red when: a vision call is reserved at the price of its text alone.
    price = price_for(MODEL)
    plain = estimate_cost(price, make_request(), {"max_tokens": 800})
    two = estimate_cost(
        price,
        make_request(images=(ImagePart(data=PNG, media_type="image/png"),) * 2),
        {"max_tokens": 800},
    )
    assert two - plain >= Decimal(2 * IMAGE_TOKENS) * price.input_per_mtok / 1_000_000


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def test_adr13_llm_call_input_records_image_hashes_not_bytes(
    engine: Engine, sessions: sessionmaker[Session]
) -> None:
    # Red when: the audit row stores the learner's notes image (ADR-0013).
    with sessions() as session:
        run = PipelineRun(
            user_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            task="read_notes",
            prompt_version="v1",
            prompt_sha256="0" * 64,
        )
        session.add(run)
        session.commit()
    part = ImagePart(data=PNG, media_type="image/png")
    client = LlmClient(
        FakeAdapter({"read_notes": lambda r: '{"ok": true}'}),
        sessions,
        models={"read_notes": MODEL},
        quota_guard=NoQuota(),
    )
    client.call(
        make_request(
            task="read_notes",
            user_id=run.user_id,
            subject_id=run.subject_id,
            pipeline_run_id=run.id,
            images=(part,),
        ),
        deadline=time.monotonic() + 9,
    )
    with Session(engine) as session:
        row = session.scalars(select(LlmCall).where(LlmCall.user_id == run.user_id)).one()
    assert row.input["images"] == [{"sha256": part.sha256, "bytes": len(PNG)}]
    assert base64.b64encode(PNG).decode() not in str(row.input)
