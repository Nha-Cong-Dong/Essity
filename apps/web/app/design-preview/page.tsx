import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { FieldError, FieldHint } from "@/components/field-error";
import { GridCorner, PageFold, Sticker } from "@/components/motifs";
import { Marker, NhanVo, NhanVoRow, NotebookCover, PencilNote } from "@/components/notebook";
import { ServiceChain } from "@/components/service-chain";
import { AppShell } from "@/components/shells";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet } from "@/components/ui/sheet";
import { designPreviewAllowed } from "@/lib/design-preview";

export const metadata: Metadata = { title: "Design preview · Essity" };

// Every token, base control, notebook object and motif of design system v3.1
// (docs/plans/design-architecture-final.md) on one page. Closed outside development unless
// WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).

const SURFACES = [
  ["bg", "bg-bg text-ink"],
  ["sheet", "bg-sheet text-ink shadow-sheet"],
  ["raised", "bg-raised text-ink shadow-over"],
  ["sunken", "bg-sunken text-ink"],
  ["cover", "bg-book-cover text-ink"],
  ["hong", "bg-hong text-on-hong"],
] as const;

const ROSE = [
  ["rose-50", "bg-rose-50"],
  ["rose-100", "bg-rose-100"],
  ["rose-200", "bg-rose-200"],
  ["rose-300", "bg-rose-300"],
  ["hong", "bg-hong"],
  ["rose-700", "bg-rose-700"],
] as const;

const INKS = [
  ["ink", "text-ink"],
  ["ink-soft", "text-ink-soft"],
  ["hong", "text-hong"],
  ["correct", "text-correct"],
  ["partial", "text-partial"],
  ["pencil", "text-pencil"],
] as const;

const TYPE = [
  ["display · 48–64/650", "font-display text-display", "Hôm nay"],
  ["title · 36–48/650", "font-display text-title", "Xong phiên hôm nay"],
  ["verdict · 28–36/650", "font-display text-verdict", "Đúng một phần"],
  ["question · 22–28/500", "font-display text-question", "Vì sao có ngày và đêm?"],
  ["lead · 22/600", "font-display text-lead", "Đáp án tham chiếu"],
  ["answer · 18/32px, hồng đứng", "text-answer text-hong", "Vì Trái Đất tự quay quanh trục."],
  ["read · 18/1.7", "text-read", "Mặt Trời chỉ chiếu sáng được một nửa Trái Đất tại mỗi thời điểm."],
  ["pencil · 18 nghiêng, chì", "font-hand text-read text-pencil", "còn thiếu · hiểu được vì sao"],
  ["body · 16/1.6", "text-body", "Vở ghi khác giáo trình ở điểm này."],
  ["meta · 14/1.5", "text-meta text-ink-soft", "Giáo trình Địa lý đại cương · tr. 24"],
] as const;

/** A second lock behind proxy.ts: core-api is never called unless the preview is allowed. */
async function GuardedServiceChain() {
  await connection(); // read the environment at request time, not at build time
  if (!designPreviewAllowed(process.env)) notFound();
  return <ServiceChain />;
}

