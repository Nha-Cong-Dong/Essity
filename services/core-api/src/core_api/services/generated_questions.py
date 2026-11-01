"""One press of "Thêm câu như thế này" (T9.6b, US-17 AC1-AC6, AC8).

Steps, in this order, and never a retry (AC6):
1. the target (a question, a type or a studied outline leaf) and its studied cards; none: no call;
2. candidates of the same target still waiting for a choice are returned as they are: a second
   click (or tab) generates nothing (AC1);
3. the press is marked `running` and committed BEFORE the AI is called, so a click that arrives
   meanwhile finds it (partial unique index) and gets `running`;
4. ai-service generates and judges (layer 2); core then runs layer 1 on the stored questions
   (`pg_trgm`, AC3) and stores what passes as `source = generated`, not kept (AC5).
A quota or model trouble is `pending_ai`: nothing stored, nothing retried. Texts of the learner
and of the model never reach a log (ADR-0013).
"""

import datetime as dt
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from core_api.clients.ai_client import NotGraded
from core_api.clients.like_contract import LikeReply
from core_api.db.models import Question
from core_api.domain.generated_questions import (
    CANDIDATES_PER_CLICK,
    MSG_EMPTY,
    MSG_FAILED,
    MSG_NO_CARDS,
    MSG_PENDING_AI,
    MSG_RUNNING,
    cap_existing,
    rubric_ideas,
)
from core_api.repositories.generated_questions import GeneratedQuestionRepository, Target
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository

_log = logging.getLogger(__name__)

Kind = Literal["question", "type", "section"]
Status = Literal["ok", "empty", "pending_ai", "failed", "running"]


class LikeAi(Protocol):
    def generate_like(self, payload: dict[str, object]) -> LikeReply | NotGraded: ...


class TargetNotFoundError(LookupError):
    """The question, type or outline section is not this user's, not in this subject, or cannot
    be generated from (an excluded or unstudied section, a section with children)."""


@dataclass
class Outcome:
    status: Status
    message: str | None = None
    candidates: list[Question] = field(default_factory=list[Question])


def _target(
    repo: GeneratedQuestionRepository, subject_id: uuid.UUID, kind: Kind, id: uuid.UUID
) -> Target | None:
    if kind == "question":
        return repo.question_target(subject_id, id)
    if kind == "type":
        return repo.type_target(subject_id, id)
    return repo.section_target(subject_id, id)


def _payload(
    repo: GeneratedQuestionRepository, user_id: uuid.UUID, subject_id: uuid.UUID, target: Target
) -> dict[str, object]:
    body: dict[str, object] = {
        "user_id": str(user_id),
        "subject_id": str(subject_id),
        "samples": [{"prompt": prompt} for prompt in target.samples],
        "existing_prompts": cap_existing(repo.existing_prompts(subject_id)),
        "cards": [{"card_id": str(c.unit_id), "text": c.text} for c in target.cards],
        "count": CANDIDATES_PER_CLICK,
    }
    if target.type_name:
        body["type_name"] = target.type_name
    return body


def generate(
    session: Session,
    user_id: uuid.UUID,
    subject_id: uuid.UUID,
    kind: Kind,
    target_id: uuid.UUID,
    ai: LikeAi,
    now: dt.datetime,
    *,
    may_call: Callable[[], bool],
) -> Outcome:
    if SubjectRepository(session, user_id).get(subject_id) is None:
        raise SubjectNotFoundError(subject_id)
    repo = GeneratedQuestionRepository(session, user_id)
    target = _target(repo, subject_id, kind, target_id)
    if target is None:
        raise TargetNotFoundError(target_id)
    waiting = repo.open_for(subject_id, kind, target_id)
    if waiting:
        return Outcome("ok", candidates=waiting)
    if not target.cards:
        return Outcome("empty", MSG_NO_CARDS)
    generation = repo.begin(subject_id, kind, target_id, now)
    if generation is None:
        return Outcome("running", MSG_RUNNING)
    session.commit()  # visible to a second click before the AI is called
    if not may_call():
        repo.drop_running(generation)
        session.commit()
        return Outcome("pending_ai", MSG_PENDING_AI)
    try:
        reply = ai.generate_like(_payload(repo, user_id, subject_id, target))
    except BaseException:
        session.rollback()
        repo.drop_running(generation)
        session.commit()
        raise
    if isinstance(reply, NotGraded):
        repo.drop_running(generation)
        session.commit()
        if reply.failure == "invalid":
            return Outcome("failed", MSG_FAILED)
        return Outcome("pending_ai", MSG_PENDING_AI)
    if reply.status == "pending_ai":
        repo.drop_running(generation)
        session.commit()
        return Outcome("pending_ai", MSG_PENDING_AI)
    stored = _store(repo, subject_id, generation.id, target, reply)
    repo.finish(generation, now)
    session.commit()
    if not stored:
        return Outcome("empty", MSG_EMPTY)
    return Outcome("ok", candidates=stored)


def _store(
    repo: GeneratedQuestionRepository,
    subject_id: uuid.UUID,
    generation_id: uuid.UUID,
    target: Target,
    reply: LikeReply,
) -> list[Question]:
    sent = {c.unit_id for c in target.cards}
    stored: list[Question] = []
    for candidate in reply.kept[:CANDIDATES_PER_CLICK]:
        ideas = rubric_ideas(candidate.rubric)
        if ideas is None or not candidate.card_ids or not set(candidate.card_ids) <= sent:
            continue  # the reply is untrusted: a card we did not send, or a rubric we cannot grade
        if repo.is_near_duplicate(subject_id, candidate.prompt):
            continue  # layer 1 on the stored ones, rejected and retired included
        question = repo.add_candidate(
            subject_id=subject_id,
            generation_id=generation_id,
            type_id=target.type_id,
            prompt=candidate.prompt,
            reference_answer=candidate.reference_answer,
            rubric=ideas,
            run_id=reply.run_id,
            unit_ids=list(dict.fromkeys(candidate.card_ids)),
        )
        if question is not None:
            stored.append(question)
    _log.info("generated questions stored", extra={"outcome": "stored" if stored else "none"})
    return stored
