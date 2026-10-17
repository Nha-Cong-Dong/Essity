import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import styles from "./notebook.module.css";

// The shared notebook objects of docs/DESIGN.md §3 and §7 (canvas Today artboard).
// NotebookPage (trang vở) comes with the review screens.

/** Vệt bút dạ quang: an orange highlighter stroke under a title. */
export function Marker({ children }: { children: ReactNode }) {
  return <span className={styles.marker}>{children}</span>;
}

/** Lời chấm bút chì: short handwritten note in pencil grey ("còn thiếu", "hiểu được vì sao"). */
export function PencilNote({ children }: { children: ReactNode }) {
  return <span className={styles.pencil}>{children}</span>;
}

/**
 * Bìa vở: a pink notebook cover with an orange stapled spine, two stripes, squared texture,
 * corner protectors and a sheet of paper behind. Tilt it 1° on Hôm nay and Tạo môn; keep it
 * straight on account screens, which have inputs (DESIGN.md §3, §6.1).
 */
export function NotebookCover({
  title,
  aside,
  tilt = false,
  children,
}: {
  /** The screen title; drawn with a highlighter stroke. */
  title: ReactNode;
  /** Right of the title, e.g. the date in handwriting. */
  aside?: ReactNode;
  tilt?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={cn(styles.cover, tilt && styles.tilted)}>
      <div className={styles.under} aria-hidden="true" />
      <div className={styles.board}>
        <div className={styles.spine} aria-hidden="true" />
        <div className={styles.titleRow}>
          <h1 className={styles.title}>
            <Marker>{title}</Marker>
          </h1>
          {aside}
        </div>
        <div className={styles.stripes} aria-hidden="true">
          <i />
          <i />
        </div>
        {children}
      </div>
    </div>
  );
}

/** Nhãn vở: the label stuck on the cover, with a dashed frame and a strip of tape. */
export function NhanVo({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn(styles.label, className)}>{children}</div>;
}

/** One line of a label: printed key, handwritten pink value on a dotted line. */
export function NhanVoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.row}>
      <span className={styles.rowKey}>{label}</span>
      <span className={styles.rowValue}>{children}</span>
    </div>
  );
}
