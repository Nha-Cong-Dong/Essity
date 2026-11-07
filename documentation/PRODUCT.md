# Product

Essity is an AI-graded spaced-repetition app for students. A learner uploads course material and notes, organises it into subjects, and studies a daily set of questions. Free-text answers are graded by an LLM against passages of the learner's own material. The schedule adapts to what the learner actually remembers.

The web UI is in Vietnamese (`<html lang="vi">`).

## Users

Students preparing for exams. Accounts use email and password with email verification and password reset. A user can export or delete their data (`api/export.py`, `domain/delete_user.py`).

## Features present in the code

Paths under "Backend" are relative to `services/core-api/src/core_api/` unless prefixed `ai-service`.

| Area | What it does | Web route | Backend |
|---|---|---|---|
| Accounts | Register, verify email, log in, reset password | `/register`, `/verify-email`, `/login`, `/forgot-password`, `/reset-password` | `api/auth.py`, `api/me.py` |
| Subjects | Create and list subjects; per-subject overview | `/subjects`, `/subjects/[id]` | `api/subjects.py` |
| Documents | Upload files (PDF, DOCX, PPTX, images), index into knowledge units | `/subjects/[id]/upload`, `/subjects/[id]/documents` | `api/documents.py`; ai-service `tasks/index_document.py`, `tasks/outline_*.py` |
| Syllabus / outline | Table of contents per subject; edit by hand or natural-language command | `/subjects/[id]/syllabus` | `api/outline.py`, `api/outline_chat.py`, `api/commands.py` |
| Knowledge vault | Browse and edit knowledge units; AI-drafted units land here directly | `/kho-kien-thuc` | `api/vault.py`, `api/units.py` |
| Today | Daily prioritised queue, ranked by forgetting risk and exam proximity | `/today` | `api/today.py`, `domain/today_v2.py` |
| Study sessions | Answer questions in free text; graded with feedback and source anchors | `/subjects/[id]/sessions/*`, `/review/[id]` | `api/sessions.py`, `api/review_sessions.py`, `api/attempts.py`, `api/grades.py` |
| Practice | Practice questions by type, generated from material or modelled on an imported question bank | `/subjects/[id]/practice` | `api/practice.py`, `api/generated_questions.py`, `api/question_banks.py` |
| Session notes | Photographed or typed study notes turned into session results | session pages | `api/session_notes.py`; ai-service `tasks/extract_session.py`, `tasks/read_notes_image.py` |
| Knowledge graph | Concept graph with prerequisite edges, per subject and global | `/subjects/[id]/graph`, `/graph` | `api/graph.py`, `api/suggestions.py` |
| Stats | Progress, mastery and readiness | `/stats` | `api/stats.py`, `domain/mastery.py`, `domain/readiness.py` |
| Scheduling | Per-knowledge-unit memory state with FSRS; per-user parameter fitting weekly | n/a | `domain/scheduling/`, `jobs/optimize_fsrs.py` |

## Not present

Mobile apps, shared decks or social features, payments, and third-party sign-in are not implemented. `apps/web/app/design-preview/` holds static design previews, not product features.

## Principles visible in the design

- Source-anchored: grades reference the passage they come from (`ai-service/.../domain/anchor_check.py`).
- Raw data is kept; AI outputs are versioned by prompt and model (`services/ai-service/prompts/`).
- No comparison of grades or effort between users.
