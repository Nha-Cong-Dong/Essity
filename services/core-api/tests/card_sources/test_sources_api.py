"""G4: `GET /v1/units/{id}/sources`: page text of a card anchor with the quote located."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.api.card_sources import locate
from core_api.api.deps import get_storage
from core_api.db.models import Anchor
from core_api.main import app
from fake_storage import FakeStorage
from v2_rows import RUN, make_document, make_subject, make_unit

KEY = "users/x/derived/p/pages.json"
PAGE2 = "Mở đầu.  TCP mở kết nối\nbằng ba bước bắt tay. Hết."


@pytest.fixture
def store():
    fake = FakeStorage()
    fake.put(KEY, json.dumps({"pages": [{"text": "trang 1"}, {"text": PAGE2}]}).encode(), None)
    app.dependency_overrides[get_storage] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_storage, None)


def test_sources_locate_quote_in_page_text(
    client: TestClient, db_session: Session, store: FakeStorage
):
    user, headers = signed_in(db_session)
    subject = make_subject(db_session, user)
    doc = make_document(db_session, user, subject, page_text_key=KEY)
    unit = make_unit(db_session, user, subject, title="TCP", status="canonical")
    db_session.add_all(
        [
            Anchor(
                user_id=user.id,
                unit_id=unit.id,
                source="document",
                document_id=doc.id,
                page_no=2,
                quote_text="TCP mở kết nối bằng ba bước",
                run_id=RUN,
            ),
            Anchor(
                user_id=user.id, unit_id=unit.id, source="notes", quote_text="ghi chú", run_id=RUN
            ),
        ]
    )
    db_session.flush()
    body = client.get(f"/v1/units/{unit.id}/sources", headers=headers).json()
    first = next(s for s in body["sources"] if s["page_no"] == 2)
    assert first["document_name"] == "Giáo trình"
    assert first["page_text"] == PAGE2
    # whitespace in the page differs from the quote: still found
    assert PAGE2[first["mark_start"] : first["mark_end"]] == "TCP mở kết nối\nbằng ba bước"
    note = next(s for s in body["sources"] if s["page_no"] is None)
    assert note["page_text"] is None and note["mark_start"] is None


def test_other_users_unit_is_404(client: TestClient, db_session: Session, store: FakeStorage):
    owner, _ = signed_in(db_session)
    _, headers = signed_in(db_session)
    unit = make_unit(db_session, owner, make_subject(db_session, owner))
    assert client.get(f"/v1/units/{unit.id}/sources", headers=headers).status_code == 404


def test_locate_prefers_stored_range():
    assert locate("abc xyz xyz", "xyz", 8, 11) == (8, 11)
    assert locate("abc xyz", "nope", None, None) is None
