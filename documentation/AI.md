# AI

All model calls live in `services/ai-service`. core-api never calls a provider directly.

## Provider and models

`AI_LLM_PROVIDER` has no default and must be set:

| Value | Behaviour |
|---|---|
| `fake` | Deterministic fake grader; allowed only in `local` and `test` |
| `anthropic` | Real calls; requires `ANTHROPIC_API_KEY` (optional `ANTHROPIC_BASE_URL` for an Anthropic-compatible endpoint) |
| `disabled` | Starts without a key; grading answers 503 `grading_disabled` |

The task-to-model table is `llm_models` in `ai_service/config.py` (override with `AI_LLM_MODELS` as JSON). By default every task uses `claude-haiku-5-5`. Every configured model must have a price in `ai_service/llm/pricing.py`, otherwise the service refuses to start.

## Tasks

`grade`, `grade_practice`, `extract_session`, `read_notes`, `chunk_units`, `draft_units`, `draft_answer`, `merge_drafts`, `generate_questions`, `generate_like`, `judge_questions`, `parse_question_bank`, `parse_command`, `syllabus_toc`, `propose_edges`, `pick_sections` (see `llm/types.py`). Prompts are versioned files in `services/ai-service/prompts/`.

## Cost control

Per-user quota, checked before every call (`llm/quota.py`):

- UTC daily and monthly windows; defaults `AI_QUOTA_DAILY_USD=0.20`, `AI_QUOTA_MONTHLY_USD=2.00`.
- Spend is the sum of recorded call costs plus reservations for calls in flight, taken under a per-user advisory lock.
- Grading is held to `limit x AI_QUOTA_HARD_CAP_FACTOR` (default 3) and refused beyond it; other tasks (such as indexing) are deferred at the plain limit.
- Costs are exact decimals rounded up to the micro-dollar, including prompt-cache write and read multipliers.
- If spend cannot be read, the call is not made (fail closed).

## Quality checks

- Anchor check: quoted evidence must appear in the source passage (`domain/anchor_check.py`).
- Evals: `services/ai-service/evals/` (suites for grade, grade_practice, draft_units, extract, generate_similar, link_question, ocr). CI uses the fake provider only; real runs are manual and cost-capped (`--max-cost-usd`). See `evals/README.md`.
- Eval export includes only accounts that consented (`core_api/cli_export_eval.py`).
