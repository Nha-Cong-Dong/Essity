"""`POST /v1/subjects/{subject_id}/outline/chat` (E3, hackathon 04/11): the outline-customise chat
in plain Vietnamese. The sentence goes to the same parser and the same validator as the command
bar (`POST /v1/commands`, T9.2), limited to the operations that change an outline (leave out,
mark studied, set pages); the answer is a short Vietnamese sentence the page shows as-is.
Nothing here is an error for the learner: every failure becomes a friendly `reply`.
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from core_api.api.commands import MAX_COMMAND_CHARS, Ai
from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.text import storable_text
from core_api.clients.ai_client import NotGraded
from core_api.db.session import DbSession
from core_api.domain.commands.registry import CommandRejected
from core_api.repositories.subject import SubjectRepository
from core_api.services.command_context import build_parse_payload
from core_api.services.commands import ApplyOutcome, CommandIdReused, CommandRequest, CommandService
from core_api.services.suggestions import learning_today

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

OUTLINE_KINDS = frozenset({"section_exclude", "section_mark", "section_set_pages"})

HINT = (
    "Mình chưa hiểu ý bạn. Bạn thử nói rõ hơn, ví dụ: “bỏ phần phụ lục”, "
    "“bỏ mục 1.2”, “đánh dấu chương 2 là đã học”."
)
UNSUPPORTED = (
    "Mình chưa làm được việc đó trong đề cương. Mình có thể bỏ mục khỏi đề cương hoặc đánh dấu "
    "mục đã học, ví dụ: “bỏ phần phụ lục”. Gộp hoặc tách mục thì bạn dùng nút Chỉnh sửa nhé."
)
QUOTA = "Trợ lý AI đã dùng hết lượt hôm nay. Bạn dùng nút Chỉnh sửa để bỏ mục nhé."
BUSY = "Trợ lý đang bận, bạn thử lại sau ít giây nhé."


class OutlineChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[
        str,
        StringConstraints(min_length=1, max_length=MAX_COMMAND_CHARS),
        AfterValidator(storable_text),
    ]
    command_id: uuid.UUID | None = None
    screen_session_id: uuid.UUID | None = None


class OutlineChatOut(BaseModel):
    status: Literal["applied", "unclear", "failed"]
    reply: str
    command_id: uuid.UUID | None = None
    affected: int = 0


class _Stop(Exception):
    def __init__(self, status: Literal["unclear", "failed"], reply: str) -> None:
        super().__init__(reply)
        self.status: Literal["unclear", "failed"] = status
        self.reply = reply


def _titles(diff: list[dict[str, Any]], key: str) -> list[str]:
    out: list[str] = []
    for item in diff:
        state = item.get(key)
        title = state.get("title") if isinstance(state, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(title, str) and title.strip():
            out.append(title.strip())
    return out


def reply_for(outcome: ApplyOutcome) -> str:
    """A short Vietnamese confirmation of what ran."""
    kind = outcome.op_kinds[0] if outcome.op_kinds else ""
    names = _titles(list(outcome.diff), "after")
    shown = ", ".join(f"“{n}”" for n in names[:3]) + (" và vài mục khác" if len(names) > 3 else "")
    what = f" ({shown})" if shown else ""
    match kind:
        case "section_exclude":
            return f"Đã bỏ {outcome.affected} mục khỏi đề cương{what}. Bấm Hoàn tác nếu bạn đổi ý."
        case "section_mark":
            return f"Đã cập nhật trạng thái đã học cho {outcome.affected} mục{what}."
        case "section_set_pages":
            return f"Đã chỉnh lại số trang của mục{what}."
        case _:
            return "Đã xong."


@router.post("/subjects/{subject_id}/outline/chat")
def outline_chat(
    subject_id: uuid.UUID,
    body: OutlineChatIn,
    user: VerifiedUser,
    session: DbSession,
    ai: Ai,
    now: Now,
) -> OutlineChatOut:
    if SubjectRepository(session, user.id).get(subject_id) is None:
        raise HTTPException(status_code=404, detail="subject_not_found")
    command_id = body.command_id or uuid.uuid4()

    def parse(text: str) -> Sequence[Mapping[str, Any]]:
        payload = build_parse_payload(session, user.id, subject_id, text, learning_today(user, now))
        session.commit()  # no transaction stays open while the model answers
        reply = ai.parse_command(jsonable_encoder(payload))
        if isinstance(reply, NotGraded):
            raise _Stop("failed", QUOTA if reply.failure == "quota" else BUSY)
        result = reply.result
        kind = result.get("kind")
        if kind == "unclear":
            raise _Stop("unclear", HINT)
        if kind not in OUTLINE_KINDS:
            raise _Stop("unclear", UNSUPPORTED)
        return [result]

    try:
        outcome = CommandService(session, user.id).apply(
            command_id,
            body.screen_session_id or uuid.uuid4(),
            CommandRequest(body.text, None),
            parse=parse,
            now=now,
        )
    except _Stop as stop:
        return OutlineChatOut(status=stop.status, reply=stop.reply)
    except CommandIdReused:
        return OutlineChatOut(status="failed", reply=BUSY)
    except CommandRejected:
        return OutlineChatOut(status="unclear", reply=HINT)
    return OutlineChatOut(
        status="applied",
        reply=reply_for(outcome),
        command_id=outcome.command_id,
        affected=outcome.affected,
    )