export default function DesignPreviewPage() {
  return (
    <AppShell current="/today" account={<AccountMenu email="ban@example.com" />}>
      <div className="flex flex-col gap-16">
        <header className="flex flex-col gap-4">
          <h1 className="text-title">Design preview</h1>
          <p className="m-0 text-ink-soft">
            Chế độ hiển thị trong menu tài khoản đổi cả trang. Hệ thiết kế v3.1.
          </p>
          <Suspense fallback={<p className="font-mono text-meta text-ink-soft">web → …</p>}>
            <GuardedServiceChain />
          </Suspense>
        </header>

        <section className="flex flex-col gap-4">
          <h2 className="text-lead">Bề mặt và mực</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {SURFACES.map(([name, classes]) => (
              <div key={name} className={`${classes} rounded-control p-4 text-meta`}>
                <div className="font-semibold">{name}</div>
                <div>Câu hỏi hôm nay</div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {ROSE.map(([name, classes]) => (
              <div key={name} className="flex flex-col items-center gap-1.5 text-meta text-ink-soft">
                <span className={`${classes} block size-14 rounded-full`} />
                {name}
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-6 text-body font-semibold">
            {INKS.map(([name, classes]) => (
              <span key={name} className={classes}>
                {name}
              </span>
            ))}
            <span className="bg-hl px-1 text-ink">hl: câu nguồn được tô</span>
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-lead">Chữ</h2>
          {TYPE.map(([meta, classes, sample]) => (
            <div
              key={meta}
              className="grid grid-cols-1 items-baseline gap-2 border-b border-line py-5 sm:grid-cols-[200px_minmax(0,1fr)] sm:gap-6"
            >
              <span className="text-meta text-ink-soft">{meta}</span>
              <span className={classes}>{sample}</span>
            </div>
          ))}
          <p className="font-display text-title">Ữ Ặ Ẫ Ỡ Ể Ộ</p>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-lead">Nút</h2>
          <div className="flex flex-wrap items-center gap-3">
            <Button>Bắt đầu</Button>
            <Button variant="secondary">Ôn thêm</Button>
            <Button variant="quiet">Không nhớ</Button>
            <Button pending>Đang gửi</Button>
            <Button disabled>Gửi</Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge>Nhận biết</Badge>
            <Badge>Vận dụng</Badge>
            <Badge>Vận dụng cao</Badge>
          </div>
        </section>

        <section className="flex max-w-[440px] flex-col gap-4">
          <h2 className="text-lead">Ô nhập</h2>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="preview-email">Email</Label>
            <Input id="preview-email" type="email" placeholder="ban@example.com" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="preview-gpa">GPA hiện tại</Label>
            <Input id="preview-gpa" aria-invalid aria-describedby="preview-gpa-error" defaultValue="4,5" />
            <FieldError id="preview-gpa-error">GPA thang 4 nằm trong khoảng 0 đến 4.</FieldError>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="preview-disabled">Không sửa được</Label>
            <Input id="preview-disabled" disabled defaultValue="2.85" aria-describedby="preview-disabled-hint" />
            <FieldHint id="preview-disabled-hint">Sau 7 ngày, mốc này sẽ không sửa được nữa.</FieldHint>
          </div>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-lead">Trang vở và ô</h2>
          <div className="grid gap-5 md:grid-cols-2">
            <Sheet className="relative">
              <PageFold />
              <p className="m-0 font-display text-question">Vì sao có ngày và đêm?</p>
              <p className="mt-4 mb-0 text-read">
                <Marker>Trái Đất tự quay quanh trục</Marker>, nên mỗi nơi lần lượt được Mặt Trời chiếu sáng.
              </p>
            </Sheet>
            <Sheet variant="sunken">
              <p className="m-0 text-meta font-semibold">Vì sao câu này?</p>
              <p className="mt-2 mb-0 text-body text-ink-soft">Lần trước bạn trả lời thiếu ý này.</p>
            </Sheet>
            <Sheet variant="tile" tone="hong" className="flex flex-col gap-4">
              <span className="text-meta text-hong-soft-text">Phiên ôn tối nay</span>
              <span className="font-display text-mega">14</span>
              <Button variant="primary-inverse" className="self-start">
                Bắt đầu
              </Button>
            </Sheet>
            <Sheet variant="tile" tone="rose" className="flex flex-col gap-4">
              <span className="font-display text-lead">Sau buổi học</span>
              <Button variant="secondary" className="self-start">
                Ghi buổi học
              </Button>
            </Sheet>
          </div>
        </section>

        <section className="relative flex flex-col gap-8 overflow-x-clip">
          <h2 className="text-lead">Đồ vật và họa tiết</h2>
          <GridCorner corner="tr" />
          <div className="relative flex justify-center px-2 pt-8 pb-12 sm:px-6">
            <div className="relative w-full max-w-[520px]">
              <Sticker icon="moon" className="-top-6 -right-3 sm:-right-6" />
              <NotebookCover title="Hôm nay" aside={<span className="font-hand text-read text-pencil">thứ Sáu, 16/10</span>}>
                <NhanVo>
                  <NhanVoRow label="Số câu">14 câu</NhanVoRow>
                  <NhanVoRow label="Thời gian">khoảng 25 phút</NhanVoRow>
                  <NhanVoRow label="Môn">Vật lý đại cương, Địa lý tự nhiên</NhanVoRow>
                </NhanVo>
                <Button size="lg" className="w-full">
                  Bắt đầu
                </Button>
              </NotebookCover>
            </div>
          </div>
          <PencilNote>còn thiếu · hiểu được vì sao</PencilNote>
        </section>
      </div>
    </AppShell>
  );
}
