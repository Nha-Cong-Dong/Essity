import { FileUp } from "lucide-react";

import { PageFold } from "@/components/motifs";
import { Marker } from "@/components/notebook";
import { AUTH_LINK } from "@/components/auth/fields";
import { Sheet } from "@/components/ui/sheet";

// T1.20, US-01 AC7 (plan K5): right after "Tạo môn", the upload step, shown as coming soon. Uploads
// arrive with T4.6; until then there is no file input, only "Làm sau" back to the list. No
// "Vào môn học" yet: the subject page is T4.9.
export function UploadStep({ name }: { name: string }) {
  return (
    <Sheet className="relative w-full max-w-220" aria-labelledby="upload-title">
      <PageFold />
      <h1 id="upload-title" className="m-0 flex flex-wrap items-center gap-3 font-display text-title">
        <Marker>Tải tài liệu cho {name}</Marker>
        <span className="rounded-full bg-sunken px-3 py-1 font-sans text-small font-semibold text-ink-soft">
          Sắp có
        </span>
      </h1>
      <p className="mt-3 mb-0 max-w-[56ch] text-read text-ink-soft">
        Giáo trình, slide hoặc ảnh vở. Câu hỏi sẽ dựa trên đúng những trang này.
      </p>
      <div
        aria-disabled="true"
        className="mt-6 flex flex-col items-center gap-2 rounded-sheet border-2 border-dashed border-line-strong bg-sunken px-6 py-10 text-center text-ink-soft"
      >
        <FileUp className="size-6" aria-hidden="true" />
        <b className="text-body text-ink" data-copy="tam">
          Thả file vào đây hoặc bấm để chọn
        </b>
        <span className="text-small" data-copy="tam">
          Tải tài liệu sẽ có ở bản sau.
        </span>
      </div>
      <p className="mt-6 mb-0">
        <a href="/subjects" className={AUTH_LINK}>
          Làm sau
        </a>
      </p>
    </Sheet>
  );
}
