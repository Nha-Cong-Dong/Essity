"""Question bank import rules (T8.1b, US-14): pure functions, no database.

- A bank question is stored word for word as the bank wrote it (the model never edits it, AC1)
  and its answer, when the bank has one, is the standard (`answer_origin = bank`).
- A new question type starts with the default reference time: 60 s per rubric idea, and a bank
  question has no rubric yet (T8.4 drafts it), so one idea (`ref_origin = default`, AC2).
- Importing again adds nothing that is already there: questions match on `content_hash` (AC8),
  which is also what stops the questions a stopped run (`pending_ai`) had split by regex from
  being stored twice when the bank is imported again.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from core_api.clients.bank_contract import BankQuestion
from core_api.domain.question_hash import content_hash

SECONDS_PER_IDEA = 60
# `question.reference_answer` is NOT NULL; a bank question without an answer carries this line
# and has no `answer_text` (the standard answer is `answer_text`, never this line).
NO_ANSWER_LINE = "Bộ câu hỏi không có đáp án cho câu này."
MAX_TYPE_NAME = 100

MSG_PENDING_AI = (
    "Chưa tách được bộ câu lúc này. Bạn nhập lại sau nhé, câu nào đã có sẽ không bị trùng."
)
MSG_FAILED = "Không đọc được bộ câu hỏi này. Thử tải lại file hoặc đổi sang file khác."
MSG_NOTHING = "Không tìm thấy câu hỏi nào trong file này."
UNMAPPED_LINE = "chưa gắn mục"


def default_ref_time_s(ideas: int = 1) -> int:
    return SECONDS_PER_IDEA * max(1, ideas)


def reference_answer_of(answer_text: str | None) -> str:
    return answer_text if answer_text is not None and answer_text.strip() else NO_ANSWER_LINE


def type_name_of(name: str | None) -> str | None:
    """One line, at most `MAX_TYPE_NAME` characters; None when nothing is left."""
    if name is None:
        return None
    clean = " ".join(name.split())[:MAX_TYPE_NAME].strip()
    return clean or None


@dataclass(frozen=True)
class NewQuestion:
    ord: int
    prompt: str
    answer_text: str | None
    source_page: int
    type_name: str | None
    section_ids: list[str]
    content_hash: str


def new_questions(
    questions: Iterable[BankQuestion], known_hashes: set[str]
) -> tuple[list[NewQuestion], int]:
    """The questions not yet stored, in bank order, and how many were skipped as duplicates
    (of a stored question or of an earlier one in the same bank)."""
    seen = set(known_hashes)
    fresh: list[NewQuestion] = []
    duplicates = 0
    for question in sorted(questions, key=lambda q: q.ord):
        digest = content_hash(question.prompt)
        if digest in seen:
            duplicates += 1
            continue
        seen.add(digest)
        answer = question.answer_text if (question.answer_text or "").strip() else None
        fresh.append(
            NewQuestion(
                ord=question.ord,
                prompt=question.prompt,
                answer_text=answer,
                source_page=question.source_page,
                type_name=type_name_of(question.type_name),
                section_ids=list(dict.fromkeys(question.section_ids)),
                content_hash=digest,
            )
        )
    return fresh, duplicates
