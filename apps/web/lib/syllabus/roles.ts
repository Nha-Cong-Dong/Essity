// T7.5a (US-01 AC4, AC7; DESIGN §6.4, design-decisions.md R2.5): document roles in the upload
// form. One main syllabus per subject; the rules below are provisional (câu tạm) until T7.4/T7.5.

export type Role = "main" | "bank" | "supplementary";
export type FileKind = "pdf" | "docx" | "pptx" | "image";
export type FileState = "uploading" | "reading" | "reading-toc" | "ready" | "partial" | "failed";

export type UploadFile = {
  id: string;
  name: string;
  kind: FileKind;
  role: Role;
  state: FileState;
  /** 0-100 while uploading. */
  progress?: number;
  unreadable?: number[];
  /** The main syllabus has been read (its outline exists): swapping it is a real change. */
  tocRead?: boolean;
  /** The role was picked by the learner, not by the default rule. */
  chosen?: boolean;
};

export const ROLE_LABEL: Record<Role, string> = {
  main: "Giáo trình chính",
  bank: "Bộ câu hỏi",
  supplementary: "Tài liệu phụ",
};

export const ROLE_HINT: Record<Role, string> = {
  main: "App dựng đề cương từ file này.",
  bank: "App tách câu hỏi và gợi ý dạng câu.",
  supplementary: "Dùng để tìm nguồn và gõ @.",
};

export const IMAGE_NOT_MAIN = "Ảnh chưa dựng được đề cương.";

/** Provisional rule: the first document is the main one if the subject and the batch have none. */
export function defaultRole(
  file: Pick<UploadFile, "kind">,
  ctx: { subjectHasMain: boolean; batch: UploadFile[] },
): Role {
  if (file.kind === "image" || ctx.subjectHasMain) return "supplementary";
  return ctx.batch.some((f) => f.role === "main") ? "supplementary" : "main";
}

/** Makes `id` the main file; the old main falls back to supplementary. */
export const switchMain = (files: UploadFile[], id: string): UploadFile[] =>
  files.map((f) => (f.id === id ? { ...f, role: "main", chosen: true } : f.role === "main" ? { ...f, role: "supplementary" } : f));

/**
 * Asking is only needed when the old main is really established: chosen by the learner, from an
 * earlier upload, or already read. A main that is just the batch default swaps without a question.
 */
export const needsConfirm = (main: UploadFile | undefined, fromEarlier: boolean): boolean =>
  main !== undefined && (fromEarlier || main.chosen === true || main.tocRead === true);
