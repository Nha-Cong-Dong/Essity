"""ai-service's POST /v1/parse-command answer, as core-api reads it (T9.2e). core-api cannot
import ai-service, so this is its own strict copy. `result` is one operation as JSON (or
`{"kind": "unclear", "reason": ...}`): core-api validates it with the same code as the ops a
client sends (`command_codec.validate_ops`), so the model's word alone never runs anything."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class ParseCommandReply(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID
    result: dict[str, Any]
