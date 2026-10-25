from fastapi import APIRouter

from ai_service.config import get_settings

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    # `grading` lets a deploy without a key (llm_provider disabled) be told apart from a
    # working one: both are up, only one grades.
    return {
        "status": "ok",
        "grading": "enabled" if get_settings().grading_enabled else "disabled",
    }
