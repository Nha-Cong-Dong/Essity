"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import { PdfPage } from "@/components/vault/pdf-page";

import { Doodle } from "@/components/icons/doodle";
import { Markdown } from "@/components/markdown/markdown";
import { Block } from "@/components/screen-kit";
import { Button, buttonVariants } from "@/components/ui/button";
import { Carousel } from "@/components/ui/carousel";
import type { VaultCard } from "@/lib/vault-api";

// G1/G3/G4: the cards of one study session. "Sửa thẻ" edits title and content in place, "Lưu"
// saves (the text becomes the answer reviews compare with), "Xóa thẻ" removes it, "Nguồn" shows the
// page the card came from with the cited passage marked.

type Source = {
  anchor_id: string;
  source: string;
  document_name: string | null;
  page_no: number | null;
  page_text: string | null;
  quote: string;
  highlight: [number, number] | null;
  file_url: string | null;
  image_url: string | null;
  note_image_urls: string[];
};

function Marked({ text, range }: { text: string; range: [number, number] }) {
  return (
    <>
      {text.slice(0, range[0])}
      <mark className="rounded-sm bg-hl px-0.5 text-ink">{text.slice(range[0], range[1])}</mark>
      {text.slice(range[1])}
    </>
  );
}

function SourceItem({ s }: { s: Source }) {
  // The original page first (PDF, drawn by pdf.js with the passage marked), then the page picture
  // (slides, scans) beside the excerpt, then plain text: each step only when the one before fails.
  const [pdfFailed, setPdfFailed] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const fail = useCallback(() => setPdfFailed(true), []);
  const usePdf = s.file_url !== null && s.page_no !== null && !pdfFailed;
  const images = s.image_url !== null ? [s.image_url] : s.note_image_urls;
  const useImage = !usePdf && images.length > 0 && !imageFailed;
  const excerpt =
    s.page_text && s.highlight ? (
      <Marked text={s.page_text} range={s.highlight} />
    ) : (
      <mark className="rounded-sm bg-hl px-0.5 text-ink">{s.quote}</mark>
    );
  return (
    <li className="rounded-control bg-sunken p-3">
      <p className="m-0 mb-1 text-body font-medium">
        {s.source === "notes" ? "Vở ghi" : (s.document_name ?? "Tài liệu")}
        {s.page_no ? ` · trang ${s.page_no}` : ""}
      </p>
      {usePdf && s.file_url && s.page_no ? <PdfPage url={s.file_url} page={s.page_no} quote={s.quote} onFail={fail} /> : null}
      {useImage ? (
        <div className="flex flex-col gap-3 min-[640px]:flex-row">
          <div className="flex flex-col gap-2 min-[640px]:w-1/2">
            {images.map((src) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={src} src={src} alt={s.page_no ? `Trang ${s.page_no} của tài liệu gốc` : "Ảnh vở ghi"} className="max-w-full" onError={() => setImageFailed(true)} />
            ))}
          </div>
          <p className="m-0 whitespace-pre-wrap text-body text-ink-soft">
            <mark className="rounded-sm bg-hl px-0.5 text-ink">{s.quote}</mark>
          </p>
        </div>
      ) : null}
      {!usePdf && !useImage ? <p className="m-0 whitespace-pre-wrap text-body text-ink-soft">{excerpt}</p> : null}
    </li>
  );
}

function SourcePanel({ cardId }: { cardId: string }) {
  const [rows, setRows] = useState<Source[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  if (rows === null && !loading && !failed) {
    setLoading(true);
    fetch(`/api/vault/cards/${cardId}/sources`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("source"))))
      .then((data: Source[]) => setRows(data))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }
  if (failed) return <p className="m-0 text-body text-ink-soft">Không mở được nguồn. Thử lại sau.</p>;
  if (rows === null) return <p className="m-0 text-body text-ink-soft">Đang mở nguồn…</p>;
  if (rows.length === 0) return <p className="m-0 text-body text-ink-soft">Thẻ này chưa có nguồn.</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {rows.map((s) => (
        <SourceItem key={s.anchor_id} s={s} />
      ))}
    </ul>
  );
}

