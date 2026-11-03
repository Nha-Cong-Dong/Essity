// T7.17 (US-02 AC1): "Ghi buổi học" opens the v2 study session, not the v1 confirm card.
import { expect, it } from "vitest";

import { newSessionTarget, sectionParam, studyHref } from "@/lib/session-study/entry";

const SUBJECT = "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b";
const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";

it("no ?session= goes to the study session start", () => {
  expect(newSessionTarget(SUBJECT, undefined)).toBe(`/subjects/${SUBJECT}/sessions/study`);
  expect(newSessionTarget(SUBJECT, ["x", "y"])).toBe(`/subjects/${SUBJECT}/sessions/study`);
  expect(newSessionTarget(SUBJECT, "not-an-id")).toBe(`/subjects/${SUBJECT}/sessions/study`);
});

it("a saved v1 session id keeps the v1 saved view", () => {
  expect(newSessionTarget(SUBJECT, SESSION)).toBeNull();
});

it("v1=1 (submissions off) shows v1, no loop", () => {
  expect(newSessionTarget(SUBJECT, undefined, "1")).toBeNull();
});

// T7.19 F2. Red when: the suggestion's section is dropped on the way to the study session, a
// made-up value is carried on, or "Học tự do" (no section) gets one.
it("studyHref carries a suggested section, only when it is an id", () => {
  expect(studyHref(SUBJECT)).toBe(`/subjects/${SUBJECT}/sessions/study`);
  expect(studyHref(SUBJECT, null)).toBe(`/subjects/${SUBJECT}/sessions/study`);
  expect(studyHref(SUBJECT, "../x")).toBe(`/subjects/${SUBJECT}/sessions/study`);
  expect(studyHref(SUBJECT, SESSION)).toBe(`/subjects/${SUBJECT}/sessions/study?section=${SESSION}`);
});

it("sectionParam reads one id from the query, nothing else", () => {
  expect(sectionParam(SESSION)).toBe(SESSION);
  expect(sectionParam(["a", SESSION])).toBeNull();
  expect(sectionParam("nope")).toBeNull();
  expect(sectionParam(undefined)).toBeNull();
});

it("the redirect from /sessions/new keeps the section", () => {
  expect(newSessionTarget(SUBJECT, undefined, undefined, SESSION)).toBe(`/subjects/${SUBJECT}/sessions/study?section=${SESSION}`);
});
