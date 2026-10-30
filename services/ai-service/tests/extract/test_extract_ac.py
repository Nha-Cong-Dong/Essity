"""T4.10: the US-02 acceptance criteria, end to end through the fake extractor and the endpoint.

The fake proves the data flow and the code's checks. Whether a real model picks the right
document and section is measured by T4.11 (eval), and the "5 seconds with a real sentence"
criterion waits for a key (as T3.1 did).
"""

import datetime
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from ai_service.api.grade import get_audit_sessions, get_llm_client
from ai_service.llm.client import LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from ai_service.tasks.extract_session import fake_extract
from tests.extract.helpers import TODAY, document, extract_body
from tests.llm.helpers import NoQuota

TOKEN = "test-service-token-0123456789abcdef"


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    sessions = sessionmaker(engine, expire_on_commit=False)
    app: FastAPI = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    llm = LlmClient(
        FakeAdapter({"extract_session": fake_extract}),
        sessions,
        models={"grade": "claude-haiku-5-5", "extract_session": "claude-haiku-5-5"},
        quota_guard=NoQuota(),
    )
    app.dependency_overrides[get_llm_client] = lambda: llm
    yield TestClient(app, headers={SERVICE_TOKEN_HEADER: TOKEN})


def ask(client: TestClient, description: str, **overrides: Any) -> dict[str, Any]:
    body = extract_body(description, **overrides)
    response = client.post("/v1/extract-session", json=body)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    data["_doc_ids"] = [d["document_id"] for d in body["documents"]]
    return data


TWO = {"documents": [document("giáo trình"), document("slide c3", labels=None)]}


def test_ac3_pages_depth_and_two_documents(client: TestClient) -> None:
    data = ask(
        client, "tối nay học giáo trình tr. 43-58, lướt tr. 59-62 và slide c3 tr. 3-9", **TWO
    )
    assert data["status"] == "proposed"
    first, second, third = data["ranges"]
    assert (first["start_page"], first["end_page"], first["depth"]) == (51, 66, "deep")
    assert (first["start_label"], first["end_label"]) == ("43", "58")
    assert (second["start_page"], second["end_page"], second["depth"]) == (67, 70, "skim")
    assert first["document_id"] == second["document_id"] == data["_doc_ids"][0]
    # The slide has no labels: its printed numbers are taken as file pages, and flagged.
    assert third["document_id"] == data["_doc_ids"][1]
    assert (third["start_page"], third["end_page"]) == (3, 9)
    assert third["basis_assumed_file"] is True
    assert third["start_label"] is None
    assert first["basis_assumed_file"] is False
    assert data["studied_on"] == TODAY.isoformat()


def test_ac3_unclear_part_is_its_own_range(client: TestClient) -> None:
    data = ask(client, "học giáo trình tr. 43-58, chưa hiểu tr. 50-52")
    assert [r["depth"] for r in data["ranges"]] == ["deep", "unclear"]


def test_ac3_section_by_chapter_uses_the_toc_span(client: TestClient) -> None:
    data = ask(client, "học giáo trình chương 3")
    [only] = data["ranges"]
    assert (only["start_page"], only["end_page"]) == (51, 74)
    assert only["sections"] == [
        "Chương 3 Tầng giao vận",
        "3.5 Connection Management",
        "3.6 Congestion Control",
    ]


def test_ac3_relative_day(client: TestClient) -> None:
    data = ask(client, "hôm qua học giáo trình tr. 10-20")
    assert data["studied_on"] == (TODAY - datetime.timedelta(days=1)).isoformat()


def test_ac3_continue_from_the_last_session(client: TestClient) -> None:
    docs = [document(last_end_page=50)]
    data = ask(client, "học tiếp giáo trình đến trang 58", documents=docs)
    [only] = data["ranges"]
    assert (only["start_page"], only["end_page"]) == (51, 66)


def test_ac3_continue_without_an_end_asks(client: TestClient) -> None:
    data = ask(client, "học tiếp giáo trình", documents=[document(last_end_page=50)])
    assert data["status"] == "clarify"
    assert data["reason"] == "missing_info"


def test_q7_trang_file_is_not_converted(client: TestClient) -> None:
    data = ask(client, "học giáo trình trang file 51-66")
    [only] = data["ranges"]
    assert (only["start_page"], only["end_page"], only["start_label"]) == (51, 66, "43")


def test_ac3b_two_documents_match_gives_a_question(client: TestClient) -> None:
    docs = [document("slide c3"), document("slide c4")]
    data = ask(client, "học slide c3 và slide c4", documents=docs)
    assert data["status"] == "clarify"
    assert data["reason"] == "ambiguous_document"
    assert sorted(data["candidate_document_ids"]) == sorted(data["_doc_ids"])


def test_ac5_vague_chapter_returns_one_question_and_no_record(client: TestClient) -> None:
    data = ask(client, "học một ít chương 4", **TWO)
    assert data["status"] == "clarify"
    assert data["question"].count("?") == 1
    assert "ranges" not in data
    assert "studied_on" not in data


def test_unknown_document_is_a_question(client: TestClient) -> None:
    data = ask(client, "học slide thầy gửi qua Zalo", **TWO)
    assert (data["status"], data["reason"]) == ("clarify", "unknown_document")


def test_ac10_no_document_means_note_only(client: TestClient) -> None:
    data = ask(client, "hôm nay xem video về DNS", **TWO)
    assert data["status"] == "note_only"
    assert data["studied_on"] == TODAY.isoformat()
    assert "ranges" not in data


def test_response_carries_the_audit_ids(client: TestClient) -> None:
    data = ask(client, "học giáo trình tr. 43-58")
    assert data["provider"] == "fake"
    assert data["prompt_version"] == "v1"
    assert data["run_id"] and data["llm_call_id"]


def test_a_document_is_never_guessed(client: TestClient) -> None:
    # T7.6 (US-02 AC3): v1 extraction stays as it is beside the v2 flow. With one document in, no
    # range names another id, and a sentence that names none gives no range at all.
    data = ask(client, "học giáo trình tr. 43-58", documents=[document("giáo trình")])
    assert {r["document_id"] for r in data["ranges"]} <= set(data["_doc_ids"])
    unnamed = ask(client, "học bài thầy gửi qua Zalo", documents=[document("giáo trình")])
    assert "ranges" not in unnamed
