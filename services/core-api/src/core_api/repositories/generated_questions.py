"""Generated practice questions of one user (T9.6b, US-17): what the AI is asked about, what is
already there, the near-duplicate check, the running guard, and the candidates waiting for a
choice. Every query is scoped to the user (ARCH §6.2)."""

import datetime as dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, Select, and_, delete, exists, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from core_api.db.models import (
    DocSection,
    KnowledgeUnit,
    Question,
    QuestionGeneration,
    QuestionType,
    QuestionUnit,
    UnitSection,
)
from core_api.domain.generated_questions import RUNNING_STALE_SECONDS, TRIGRAM_THRESHOLD
from core_api.domain.question_hash import content_hash
from core_api.repositories.base import UserScopedRepository

# unit.status values that count as a card the learner owns (not a draft, not retired).
LIVE_CARD = ("canonical",)
MAX_CARDS = 40
MAX_SAMPLES = 3
MAX_CARD_CHARS = 1500
MAX_EXISTING_ROWS = 300
GENERATED_LEVEL = 2


@dataclass(frozen=True)
class Card:
    unit_id: uuid.UUID
    text: str


@dataclass(frozen=True)
class Target:
    """What one press is about: the type name and id (None: the AI's default), up to three sample
    prompts, and the studied cards the AI may use."""

    kind: str
    id: uuid.UUID
    type_id: uuid.UUID | None
    type_name: str | None
    samples: list[str]
    cards: list[Card] = field(default_factory=list[Card])


