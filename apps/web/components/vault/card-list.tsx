"use client";

import { useCallback, useState } from "react";

import { PdfPage } from "@/components/vault/pdf-page";

import { Button } from "@/components/ui/button";
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
      <mark className="rounded-sm bg-hong/25 px-0.5 text-ink">{text.slice(range[0], range[1])}</mark>
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
      <mark className="rounded-sm bg-hong/25 px-0.5 text-ink">{s.quote}</mark>
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
            <mark className="rounded-sm bg-hong/25 px-0.5 text-ink">{s.quote}</mark>
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

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError("");
    const r = await fetch(`/api/vault/cards/${card.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(draft),
    }).catch(() => null);
    setBusy(false);
    if (!r?.ok) return setError("Chưa lưu được. Thử lại.");
    setSaved(draft);
    setDraft(null);
  }

  async function remove() {
    setBusy(true);
    const r = await fetch(`/api/vault/cards/${card.id}`, { method: "DELETE" }).catch(() => null);
    setBusy(false);
    if (!r?.ok) return setError("Chưa xóa được. Thử lại.");
    onGone(card.id);
  }

  return (
    <li className="flex flex-col gap-3 rounded-sheet bg-sheet p-5 shadow-sheet" data-slot="vault-card">
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
            className="min-h-32 rounded-control bg-bg p-3 text-body inset-ring-[1.5px] inset-ring-line-strong"
            value={draft.content}
            maxLength={4000}
            onChange={(e) => setDraft({ ...draft, content: e.target.value })}
          />
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
            <Button variant="quiet" onClick={remove} disabled={busy}>
              Xóa thẻ
            </Button>
          </div>
        </>
      ) : (
        <>
          <h3 className="m-0 text-lead font-semibold">{saved.title}</h3>
          <p className="m-0 whitespace-pre-wrap text-body">{saved.content}</p>
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
      {showSource && !draft ? <SourcePanel cardId={card.id} /> : null}
    </li>
  );
}

export function CardList({ cards }: { cards: VaultCard[] }) {
  const [gone, setGone] = useState<string[]>([]);
  const shown = cards.filter((c) => !gone.includes(c.id));
  if (shown.length === 0) return <p className="m-0 text-lead">Buổi này chưa có thẻ nào.</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-4 p-0">
      {shown.map((c) => (
        <Card key={c.id} card={c} onGone={(id) => setGone((g) => [...g, id])} />
      ))}
    </ul>
  );
}
