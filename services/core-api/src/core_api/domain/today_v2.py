"""Compose the v2 Today screen (T7.11a, v2 design §6.2, US-03 AC1/AC3/AC4/AC7/AC10, US-15 AC11).
Pure: no database, no AI. The v1 composer (`today.py`) stays live; this module only imports it.

Three parts plus an optional fourth:

- `next_study`: the top 2 subjects from `suggest` with a short reason each, or one neutral reason
  line plus links to Review, Practice and Subjects when nothing can be suggested.
- `review`: due canonical cards only, at most `MAX_QUESTIONS` / `MAX_MINUTES` like v1, riskiest
  first (recall now times the v1 exam weight). A card saved today enters from the next learning day.
  No total backlog is exposed: only the items of today.
- `unfinished`: one line per study session with draft cards left or a submission waiting for the
  AI, linking to that session.
- `practice` (T8.5): typed optional field; the other parts do not depend on it.

Small choices the spec leaves open: a card's "why" line states its recall chance in whole percent;
when several reasons for an empty `next_study` hold, exam-over wins over "no syllabus", which wins
over "all studied"; a filter that hides every subject has its own line.
"""

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import learning_day
from core_api.domain.suggest import (
    SubjectInput,
    SuggestFilter,
    Suggestion,
    suggest_today,
)
from core_api.domain.today import (
    MAX_MINUTES,
    MAX_QUESTIONS,
    MINUTES_PER_QUESTION,
    exam_weight,
)

_ONE_DAY = timedelta(days=1)
Link = Literal["review", "practice", "subjects"]
EMPTY_LINKS: tuple[Link, ...] = ("review", "practice", "subjects")

REASON_NO_SUBJECTS = "Chưa có môn nào."
REASON_EXAMS_OVER = "Các môn đã thi xong."
REASON_NO_SYLLABUS = "Chưa có giáo trình để gợi ý."
REASON_ALL_STUDIED = "Đã học hết đề cương."
REASON_FILTERED = "Bộ lọc tuần này đã ẩn hết các môn."


@dataclass(frozen=True)
class ReviewCard:
    """A canonical card with its schedule. `recall` = probability of recall now (0..1)."""

    card_id: uuid.UUID
    subject_id: uuid.UUID
    created_at: datetime
    due: datetime
    recall: float


@dataclass(frozen=True)
class DraftSession:
    """A study session with draft cards not yet reviewed, or a submission waiting for the AI."""

    session_id: uuid.UUID
    subject_id: uuid.UUID
    draft_cards: int
    pending_ai: bool
    updated_at: datetime


@dataclass(frozen=True)
class PracticeLine:
    subject_id: uuid.UUID
    ready_questions: int
    question_types: int


@dataclass(frozen=True)
class PracticePart:  # filled by T8.5
    lines: tuple[PracticeLine, ...] = ()


@dataclass(frozen=True)
class TodayInputs:
    now: datetime
    tz: ZoneInfo
    day_start_hour: int
    subjects: Sequence[SubjectInput]
    subject_names: Mapping[uuid.UUID, str]
    cards: Sequence[ReviewCard]
    sessions: Sequence[DraftSession] = ()
    filters: SuggestFilter | None = None
    practice: PracticePart | None = None


@dataclass(frozen=True)
class NextStudyItem:
    subject_id: uuid.UUID
    subject_name: str
    suggestion: Suggestion
    reason: str


@dataclass(frozen=True)
class NextStudy:
    items: tuple[NextStudyItem, ...]
    empty_reason: str | None  # set exactly when `items` is empty
    links: tuple[Link, ...]  # set exactly when `items` is empty


@dataclass(frozen=True)
class ReviewItem:
    card_id: uuid.UUID
    subject_id: uuid.UUID
    why: str


@dataclass(frozen=True)
class Review:
    items: tuple[ReviewItem, ...]
    minutes: int
    next_due_day: date | None  # only when nothing is due today
    new_saved_today: bool  # a card saved today waits for the next learning day


@dataclass(frozen=True)
class UnfinishedItem:
    session_id: uuid.UUID
    subject_id: uuid.UUID
    line: str


@dataclass(frozen=True)
class TodayV2:
    day: date
    unfinished: tuple[UnfinishedItem, ...]
    review: Review
    next_study: NextStudy
    practice: PracticePart | None = None


def compose(inputs: TodayInputs) -> TodayV2:
    today = learning_day(inputs.now, inputs.tz, inputs.day_start_hour)
    return TodayV2(
        day=today,
        unfinished=_unfinished(inputs),
        review=_review(inputs, today),
        next_study=_next_study(inputs, today),
        practice=inputs.practice,
    )


