"""T7.6, migration 0024 (ADR-0008, additions only; US-02 AC2, AC3): section page positions,
the submission's own file keys and the document types a submission may hold. The database,
not the code, says no."""

import uuid
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from core_api.db.models import NoteFile, Submission
from v2_rows import World, make_document, make_section, make_study_session

SHA = "ab" * 32
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def key(world: World, session_id: uuid.UUID, ext: str = "pdf", sha: str = SHA) -> str:
    return f"users/{world.alice.id}/sessions/{session_id}/notes/{sha}.{ext}"


def submit(world: World, keys: Any) -> Submission:
    study = make_study_session(world.session, world.alice, world.subject)
    row = Submission(
        user_id=world.alice.id,
        session_id=study.id,
        status="queued",
        file_keys=keys(study.id) if callable(keys) else keys,
    )
    world.session.add(row)
    world.session.flush()
    return row


# --- submission.file_keys ---------------------------------------------------------------------


def test_file_keys_of_the_session_are_accepted(world: World) -> None:
    submit(world, lambda sid: [key(world, sid), key(world, sid, "docx", "cd" * 32)])
    submit(world, [])


@pytest.mark.parametrize(
    "bad",
    [
        lambda w, sid: [f"users/{w.bob.id}/sessions/{sid}/notes/{SHA}.pdf"],
        lambda w, sid: [f"users/{w.alice.id}/sessions/{uuid.uuid4()}/notes/{SHA}.pdf"],
        lambda w, sid: [key(w, sid), f"users/{w.bob.id}/sessions/{sid}/notes/{SHA}.pdf"],
        lambda w, sid: [f"users/{w.alice.id}/sessions/{sid}/notes/{SHA}.exe"],
        lambda w, sid: [f"users/{w.alice.id}/sessions/{sid}/notes/short.pdf"],
        lambda w, sid: [key(w, sid, sha=f"{i:064x}") for i in range(21)],
        lambda w, sid: [key(w, sid), None],
    ],
    ids=["other_user", "other_session", "foreign_in_middle", "bad_ext", "bad_sha", "21", "null"],
)
def test_file_keys_check_rejects_foreign_or_odd_keys(world: World, bad: Any) -> None:
    # Red when: the file_keys CHECK is missing, or checks only the first element.
    with pytest.raises(IntegrityError):
        submit(world, lambda sid: bad(world, sid))


# --- doc_section page positions ---------------------------------------------------------------


def section(world: World, document: Any = None, **kw: Any) -> Any:
    document = document or make_document(world.session, world.alice, world.subject)
    return make_section(world.session, world.alice, document, **kw)


def test_section_pages_set_together_are_accepted(world: World) -> None:
    document = make_document(world.session, world.alice, world.subject)
    section(world, document)
    section(world, document, first_page=3, last_page=3)
    section(world, document, first_page=3, last_page=9)


@pytest.mark.parametrize(
    "pages",
    [
        {"first_page": 3},
        {"last_page": 3},
        {"first_page": 0, "last_page": 2},
        {"first_page": 5, "last_page": 4},
    ],
    ids=["first_only", "last_only", "from_zero", "reversed"],
)
def test_section_pages_both_or_neither_and_ordered(world: World, pages: dict[str, int]) -> None:
    # Red when: the CHECKs on doc_section.first_page / last_page are missing.
    with pytest.raises(IntegrityError):
        section(world, **pages)


# --- note_file mime ---------------------------------------------------------------------------


def test_note_file_takes_docx_and_pptx_mimes(world: World) -> None:
    study = make_study_session(world.session, world.alice, world.subject)
    for mime, ext, sha in ((DOCX, "docx", "cd" * 32), (PPTX, "pptx", "ef" * 32)):
        world.session.add(
            NoteFile(
                user_id=world.alice.id,
                session_id=study.id,
                object_key=key(world, study.id, ext, sha),
                sha256=sha,
                mime=mime,
                size_bytes=1,
            )
        )
        world.session.flush()


def test_note_file_still_refuses_unknown_mime(world: World) -> None:
    study = make_study_session(world.session, world.alice, world.subject)
    world.session.add(
        NoteFile(
            user_id=world.alice.id,
            session_id=study.id,
            object_key=key(world, study.id, "pdf"),
            sha256=SHA,
            mime="application/zip",
            size_bytes=1,
        )
    )
    with pytest.raises(IntegrityError):
        world.session.flush()
