import { PageFold } from "@/components/motifs";
import { Marker } from "@/components/notebook";
import { AUTH_LINK } from "@/components/auth/fields";
import { Uploader } from "@/components/subjects/uploader";
import { Sheet } from "@/components/ui/sheet";

// T1.20, US-01 AC7 (plan K5): right after "Tạo môn", the upload step; T4.6 made it real. No "Vào môn
// học" yet: the subject page is T4.9.
export function UploadStep({ name, subjectId }: { name: string; subjectId: string }) {
  return (
    <Sheet className="relative w-full max-w-220" aria-labelledby="upload-title">
      <PageFold />
      <h1 id="upload-title" className="m-0 flex flex-wrap items-center gap-3 font-display text-title">
        <Marker>Tải tài liệu cho {name}</Marker>
      </h1>
      <p className="mt-3 mb-0 max-w-[56ch] text-read text-ink-soft">
        Giáo trình, slide hoặc ảnh vở. Câu hỏi sẽ dựa trên đúng những trang này.
      </p>
      <Uploader subjectId={subjectId} />
      <p className="mt-6 mb-0">
        <a href="/subjects" className={AUTH_LINK}>
          Làm sau
        </a>
      </p>
    </Sheet>
  );
}