function Card({ card, onGone }: { card: VaultCard; onGone: (id: string) => void }) {
  const [saved, setSaved] = useState({ title: card.title, content: card.content });
  const [draft, setDraft] = useState<{ title: string; content: string } | null>(null);
  const [showSource, setShowSource] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  // Q14 (QA 05/11): deleting asks first, in the page.
  const [confirming, setConfirming] = useState(false);

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError("");
    setExpired(false);
    const r = await fetch(`/api/vault/cards/${card.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(draft),
    }).catch(() => null);
    setBusy(false);
    if (r?.status === 401) return setExpired(true); // E-01: keep the form, offer a sign-in link
    if (!r?.ok) return setError("Chưa lưu được. Thử lại.");
    setSaved(draft);
    setDraft(null);
  }

  async function remove() {
    setBusy(true);
    setExpired(false);
    const r = await fetch(`/api/vault/cards/${card.id}`, { method: "DELETE" }).catch(() => null);
    setBusy(false);
    if (r?.status === 401) return setExpired(true);
    if (!r?.ok) return setError("Chưa xóa được. Thử lại.");
    onGone(card.id);
  }

  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-tile bg-sheet p-6 text-ink" data-slot="vault-card">
      {draft ? (
        <>
          <input
            aria-label="Tiêu đề thẻ"
            className="h-11 rounded-control bg-bg px-3 text-body font-semibold inset-ring-[1.5px] inset-ring-line-strong"
            value={draft.title}
            maxLength={200}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
          <textarea
            aria-label="Nội dung thẻ"
            aria-describedby={`md-hint-${card.id}`}
            className="min-h-32 rounded-control bg-bg p-3 text-body inset-ring-[1.5px] inset-ring-line-strong"
            value={draft.content}
            maxLength={4000}
            onChange={(e) => setDraft({ ...draft, content: e.target.value })}
          />
          <p id={`md-hint-${card.id}`} className="m-0 text-meta text-ink-soft">
            Viết được Markdown. Công thức đặt trong $...$ (cùng dòng) hoặc $$...$$ (khối), ví dụ $n_1 n_2$.
          </p>
          {draft.content.trim() ? (
            <section aria-label="Xem trước nội dung" className="flex flex-col gap-1 rounded-control bg-sunken p-3">
              <span className="text-meta text-ink-soft">Xem trước</span>
              <Markdown className="text-body" text={draft.content} />
            </section>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              size="md"
             
              disabled={busy || !draft.title.trim() || !draft.content.trim()}
              onClick={save}
            >
              Lưu
            </Button>
            <Button variant="quiet" onClick={() => setDraft(null)} disabled={busy}>
              Hủy
            </Button>
            <Button variant="quiet" onClick={() => setConfirming(true)} disabled={busy || confirming}>
              Xóa thẻ
            </Button>
          </div>
          {confirming ? (
            <div role="group" aria-label="Xác nhận xóa thẻ" className="flex flex-col gap-3 rounded-tile bg-sunken p-4">
              <p className="m-0 text-body">Xóa thẻ này? Thẻ sẽ không còn trong Kho và không được ôn nữa.</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" onClick={remove} pending={busy}>
                  Xóa hẳn thẻ
                </Button>
                <Button variant="quiet" onClick={() => setConfirming(false)} disabled={busy}>
                  Giữ thẻ
                </Button>
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <>
          <h3 className="m-0 text-lead font-semibold">{saved.title}</h3>
          <Markdown className="text-body" text={saved.content} />
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="md" onClick={() => setDraft(saved)}>
              Sửa thẻ
            </Button>
            <Button variant="quiet" aria-expanded={showSource} onClick={() => setShowSource((v) => !v)}>
              Nguồn
            </Button>
          </div>
        </>
      )}
      {error ? (
        <p role="alert" className="m-0 text-body text-ink-soft">
          {error}
        </p>
      ) : null}
      {expired ? (
        <p role="alert" className="m-0 text-body text-ink-soft">
          Phiên đăng nhập đã hết hạn.{" "}
          <Link href="/login" className={buttonVariants({ variant: "quiet" })}>
            Đăng nhập lại
          </Link>
        </p>
      ) : null}
      {showSource && !draft ? <SourcePanel cardId={card.id} /> : null}
    </article>
  );
}

// V4-SCREENS-B: a white sheet per card on one plum stage, side by side in a horizontal band (ui/carousel).
// The two round buttons are re-coloured for the plum ground (--on-plum-action, never --hong on plum).
const STAGE_BUTTONS =
  "[&_[data-slot=carousel-track]>div]:w-[min(380px,calc(100vw-96px))] [&_[data-slot=carousel-meta]]:text-on-plum [&_button[aria-label^=Th]]:bg-on-plum-action [&_button[aria-label^=Th]]:text-on-plum-action-fg [&_button[aria-label^=Th]]:inset-ring-0 [&_button[aria-label^=Th]:hover]:bg-on-plum-action [&_button[aria-label^=Th]:disabled]:bg-on-plum/15 [&_button[aria-label^=Th]:disabled]:text-on-plum-soft";

export function CardList({ cards, subjectName }: { cards: VaultCard[]; subjectName?: string }) {
  const [gone, setGone] = useState<string[]>([]);
  const shown = cards.filter((c) => !gone.includes(c.id));
  // E-12: the count lives here so deleting a card updates it (and the carousel's "1 / n") at once.
  const subtitle = [subjectName, shown.length > 0 ? `${shown.length} thẻ` : null].filter(Boolean).join(" · ");
  const subline = subtitle ? <p className="m-0 -mt-3 text-read text-ink-soft">{subtitle}</p> : null;
  if (shown.length === 0) {
    return (
      <>
      {subline}
      <Block as="section" tier="sheet" aria-label="Chưa có thẻ">
        <Doodle name="sach-mo" size={48} className="mb-2 text-hong-text" />
        <p className="m-0 text-lead">Buổi này chưa có thẻ nào.</p>
      </Block>
      </>
    );
  }
  return (
    <>
    {subline}
    <Block tier="field" className="p-4 min-[901px]:p-6" data-vault-stage>
      <Carousel label="Thẻ của buổi học" className={STAGE_BUTTONS}>
        {shown.map((c) => (
          <Card key={c.id} card={c} onGone={(id) => setGone((g) => [...g, id])} />
        ))}
      </Carousel>
    </Block>
    </>
  );
}
