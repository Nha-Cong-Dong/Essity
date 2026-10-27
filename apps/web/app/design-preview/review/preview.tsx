"use client";

import { ReviewScreen } from "@/components/review/review-screen";
import type { AttemptView, Current, Reply, ReviewApi } from "@/lib/review-client";

// The answer screen with fixed data and no core-api (ADR-0025): the busiest question (a long
// subject name, a long prompt, one long word), and the answers it grades with, for the layout test.

const ATTEMPT = "0b8f1d2e-0000-4000-8000-0000000000a1";
const LONG_WORD = "Kiếntrúcmáytínhvàhệđiềuhànhnângcaohọckỳhainămhaingànhaimươisáu" + "_kếtthúc";

const STEP: Current = {
  done: false,
  ungraded: [],
  position: 7,
  total: 14,
  question: {
    id: "0b8f1d2e-0000-4000-8000-0000000000b1",
    prompt:
      "Gói SYN-ACK trong quá trình bắt tay ba bước bị mất. Client và server sẽ làm gì tiếp theo, và vì sao " +
      LONG_WORD +
      "?",
    subject: { id: "0b8f1d2e-0000-4000-8000-000000000001", name: LONG_WORD },
    unit_ids: [],
  },
  attempt: {
    id: ATTEMPT,
    status: "draft",
    answer_text: "Client không nhận được SYN-ACK nên chờ hết timeout rồi gửi lại SYN. " + LONG_WORD,
    dont_remember: false,
  },
};

function graded(text: string, dontRemember: boolean): AttemptView {
  return {
    status: "submitted",
    grading: "graded",
    failure: null,
    result: {
      grade_id: "0b8f1d2e-0000-4000-8000-0000000000e1",
      overall: dontRemember ? "forgot" : "partial",
      understanding: dontRemember ? null : 1,
      missing: dontRemember
        ? []
        : ["Server giữ trạng thái SYN-RECEIVED và gửi lại SYN-ACK.", "Hết số lần thử thì huỷ kết nối. " + LONG_WORD],
      units: [
        { unit_id: "0b8f1d2e-0000-4000-8000-0000000000c1", title: "Thiết lập kết nối TCP", verdict: "correct" },
        { unit_id: "0b8f1d2e-0000-4000-8000-0000000000c2", title: "Cơ chế timeout và gửi lại " + LONG_WORD, verdict: "incorrect" },
      ],
      reference_answer:
        "Client hết timeout thì gửi lại SYN; server ở SYN-RECEIVED gửi lại SYN-ACK. Hết số lần thử thì huỷ kết nối.",
      sources: [
        {
          anchor_id: "0b8f1d2e-0000-4000-8000-0000000000d1",
          quote_text: "Nếu SYN-ACK bị mất, server giữ trạng thái SYN-RECEIVED và gửi lại sau timeout. " + LONG_WORD,
          kind: "document",
          page_no: 47,
        },
        { anchor_id: "0b8f1d2e-0000-4000-8000-0000000000d2", quote_text: "SYN gửi lại sau 1 s, 2 s, 4 s.", kind: "notes", page_no: null },
      ],
      practice: true,
    },
    answer_text: text,
    submitted_at: "2026-10-21T14:42:00Z",
    question: { id: STEP.question.id, prompt: STEP.question.prompt },
  };
}

const ok = <T,>(data: T): Promise<Reply<T>> => Promise.resolve({ ok: true, data });

const API: ReviewApi = {
  current: () => ok(STEP),
  open: () => ok(STEP.attempt!),
  stop: () => ok({ answered: 7, total: 14 }),
  saveDraft: () => ok(null),
  submit: (_, answer) => ok(graded(answer.answer_text, answer.dont_remember)),
  regrade: () => ok(graded("", false)),
  read: () => ok(graded("", false)),
};

export function ReviewPreview() {
  return <ReviewScreen sessionId="0b8f1d2e-0000-4000-8000-0000000000e1" api={API} />;
}
