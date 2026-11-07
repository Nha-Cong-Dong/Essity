# AI

All model calls live in `services/ai-service`. core-api never calls a provider directly. The production model is Anthropic Claude Haiku (`claude-haiku-5-5`).

## Provider

`AI_LLM_PROVIDER` has no default and must be set:

| Value | Behaviour |
|---|---|
| `fake` | Deterministic fake grader; allowed only in `local` and `test`. Used by development and CI. |
| `anthropic` | Real calls; requires `ANTHROPIC_API_KEY`. Optional `ANTHROPIC_BASE_URL` for an Anthropic-compatible endpoint. |
| `disabled` | Starts without a key; grading answers 503 `grading_disabled`. |

## Models and pricing

The task-to-model table is `llm_models` in `ai_service/config.py`; override it with `AI_LLM_MODELS` (JSON). By default every task uses `claude-haiku-5-5`. Every configured model must have a price in `ai_service/llm/pricing.py`, otherwise the service refuses to start. Adding a model means adding its price first.

## Tasks

Task names are defined in `llm/types.py`; prompts are versioned files in `services/ai-service/prompts/`.

| Group | Tasks |
|---|---|
| Grading | `grade`, `grade_practice` |
| Documents and outline | `chunk_units`, `draft_units`, `draft_answer`, `merge_drafts`, `syllabus_toc`, `pick_sections` |
| Session notes | `extract_session`, `read_notes` |
| Practice | `generate_questions`, `generate_like`, `judge_questions`, `parse_question_bank` |
| Commands and graph | `parse_command`, `propose_edges` |

Cards drafted by `draft_units` and `merge_drafts` are written directly into the learner's vault.

## HTTP surface

core-api calls ai-service with `X-Service-Token`: grading (`POST /v1/grade`, `/v1/grade-practice`), commands, question-bank and practice generation, notes extraction, edge proposals. Document indexing and session processing run asynchronously through Redis Streams (see [ARCHITECTURE.md](ARCHITECTURE.md)).

## Cost control

Per-user quota, checked before every call (`llm/quota.py`):

- UTC daily and monthly windows. Defaults: `AI_QUOTA_DAILY_USD=0.20`, `AI_QUOTA_MONTHLY_USD=2.00`.
- Spend is the sum of recorded call costs plus reservations for calls in flight, taken under a per-user advisory lock.
- Grading is held to `limit x AI_QUOTA_HARD_CAP_FACTOR` (default 3) and refused beyond it; other tasks (such as indexing) are deferred at the plain limit.
- Costs are exact decimals rounded up to the micro-dollar, including prompt-cache write and read multipliers.
- If spend cannot be read, the call is not made (fail closed).

## Quality checks

- **Anchor check.** Quoted evidence must appear in the source passage (`domain/anchor_check.py`); grades with invented quotes are rejected.
- **Evals.** `services/ai-service/evals/` holds suites for grade, grade_practice, draft_units, extract, generate_similar, link_question and ocr, with a runner in `evals/framework`. CI uses the fake provider only. Real runs are manual and cost-capped (`--max-cost-usd`); see `evals/README.md`.
- **Eval data.** Export includes only accounts that consented (`core_api/cli_export_eval.py`).
