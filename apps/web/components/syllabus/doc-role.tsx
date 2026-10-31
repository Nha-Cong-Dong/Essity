"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { type ApiRole, patchDocument, putTextbook } from "@/lib/syllabus/api";
import type { Role } from "@/lib/syllabus/roles";

import { RolePicker } from "./role-picker";

// T7.5 (US-01 AC4, AC5; DESIGN §6.4; design-decisions.md R2.5): the role of one uploaded document,
// on the real API. The look is T7.5a's RolePicker. Main textbook: core-api only accepts it on a
// document that has been read, so the choice waits (and says so) until then; when the subject
// already has one, nothing is replaced until the learner agrees, and a second agreement is asked
// when live cards are linked to the old one (the card count comes from core-api's 409).

const POLL_MS = 3000;
const MAX_WAIT = 100; // 5 minutes of 3 s

const API_ROLE: Record<Role, ApiRole> = { main: "textbook", bank: "question_bank", supplementary: "auxiliary" };

type Phase =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "waiting" }
  | { kind: "confirm" }
  | { kind: "confirm-cards"; cards: number }
  | { kind: "error" };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function DocRole({
  subjectId,
  documentId,
  name,
  initialRole,
}: {
  subjectId: string;
  documentId: string;
  name: string;
  initialRole: Role;
}) {
  const [role, setRole] = useState<Role>("supplementary");
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  // What core-api has (a new document is "auxiliary"), and which pick is current: a pick made while
  // an older one still waits cancels it.
  const saved = useRef<Role>("supplementary");
  const ticket = useRef(0);
  const started = useRef(false);
  const alive = useRef(false);
  const confirmButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (phase.kind === "confirm" || phase.kind === "confirm-cards") confirmButton.current?.focus();
  }, [phase.kind]);

  useEffect(() => {
    alive.current = true;
    if (!started.current) {
      started.current = true;
      if (initialRole !== "supplementary") void pick(initialRole);
    }
    return () => {
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stale = (mine: number) => mine !== ticket.current || !alive.current;

  async function becomeMain(mine: number, replace: boolean, confirm: boolean) {
    for (let tries = 0; tries < MAX_WAIT; tries++) {
      const sent = replace
        ? await putTextbook(subjectId, documentId, confirm)
        : await patchDocument(documentId, { role: "textbook" });
      if (stale(mine)) return;
      if (sent.ok) {
        saved.current = "main";
        return setPhase({ kind: "idle" });
      }
      if (sent.code === "document_not_ready") {
        setPhase({ kind: "waiting" });
        await sleep(POLL_MS);
        if (stale(mine)) return;
        continue;
      }
      if (sent.code === "textbook_exists") return setPhase({ kind: "confirm" });
      if (sent.code === "textbook_has_cards") return setPhase({ kind: "confirm-cards", cards: sent.cards ?? 0 });
      return setPhase({ kind: "error" });
    }
    setPhase({ kind: "error" });
  }

  async function pick(next: Role) {
    const mine = ++ticket.current;
    setRole(next);
    if (next === saved.current) return setPhase({ kind: "idle" });
    setPhase({ kind: "saving" });
    if (next === "main") return becomeMain(mine, false, false);
    const sent = await patchDocument(documentId, { role: API_ROLE[next] });
    if (stale(mine)) return;
    if (sent.ok || sent.code === "nothing_to_change") {
      saved.current = next;
      return setPhase({ kind: "idle" });
    }
    setPhase({ kind: "error" });
  }

  function keepOld() {
    ticket.current += 1;
    setRole(saved.current);
    setPhase({ kind: "idle" });
  }

  const replace = (confirm: boolean) => {
    const mine = ++ticket.current;
    setPhase({ kind: "saving" });
    void becomeMain(mine, true, confirm);
  };

  return (
    <div className="flex flex-col gap-2" data-doc-role={documentId}>
      <RolePicker file={{ id: documentId, name, kind: "pdf", role, state: "ready" }} onPick={(next) => void pick(next)} />
      <div role="status" className="text-small text-ink-soft">
        {phase.kind === "saving" && "Đang lưu…"}
        {phase.kind === "waiting" && "Sẽ đặt làm giáo trình chính khi đọc xong."}
      </div>
      {phase.kind === "error" && (
        <p role="alert" className="m-0 flex flex-wrap items-center gap-x-2 text-small">
          Chưa đổi được vai trò.
          <Button variant="quiet" onClick={() => void pick(role === saved.current ? "supplementary" : role)}>
            Thử lại
          </Button>
        </p>
      )}
      {(phase.kind === "confirm" || phase.kind === "confirm-cards") && (
        <div role="group" aria-label="Đổi giáo trình chính" className="flex flex-col gap-2 rounded-sheet bg-sunken p-4" data-confirm-replace>
          <p className="m-0 text-body">
            {phase.kind === "confirm"
              ? "Môn này đã có giáo trình chính. Đổi sang file này? Giáo trình cũ thành tài liệu phụ, không bị xóa."
              : `${phase.cards} thẻ đang gắn với giáo trình cũ. Thẻ vẫn được giữ, nhưng đề cương mới bắt đầu từ đầu.`}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button ref={confirmButton} onClick={() => replace(phase.kind === "confirm-cards")}>
              {phase.kind === "confirm" ? "Đổi giáo trình chính" : "Vẫn đổi"}
            </Button>
            <Button variant="quiet" onClick={keepOld}>
              Giữ giáo trình cũ
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
