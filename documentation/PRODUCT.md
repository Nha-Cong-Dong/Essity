# Product

Essity is an AI-graded spaced-repetition app for students. A learner uploads course material, organises it into subjects, and studies a daily set of questions. Free-text answers are graded by an LLM against passages of the learner's own material. FSRS schedules each knowledge unit and each practice question, so the queue follows what the learner remembers.

The web UI is in Vietnamese (`<html lang="vi">`).

## Users

Students preparing for exams. Accounts use email and password; email verification and password reset are sent over SMTP. A user can export or delete their data (`api/export.py`, `domain/delete_user.py`).

## Core concepts

| Concept | Meaning |
|---|---|
| Subject | A course or exam topic; owns documents, outline, units, sessions and an exam date |
| Document | An uploaded PDF, DOCX, PPTX or image, indexed asynchronously |
| Knowledge unit (card) | A unit of knowledge with a source anchor; the vault (Kho) holds all units and is the source of truth |
| Practice question | A question generated from material or modelled on an imported bank; scheduled by FSRS per question, separately from unit schedules |
| Session | A study run: answer, get graded, see feedback, finish with a summary |

AI-drafted units are written directly into the vault; there is no draft or review queue. The learner edits them in place.

## Features

Backend paths are relative to `services/core-api/src/core_api/` unless prefixed `ai-service`.

| Area | What it does | Web route | Backend |
|---|---|---|---|
| Landing | Public page; signed-in users are redirected | `/` | n/a |
| Accounts | Register, verify email, log in, reset password | `/register`, `/check-email`, `/verify-email`, `/login`, `/forgot-password`, `/reset-password` | `api/auth.py`, `api/me.py`, `jobs/send_email.py` |
| Subjects | Create and list subjects; per-subject overview | `/subjects`, `/subjects/new`, `/subjects/[id]` | `api/subjects.py` |
| Documents | Upload files directly to object storage, index into units | `/subjects/[id]/upload`, `/subjects/[id]/documents`, `/subjects/[id]/documents/[docId]` | `api/documents.py`; ai-service `tasks/index_document.py`, `tasks/outline_*.py` |
| Syllabus | Table of contents per subject; edit by hand or with a natural-language command | `/subjects/[id]/syllabus` | `api/outline.py`, `api/outline_chat.py`, `api/commands.py` |
| Knowledge vault | Browse and edit units | `/kho-kien-thuc` | `api/vault.py`, `api/units.py` |
| Today | Daily queue ranked by forgetting risk, exam proximity and prerequisites | `/today` | `api/today.py`, `domain/today_v2.py` |
| Study sessions | Free-text answers graded with feedback and source anchors; review of results | `/subjects/[id]/sessions/new`, `/subjects/[id]/sessions/study`, `/subjects/[id]/sessions/[sid]`, `/review/[id]` | `api/sessions.py`, `api/review_sessions.py`, `api/attempts.py`, `api/grades.py`, `api/submissions.py` |
| Practice | Practice questions by type, from material or an imported question bank | `/subjects/[id]/practice` | `api/practice.py`, `api/generated_questions.py`, `api/question_banks.py` |
| Session notes | Typed or photographed notes turned into session results | session pages | `api/session_notes.py`; ai-service `tasks/extract_session.py`, `tasks/read_notes_image.py` |
| Knowledge graph | Concept graph with prerequisite edges, per subject and global | `/subjects/[id]/graph`, `/graph` | `api/graph.py`, `api/suggestions.py` |
| Stats | Progress, mastery, readiness | `/stats` | `api/stats.py`, `domain/mastery.py`, `domain/readiness.py` |
| Scheduling | FSRS memory state per unit and per practice question; weekly per-user parameter fitting | n/a | `domain/scheduling/`, `jobs/optimize_fsrs.py` |
| Data control | Export and delete account data | account menu | `api/export.py`, `domain/delete_user.py`, `jobs/erase_user_sweep.py` |

## Not built

Mobile apps, shared decks or social features, and payments are not implemented. Google sign-in is drawn on the login page but disabled (`GOOGLE_SIGN_IN_ENABLED = false` in `apps/web/lib/auth-flags.ts`; `GOOGLE_*` variables are reserved). `apps/web/app/design-preview/` holds static design previews, not product features, and is hidden outside development unless `WEB_DESIGN_PREVIEW=1`.

## Principles visible in the design

- Source-anchored: grades quote the passage they come from, and the quote is verified against the source (`ai-service` `domain/anchor_check.py`).
- Raw data is kept; AI outputs are versioned by prompt and model (`services/ai-service/prompts/`).
- No comparison of grades or effort between users.
- AI spend is capped per user (see [AI.md](AI.md)).
