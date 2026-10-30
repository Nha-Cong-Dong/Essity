"use client";

import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import {
  cellLabel,
  dayLabel,
  type GridCell,
  levelLegend,
  monthLabels,
  sectionsText,
} from "@/lib/stats";

import styles from "./stats.module.css";

// T9.5a (US-10 AC4-AC6; DESIGN §6.13, .work/T9.5a/design-decisions.md): the activity grid. Columns
// are weeks, rows are weekdays. One tab stop; arrow keys move by day (up/down) and week
// (left/right). Hovering or focusing shows a day; a tap, Enter or Space pins it and the status
// line says it once. The panel under the grid replaces a popover: it cannot be clipped by the
// scrolling box or hidden under a finger. An empty day is a plain fact, never a lack.

const ROW_LABELS = ["T2", "", "T4", "", "T6", "", ""];
const MIN_LABEL_GAP = 3; // columns between two month labels

export type GridSubject = { id: string; name: string };

export function ActivityGrid({
  cells,
  today,
  subjects,
  examBy,
}: {
  cells: GridCell[];
  today: string;
  subjects: GridSubject[];
  /** Exam day -> names of the subjects whose exam it is. */
  examBy: Record<string, string[]>;
}) {
  const names = useMemo(() => new Map(subjects.map((s) => [s.id, s.name])), [subjects]);
  const start = Math.max(
    cells.findIndex((c) => c.day === today),
    0,
  );
  const [focused, setFocused] = useState(start);
  const [pinned, setPinned] = useState(start);
  const [hover, setHover] = useState<number | null>(null);
  const [onCell, setOnCell] = useState(false);
  const [announce, setAnnounce] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const refs = useRef<Map<number, HTMLButtonElement>>(new Map());

  const columns = cells.length === 0 ? 0 : cells[cells.length - 1].column + 1;
  const byPos = useMemo(() => {
    const map = new Map<string, number>();
    cells.forEach((c, i) => map.set(`${c.row}:${c.column}`, i));
    return map;
  }, [cells]);

  const labels = useMemo(() => {
    const kept: { column: number; text: string }[] = [];
    for (const m of monthLabels(cells)) {
      if (kept.length > 0 && m.column - kept[kept.length - 1].column < MIN_LABEL_GAP) continue;
      const first = cells.find((c) => c.column === m.column);
      // A year only where January starts a later year; the first label would run under the weekday column.
      const year = m.label === "Th1" && first && kept.length > 0 ? ` ${first.day.slice(0, 4)}` : "";
      kept.push({ column: m.column, text: m.label + year });
    }
    return new Map(kept.map((k) => [k.column, k.text]));
  }, [cells]);

  function reveal(i: number) {
    const box = scroller.current;
    const el = refs.current.get(i);
    if (!box || !el) return;
    const left = el.offsetLeft;
    const pad = 48;
    if (left < box.scrollLeft + pad) box.scrollLeft = Math.max(left - pad, 0);
    else if (left + el.offsetWidth > box.scrollLeft + box.clientWidth - pad) {
      box.scrollLeft = left + el.offsetWidth - box.clientWidth + pad;
    }
  }

  // Open on today, near the middle, so the wide grid does not start at its oldest week.
  useEffect(() => {
    const box = scroller.current;
    const el = refs.current.get(start);
    if (box && el) box.scrollLeft = Math.max(el.offsetLeft - box.clientWidth / 2, 0);
  }, [start]);

  function pin(i: number) {
    setPinned(i);
    setAnnounce(cellLabel(cells[i], today));
  }

  function onKey(event: KeyboardEvent, i: number) {
    const step: Record<string, number> = { ArrowUp: -1, ArrowDown: 1, ArrowLeft: -7, ArrowRight: 7 };
    if (event.key in step) {
      event.preventDefault();
      const next = Math.min(Math.max(i + step[event.key], 0), cells.length - 1);
      setFocused(next);
      refs.current.get(next)?.focus();
      reveal(next);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      pin(i);
    }
  }

  function move(delta: number) {
    const next = Math.min(Math.max(pinned + delta, 0), cells.length - 1);
    setFocused(next);
    pin(next);
    reveal(next);
  }

  if (cells.length === 0) return null;
  const cell = cells[hover ?? (onCell ? focused : pinned)];
  const worked = cell.cardsSaved + cell.questionsAnswered > 0;
  const subjectText = cell.subjects
    .map((id) => names.get(id) ?? "")
    .filter(Boolean)
    .join(", ");
  const workedDays = cells.filter((c) => c.cardsSaved + c.questionsAnswered > 0).reverse();
  const hasExam = cells.some((c) => c.examDay);
  const range = `${dayLabel(cells[0].day)} tới ${dayLabel(cells[cells.length - 1].day)}`;

  return (
    <div data-activity-grid className={styles.root}>
      <div ref={scroller} className={styles.scroll}>
        <div className={styles.grid} role="grid" aria-label={`Hoạt động theo ngày, ${range}`}>
          <div className={styles.row} aria-hidden="true">
            <span className={styles.corner} />
            <div className={styles.months}>
              {Array.from({ length: columns }, (_, col) => (
                <span key={col} className={styles.month}>
                  {labels.get(col) ?? ""}
                </span>
              ))}
            </div>
          </div>
          {ROW_LABELS.map((label, row) => (
            <div key={row} role="row" className={styles.row}>
              <span aria-hidden="true" className={styles.weekday}>
                {label}
              </span>
              {Array.from({ length: columns }, (_, col) => {
                const i = byPos.get(`${row}:${col}`);
                if (i === undefined) return <span key={col} aria-hidden="true" className={styles.slot} />;
                const c = cells[i];
                return (
                  <span key={col} role="gridcell" className="flex">
                    <button
                      type="button"
                      ref={(el) => {
                        if (el) refs.current.set(i, el);
                        else refs.current.delete(i);
                      }}
                      className={styles.cell}
                      tabIndex={i === focused ? 0 : -1}
                      aria-label={cellLabel(c, today)}
                      data-day={c.day}
                      data-level={c.level}
                      data-future={c.future}
                      data-today={c.day === today}
                      data-exam={c.examDay}
                      data-pinned={i === pinned}
                      onClick={() => {
                        setFocused(i);
                        pin(i);
                      }}
                      onFocus={() => {
                        setFocused(i);
                        setOnCell(true);
                      }}
                      onBlur={() => setOnCell(false)}
                      onKeyDown={(e) => onKey(e, i)}
                      onMouseEnter={() => setHover(i)}
                      onMouseLeave={() => setHover(null)}
                    />
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <p className="sr-only">Dùng phím mũi tên để đổi ngày; Enter để xem chi tiết.</p>
      <p role="status" className="sr-only">
        {announce}
      </p>

      <div className="mt-4 flex flex-col gap-2 text-meta text-ink-soft" data-legend>
        <div className={styles.legend}>
          <span>Ít</span>
          {[0, 1, 2, 3, 4].map((level) => (
            <span key={level} aria-hidden="true" className={styles.swatch} data-level={level} />
          ))}
          <span>Nhiều</span>
          <span>· {levelLegend()}</span>
        </div>
        <div className={styles.legend}>
          <span aria-hidden="true" className={styles.swatch} data-today="true" />
          <span>viền đậm: hôm nay</span>
          {hasExam && (
            <>
              <span aria-hidden="true" className={styles.swatch} data-exam="true" />
              <span>ngày thi</span>
            </>
          )}
        </div>
      </div>

      <Sheet variant="sunken" className="mt-4 min-h-36" data-day-detail>
        <p className="m-0 text-read font-semibold">
          {dayLabel(cell.day)}
          {cell.day === today ? " · hôm nay" : ""}
        </p>
        {cell.examDay && (
          <p className="m-0 mt-1 wrap-anywhere">
            Ngày thi: <span data-user>{(examBy[cell.day] ?? []).join(", ")}</span>
          </p>
        )}
        {cell.future ? (
          <p className="m-0 mt-1 text-ink-soft">
            Chưa tới ngày này.
          </p>
        ) : worked ? (
          <>
            <p className="m-0 mt-1">
              {cell.cardsSaved} thẻ đã lưu · {cell.questionsAnswered} câu đã làm
            </p>
            {subjectText && (
              <p className="m-0 mt-1 text-meta wrap-anywhere">
                Môn: <span data-user>{subjectText}</span>
              </p>
            )}
            {cell.sections.length > 0 && (
              <p className="m-0 text-meta wrap-anywhere">
                Mục: <span data-user>{sectionsText(cell.sections)}</span>
              </p>
            )}
          </>
        ) : (
          <p className="m-0 mt-1 text-ink-soft">
            {cell.day === today ? "Hôm nay chưa có thẻ hay câu nào được ghi." : "Không có ghi nhận ngày này."}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-1">
          <Button variant="quiet" type="button" onClick={() => move(-1)} disabled={pinned === 0}>
            Ngày trước
          </Button>
          <Button variant="quiet" type="button" onClick={() => move(1)} disabled={pinned === cells.length - 1}>
            Ngày sau
          </Button>
        </div>
      </Sheet>

      <details className="mt-4">
        <summary className="flex min-h-11 cursor-pointer items-center text-body font-medium underline decoration-line-strong decoration-[1.5px] underline-offset-[5px]">
          Xem dạng danh sách
        </summary>
        <div role="region" tabIndex={0} aria-labelledby="alt-caption" className={styles.alt} data-alt-list>
          <table className="w-full [border-collapse:collapse] text-meta">
            <caption id="alt-caption" className="py-2 text-left font-semibold">
              Lượng việc theo ngày (chỉ những ngày có ghi nhận)
            </caption>
            <thead>
              <tr>
                <th scope="col" className="py-1 pr-4 text-left font-semibold">
                  Ngày
                </th>
                <th scope="col" className="py-1 pr-4 text-left font-semibold">
                  Thẻ đã lưu
                </th>
                <th scope="col" className="py-1 text-left font-semibold">
                  Câu đã làm
                </th>
              </tr>
            </thead>
            <tbody>
              {workedDays.length === 0 ? (
                <tr>
                  <td colSpan={3} className="py-2 text-ink-soft">
                    Chưa có ngày nào được ghi.
                  </td>
                </tr>
              ) : (
                workedDays.map((c) => (
                  <tr key={c.day} className="border-t border-line">
                    <th scope="row" className="py-1 pr-4 text-left font-normal">
                      {dayLabel(c.day)}
                    </th>
                    <td className="py-1 pr-4 tabular-nums">{c.cardsSaved}</td>
                    <td className="py-1 tabular-nums">{c.questionsAnswered}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
