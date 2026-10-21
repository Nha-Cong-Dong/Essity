import type { Metadata } from "next";
import { Suspense } from "react";

import { FieldError, FieldHint } from "@/components/field-error";
import { NhanVo, NhanVoRow, NotebookCover, PencilNote } from "@/components/notebook";
import { ServiceChain } from "@/components/service-chain";
import { AppShell } from "@/components/shells";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { ThemeSwitch } from "./theme-switch";

export const metadata: Metadata = { title: "Design preview · Essity" };

// Every token, base control and notebook object of docs/DESIGN.md §3 and §7 on one page (T1.1).
// NotebookPage (trang vở) is added with the review screens.

const SURFACES = [
  ["paper", "bg-paper text-ink"],
  ["sheet", "bg-sheet text-ink"],
  ["subtle", "bg-subtle text-ink"],
  ["cover", "bg-cover text-ink"],
  ["hong", "bg-hong text-on-hong"],
] as const;

const INKS = [
  ["ink", "text-ink"],
  ["ink-soft", "text-ink-soft"],
  ["hong", "text-hong"],
  ["cam", "text-cam"],
  ["right", "text-right"],
  ["partial", "text-partial"],
  ["miss", "text-miss"],
] as const;

const TYPE = [
  ["title · Bricolage 52/650", "font-display text-title", "Xong phiên hôm nay"],
  ["display · Bricolage 64/600", "font-display text-display", "14"],
  ["verdict · 40/650", "font-display text-verdict", "Đúng một phần"],
  ["question · Bricolage 26/500", "font-display text-question", "Gói SYN-ACK bị mất. Client và server sẽ làm gì tiếp theo?"],
  ["section · 22/600", "font-display text-section", "Đáp án tham chiếu"],
  ["answer · 18/32px, hồng", "text-answer text-hong", "Client hết timeout và gửi lại SYN."],
  ["source · 18/1.75", "text-source", "Khi rwnd = 0, bên gửi bật persist timer."],
  ["hand · Be Vietnam Pro nghiêng 18, chì", "font-hand text-hand text-miss", "còn thiếu · hiểu được vì sao"],
  ["body · 16/1.6", "text-body", "Vở ghi khác giáo trình ở điểm này."],
  ["small · 14 / caption · 13", "text-small text-ink-soft", "Giáo trình MMT · tr. 47 (trang file 55)"],
] as const;

export default function DesignPreviewPage() {
  return (
    <AppShell>
      <div className="flex flex-col gap-16">
        <header className="flex flex-col gap-4">
          <h1 className="text-title">Design preview</h1>
          <ThemeSwitch />
          <Suspense fallback={<p className="font-mono text-small text-ink-soft">web → …</p>}>
            <ServiceChain />
          </Suspense>
        </header>

        <section className="flex flex-col gap-4">
          <h2 className="text-section">Màu</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {SURFACES.map(([name, classes]) => (
              <div key={name} className={`${classes} rounded-md border border-line p-4 text-small`}>
                <div className="font-semibold">{name}</div>
                <div>Câu hỏi hôm nay</div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-6 text-body font-semibold">
            {INKS.map(([name, classes]) => (
              <span key={name} className={classes}>
                {name}
              </span>
            ))}
            <span className="bg-hl px-1">hl: đoạn nguồn được tô</span>
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-section">Chữ</h2>
          {TYPE.map(([meta, classes, sample]) => (
            <div key={meta} className="grid grid-cols-[180px_minmax(0,1fr)] items-baseline gap-6 border-b border-line py-5">
              <span className="text-caption text-ink-soft">{meta}</span>
              <span className={classes}>{sample}</span>
            </div>
          ))}
          <p className="font-display text-title">Ữ Ặ Ẫ Ỡ Ể Ộ</p>
          <p className="font-mono text-[15px]">fork() trả về 0 cho tiến trình con</p>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-section">Nút</h2>
          <div className="flex flex-wrap items-center gap-3">
            <Button>Bắt đầu</Button>
            <Button variant="secondary">Ôn thêm</Button>
            <Button variant="quiet">Không nhớ</Button>
            <Button disabled>Gửi</Button>
            <Button variant="secondary" disabled>
              Gửi lại (0:42)
            </Button>
          </div>
          <p className="text-small text-ink-soft">Tối đa một nút chính mỗi màn hình.</p>
        </section>

        <section className="flex max-w-[400px] flex-col gap-6">
          <h2 className="text-section">Ô nhập</h2>
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" defaultValue="minhanh.k21@sv.edu.vn" />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Mật khẩu</Label>
            <Input id="password" type="password" aria-describedby="password-hint" />
            <FieldHint id="password-hint">Ít nhất 8 ký tự. Không cần ký tự đặc biệt.</FieldHint>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="exam-date">Ngày thi</Label>
            <Input id="exam-date" defaultValue="02/10/2026" aria-invalid aria-describedby="exam-date-error" />
            <FieldError id="exam-date-error">Ngày thi phải sau hôm nay.</FieldError>
          </div>
          <div className="flex items-center gap-3">
            <input id="forgot" type="checkbox" className="size-[22px] accent-hong" />
            <label htmlFor="forgot">Không nhớ</label>
          </div>
          <div className="flex gap-8 font-medium">
            <a href="#forgot">Quên mật khẩu?</a>
            <a href="#forgot">Nhập sau</a>
          </div>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-section">Nhãn mức câu hỏi, cùng một kiểu</h2>
          <div className="flex gap-2.5">
            <Badge>Nhận biết</Badge>
            <Badge>Vận dụng</Badge>
            <Badge>Vận dụng cao</Badge>
          </div>
        </section>

        <section className="flex flex-col gap-8">
          <h2 className="text-section">Đồ vật: bìa vở, nhãn vở, bút dạ, bút chì</h2>
          <div className="flex justify-center px-6 pt-8 pb-12">
            <NotebookCover
              title="Hôm nay"
              aside={<span className="font-hand text-hand text-cam">thứ Sáu, 16/10</span>}
            >
              <NhanVo>
                <p className="m-0 mb-3.5 text-center font-display text-[18px] font-bold text-hong">
                  Phiên ôn
                </p>
                <NhanVoRow label="Số câu">14 câu</NhanVoRow>
                <NhanVoRow label="Thời gian">khoảng 25 phút</NhanVoRow>
                <NhanVoRow label="Môn">Mạng máy tính, Hệ điều hành</NhanVoRow>
              </NhanVo>
              <Button className="h-15 w-full rounded-[10px] text-[18px]">Bắt đầu</Button>
            </NotebookCover>
          </div>
          <PencilNote>còn thiếu · hiểu được vì sao</PencilNote>
        </section>
      </div>
    </AppShell>
  );
}