class GeneratedQuestionRepository(UserScopedRepository[Question]):
    model = Question

    # --- What the AI is asked about ---------------------------------------------------------

    def _live_cards(self, *where: ColumnElement[bool], subject_id: uuid.UUID) -> list[Card]:
        rows = self.session.execute(
            select(KnowledgeUnit.id, KnowledgeUnit.title, KnowledgeUnit.summary)
            .where(
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.subject_id == subject_id,
                KnowledgeUnit.status.in_(LIVE_CARD),
                KnowledgeUnit.skipped_at.is_(None),
                *where,
            )
            .order_by(KnowledgeUnit.created_at, KnowledgeUnit.id)
            .limit(MAX_CARDS)
        ).all()
        return [Card(id, f"{title}: {summary}"[:MAX_CARD_CHARS]) for id, title, summary in rows]

    def _cards_of_questions(
        self, subject_id: uuid.UUID, question_ids: list[uuid.UUID]
    ) -> list[Card]:
        if not question_ids:
            return []
        linked = select(QuestionUnit.unit_id).where(
            QuestionUnit.user_id == self.user_id, QuestionUnit.question_id.in_(question_ids)
        )
        return self._live_cards(KnowledgeUnit.id.in_(linked), subject_id=subject_id)

    def _type(self, type_id: uuid.UUID | None, subject_id: uuid.UUID) -> QuestionType | None:
        if type_id is None:
            return None
        return self.session.scalars(
            select(QuestionType).where(
                QuestionType.user_id == self.user_id,
                QuestionType.id == type_id,
                QuestionType.subject_id == subject_id,
            )
        ).first()

    def question_target(self, subject_id: uuid.UUID, question_id: uuid.UUID) -> Target | None:
        """ "Thêm câu như thế này" on one question: its type, its prompt as the sample, the live
        cards it checks. A candidate nobody kept is no sample (it is not a practice question)."""
        question = self.session.scalars(
            select(Question).where(
                Question.user_id == self.user_id,
                Question.id == question_id,
                Question.subject_id == subject_id,
                Question.status == "active",
                *self._practice_only(),
            )
        ).first()
        if question is None:
            return None
        kind = self._type(question.type_id, subject_id)
        return Target(
            "question",
            question_id,
            kind.id if kind else None,
            kind.name if kind else None,
            [question.prompt],
            self._cards_of_questions(subject_id, [question_id]),
        )

    def type_target(self, subject_id: uuid.UUID, type_id: uuid.UUID) -> Target | None:
        """The same on a whole type: up to three of its newest practice questions as samples."""
        kind = self._type(type_id, subject_id)
        if kind is None:
            return None
        questions = self.session.execute(
            select(Question.id, Question.prompt)
            .where(
                Question.user_id == self.user_id,
                Question.subject_id == subject_id,
                Question.type_id == type_id,
                Question.status == "active",
                *self._practice_only(),
            )
            .order_by(Question.created_at.desc(), Question.id)
            .limit(MAX_SAMPLES)
        ).all()
        return Target(
            "type",
            type_id,
            kind.id,
            kind.name,
            [prompt for _, prompt in questions],
            self._cards_of_questions(subject_id, [id for id, _ in questions]),
        )

    def section_target(self, subject_id: uuid.UUID, section_id: uuid.UUID) -> Target | None:
        """ "Sinh câu luyện tập cho mục này" (AC1, a subject with no bank): a studied leaf of the
        outline, no sample, the AI's default type, the live cards linked to the section."""
        section = self.session.scalars(
            select(DocSection).where(
                DocSection.user_id == self.user_id,
                DocSection.id == section_id,
                DocSection.subject_id == subject_id,
                DocSection.excluded.is_(False),
                DocSection.studied_weight > 0,
            )
        ).first()
        if section is None:
            return None
        child = DocSection.__table__.alias("child")
        has_child = self.session.scalar(
            select(exists().where(child.c.parent_id == section_id, child.c.user_id == self.user_id))
        )
        if has_child:
            return None
        linked = select(UnitSection.unit_id).where(
            UnitSection.user_id == self.user_id, UnitSection.section_id == section_id
        )
        cards = self._live_cards(KnowledgeUnit.id.in_(linked), subject_id=subject_id)
        return Target("section", section_id, None, None, [], cards)

    @staticmethod
    def _practice_only() -> tuple[ColumnElement[bool], ColumnElement[bool]]:
        """A generated candidate is a practice question only once kept (AC5)."""
        return (
            (Question.source != "generated") | (Question.kept_at.is_not(None)),
            Question.quality_status == "ok",
        )

    def existing_prompts(self, subject_id: uuid.UUID) -> list[str]:
        """Every question prompt of the subject, the rejected and retired ones too (a rejected
        question is never suggested again), newest first."""
        return list(
            self.session.scalars(
                select(Question.prompt)
                .where(Question.user_id == self.user_id, Question.subject_id == subject_id)
                .order_by(Question.created_at.desc(), Question.id)
                .limit(MAX_EXISTING_ROWS)
            )
        )

    def is_near_duplicate(self, subject_id: uuid.UUID, prompt: str) -> bool:
        """Layer 1 on stored questions (AC3): `pg_trgm` similarity against every question of the
        subject, whatever its status."""
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        Question.user_id == self.user_id,
                        Question.subject_id == subject_id,
                        func.similarity(Question.prompt, prompt) >= TRIGRAM_THRESHOLD,
                    )
                )
            )
        )

    # --- The running guard ------------------------------------------------------------------

    def begin(
        self, subject_id: uuid.UUID, kind: str, target_id: uuid.UUID, now: dt.datetime
    ) -> QuestionGeneration | None:
        """Mark the press as running, or None when one is already running for the target (a
        second click or tab). A row left by a crash older than a minute is replaced."""
        self.session.execute(
            delete(QuestionGeneration).where(
                QuestionGeneration.user_id == self.user_id,
                QuestionGeneration.subject_id == subject_id,
                QuestionGeneration.target_kind == kind,
                QuestionGeneration.target_id == target_id,
                QuestionGeneration.status == "running",
                QuestionGeneration.created_at < now - dt.timedelta(seconds=RUNNING_STALE_SECONDS),
            )
        )
        row = QuestionGeneration(
            user_id=self.user_id,
            subject_id=subject_id,
            target_kind=kind,
            target_id=target_id,
            created_at=now,
        )
        try:
            with self.session.begin_nested():
                self.session.add(row)
        except IntegrityError:
            return None
        return row

    def finish(self, generation: QuestionGeneration, now: dt.datetime) -> None:
        generation.status = "done"
        generation.finished_at = now
        self.session.flush()

    def drop_running(self, generation: QuestionGeneration) -> None:
        self.session.delete(generation)
        self.session.flush()

    # --- Candidates -------------------------------------------------------------------------

    def open_for(self, subject_id: uuid.UUID, kind: str, target_id: uuid.UUID) -> list[Question]:
        """Candidates of this target still waiting for "Đưa vào luyện tập" or "Không giữ"."""
        return list(
            self.session.scalars(
                self._open_query(subject_id)
                .join(
                    QuestionGeneration,
                    and_(
                        QuestionGeneration.id == Question.generation_id,
                        QuestionGeneration.user_id == self.user_id,
                    ),
                )
                .where(
                    QuestionGeneration.target_kind == kind,
                    QuestionGeneration.target_id == target_id,
                )
            )
        )

    def open_of_subject(self, subject_id: uuid.UUID) -> list[Question]:
        return list(self.session.scalars(self._open_query(subject_id)))

    def _open_query(self, subject_id: uuid.UUID) -> Select[tuple[Question]]:
        return (
            select(Question)
            .where(
                Question.user_id == self.user_id,
                Question.subject_id == subject_id,
                Question.source == "generated",
                Question.status == "active",
                Question.quality_status == "ok",
                Question.kept_at.is_(None),
            )
            .order_by(Question.created_at, Question.id)
        )

    def add_candidate(
        self,
        *,
        subject_id: uuid.UUID,
        generation_id: uuid.UUID,
        type_id: uuid.UUID | None,
        prompt: str,
        reference_answer: str,
        rubric: list[str],
        run_id: uuid.UUID,
        unit_ids: list[uuid.UUID],
    ) -> Question | None:
        """Store one candidate that passed both filters, with the units it checks. None when an
        active question already has this exact text (the partial unique index)."""
        question_id = uuid.uuid4()
        inserted = self.session.execute(
            insert(Question)
            .values(
                id=question_id,
                user_id=self.user_id,
                subject_id=subject_id,
                level=GENERATED_LEVEL,
                prompt=prompt,
                reference_answer=reference_answer,
                rubric=rubric,
                status="active",
                content_hash=content_hash(prompt),
                run_id=run_id,
                source="generated",
                type_id=type_id,
                quality_status="ok",
                answer_text=reference_answer,
                answer_origin="ai",
                generation_id=generation_id,
                # Not now(): the candidates of one press keep the order they were stored in.
                created_at=func.clock_timestamp(),
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "subject_id", "content_hash"],
                index_where=text("status = 'active'"),
            )
            .returning(Question.id)
        ).scalar_one_or_none()
        if inserted is None:
            return None
        for unit_id in unit_ids:
            self.session.add(
                QuestionUnit(
                    user_id=self.user_id,
                    subject_id=subject_id,
                    question_id=question_id,
                    unit_id=unit_id,
                )
            )
        self.session.flush()
        question = self.get(question_id)
        assert question is not None
        self.session.refresh(question)
        return question

    def candidate(self, question_id: uuid.UUID) -> Question | None:
        """A generated question of this user, whatever its state; None otherwise."""
        return self.session.scalars(
            select(Question).where(
                Question.user_id == self.user_id,
                Question.id == question_id,
                Question.source == "generated",
            )
        ).first()
