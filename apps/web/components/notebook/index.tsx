import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import styles from "./notebook.module.css";

// The shared notebook objects of docs/DESIGN.md §3 and §7 (canvas Today artboard).
// NotebookPage (trang vở) comes with the review screens.

/** Vệt bút dạ quang: a pink highlighter stroke under a title. */
export function Marker({ children }: { children: ReactNode }) {
  return <span className={styles.marker}>{children}</span>;
}

/** Lời chấm bút chì: short italic note in pencil grey ("còn thiếu", "hiểu được vì sao"). */
export function PencilNote({ children }: { children: ReactNode }) {
  return <span className={styles.pencil}>{children}</span>;
}

/**
 * Bìa vở at level b (design system v3.1 §4.4): a rose cover with three details only, the deep
 * pink spine, one stripe and the highlighter under the title. Always straight.
 */
export function NotebookCover({
  title,
  aside,
  children,
}: {
  /** The screen title; drawn with a highlighter stroke. */
  title: ReactNode;
  /** Right of the title, e.g. the date in handwriting. */
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={styles.cover}>
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
        </div>
        {children}
      </div>
    </div>
  );
}

/** Nhãn vở: a sheet on the cover (§4.5), no dashed frame and no tape. */
export function NhanVo({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn(styles.label, className)}>{children}</div>;
}

/** One line of a label: the key in soft ink, the value in upright ink; a hairline between rows. */
export function NhanVoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.row}>
      <span className={styles.rowKey}>{label}</span>
      <span className={styles.rowValue}>{children}</span>
    </div>
  );
}
