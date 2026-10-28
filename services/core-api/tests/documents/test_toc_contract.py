"""`GET /v1/documents/{id}/toc` against `contracts/files/toc.v1.schema.json` (T4.9): core-api is
the reader, so it relays the file ai-service writes (the contract's example) unchanged."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session
from test_document_indexed import index, uploaded

from accounts import signed_in
from fake_storage import FakeStorage

FILES = Path(__file__).resolve().parents[4] / "contracts" / "files"
pytestmark = pytest.mark.usefixtures("fake_storage")


def test_the_toc_relayed_is_the_contracts(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    example = (FILES / "examples" / "toc.v1.json").read_bytes()
    schema = json.loads((FILES / "toc.v1.schema.json").read_text(encoding="utf-8"))
    user, headers = signed_in(db_session)
    document = uploaded(db_session, user)
    index(db_session, document, fake_storage, example)

    toc = client.get(f"/v1/documents/{document.id}/toc", headers=headers).json()["toc"]

    assert cast(Any, Draft202012Validator(schema)).is_valid(toc)
    assert toc == json.loads(example)