def _name(inputs: TodayInputs, subject_id: uuid.UUID) -> str:
    return inputs.subject_names.get(subject_id, "Môn học")


def _unfinished(inputs: TodayInputs) -> tuple[UnfinishedItem, ...]:
    rows = [s for s in inputs.sessions if s.draft_cards > 0 or s.pending_ai]
    rows.sort(key=lambda s: (s.updated_at, str(s.session_id)))
    return tuple(UnfinishedItem(s.session_id, s.subject_id, _session_line(inputs, s)) for s in rows)


def _session_line(inputs: TodayInputs, session: DraftSession) -> str:
    name = _name(inputs, session.subject_id)
    if session.draft_cards > 0:
        line = f"{name}: còn {session.draft_cards} thẻ nháp chưa duyệt."
        return line + (" Bài nộp đang chờ lượt AI." if session.pending_ai else "")
    return f"{name}: bài nộp đang chờ lượt AI; bạn vẫn sửa và thêm thẻ bằng tay được."


def _review(inputs: TodayInputs, today: date) -> Review:
    exams = {s.id: s.exam_date for s in inputs.subjects}
    due: list[tuple[float, datetime, str, ReviewCard]] = []
    next_day: date | None = None
    new_saved_today = False
    for card in inputs.cards:
        saved = learning_day(card.created_at, inputs.tz, inputs.day_start_hour)
        due_day = learning_day(card.due, inputs.tz, inputs.day_start_hour)
        if saved >= today and due_day <= today:  # a new card enters from the next learning day
            new_saved_today = True
        effective = max(due_day, saved + _ONE_DAY)
        if effective <= today:
            risk = card.recall * exam_weight(exams.get(card.subject_id), today)
            due.append((risk, card.due, str(card.card_id), card))
        elif next_day is None or effective < next_day:
            next_day = effective
    due.sort(key=lambda row: row[:3])
    room = min(MAX_QUESTIONS, math.floor(MAX_MINUTES / MINUTES_PER_QUESTION))
    items = tuple(
        ReviewItem(c.card_id, c.subject_id, _card_why(c.recall)) for _, _, _, c in due[:room]
    )
    return Review(
        items=items,
        minutes=math.ceil(len(items) * MINUTES_PER_QUESTION),
        next_due_day=None if items else next_day,
        new_saved_today=new_saved_today,
    )


def _card_why(recall: float) -> str:
    return f"Đến hạn ôn; khả năng nhớ khoảng {round(recall * 100)}%."


def _next_study(inputs: TodayInputs, today: date) -> NextStudy:
    suggestions = suggest_today(inputs.subjects, today, inputs.filters)
    if suggestions:
        by_id = {s.id: s for s in inputs.subjects}
        items = tuple(
            NextStudyItem(
                s.subject_id,
                _name(inputs, s.subject_id),
                s,
                _reason(by_id[s.subject_id], s),
            )
            for s in suggestions
        )
        return NextStudy(items, None, ())
    return NextStudy((), _empty_reason(inputs, today), EMPTY_LINKS)


def _reason(subject: SubjectInput, suggestion: Suggestion) -> str:
    title = suggestion.leaf_title
    if suggestion.partial:
        left = f"{suggestion.remaining_weight:g} {suggestion.unit or ''}".strip()
        return f"Bạn học dở mục {title}: còn {left}."
    position = next(
        (i for i, leaf in enumerate(subject.leaves) if leaf.id == suggestion.leaf_id), 0
    )
    reached = [leaf for leaf in subject.leaves[position + 1 :] if leaf.covered_weight > 0]
    if reached:
        return f"Mục {title} chưa học; bạn đã học tới {reached[-1].title}."
    return f"Mục {title} là mục tiếp theo trong đề cương."


def _empty_reason(inputs: TodayInputs, today: date) -> str:
    if not inputs.subjects:
        return REASON_NO_SUBJECTS
    running = [s for s in inputs.subjects if s.exam_date is None or s.exam_date >= today]
    if not running:
        return REASON_EXAMS_OVER
    flt = inputs.filters or SuggestFilter()
    visible = [
        s
        for s in running
        if (flt.only_subjects is None or s.id in flt.only_subjects)
        and not (s.id in flt.hidden_until and today < flt.hidden_until[s.id])
    ]
    if not visible:
        return REASON_FILTERED
    if not any(s.leaves for s in visible):
        return REASON_NO_SYLLABUS
    return REASON_ALL_STUDIED
