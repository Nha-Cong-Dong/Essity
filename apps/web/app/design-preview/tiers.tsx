"use client";

import { useState } from "react";

import { Mascot } from "@/components/mascot";
import { BackLink, Block, SectionHead } from "@/components/screen-kit";
import { Button } from "@/components/ui/button";
import { Carousel } from "@/components/ui/carousel";
import { Dialog } from "@/components/ui/dialog";

// DESIGN-W0: the four tiers of a block, the card band and the praise dialog, drawn once in the light
// palette and once in the dark one ([data-tone] switches the tokens of a subtree), whatever the
// theme of the page. Closed outside development like the rest of /design-preview.

const CARDS = [
  ["Nhiệt độ sôi", "Nước sôi ở 100 °C khi áp suất là 1 atm."],
  ["Áp suất", "Áp suất giảm thì nhiệt độ sôi giảm."],
  ["Hơi nước", "Hơi bão hòa là hơi ở trạng thái cân bằng với chất lỏng."],
  ["Nhiệt dung", "Nhiệt cần để tăng một độ cho một đơn vị khối lượng."],
  ["Ẩn nhiệt", "Nhiệt cần để đổi pha mà nhiệt độ không đổi."],
] as const;

function Tiers({ tone }: { tone: "light" | "dark" }) {
  const [open, setOpen] = useState(false);
  const [host, setHost] = useState<HTMLElement | null>(null);
  return (
    <div ref={setHost} data-tone={tone} className="flex flex-col gap-6 rounded-sheet bg-bg p-6 text-ink" data-testid={`tiers-${tone}`}>
      <p className="m-0 text-meta text-ink-soft">{tone === "light" ? "Sáng" : "Tối"}</p>
      <BackLink href="/design-preview">Môn học</BackLink>
      <div className="grid gap-5 md:grid-cols-2">
        <Block tier="field" className="flex flex-col items-start gap-4">
          <span className="text-meta text-on-plum-soft">T1 · trường màu</span>
          <span className="font-display text-display">14</span>
          <span className="text-body">thẻ đến hạn hôm nay</span>
          <a
            href="/design-preview"
            className="inline-flex h-13 items-center rounded-full bg-on-plum-action px-6 font-semibold text-on-plum-action-fg no-underline"
          >
            Bắt đầu ôn
          </a>
        </Block>
        <div className="flex flex-col gap-5">
          <Block tier="tint">
            <p className="m-0 text-meta text-ink-soft">T2 · ô nhấn hồng</p>
            <p className="m-0 mt-1 font-display text-lead">Học gì tiếp theo?</p>
          </Block>
          <Block tier="tint" tone="cam">
            <p className="m-0 text-meta text-cam">→ Tiếp theo</p>
            <p className="m-0 mt-1 font-display text-lead">Mạng máy tính · Chương 3</p>
          </Block>
          <Block tier="sheet">
            <p className="m-0 text-meta text-ink-soft">T3 · tờ, viền 1px</p>
            <p className="m-0 mt-1 text-body">Không bóng, không nền màu.</p>
          </Block>
        </div>
      </div>
      <div className="flex items-center justify-between border-b border-line py-3">
        <span className="text-body">T4 · hàng trần trên nền</span>
        <span className="text-meta text-ink-soft">thi 20/12</span>
      </div>
      <div className="flex flex-col gap-3">
        <SectionHead title="Băng thẻ" />
        <Carousel label={`Thẻ của buổi học (${tone})`}>
          {CARDS.map(([title, body]) => (
            <Block key={title} tier="sheet" className="rounded-tile">
              <p className="m-0 font-display text-lead">{title}</p>
              <p className="m-0 mt-2 text-body text-ink-soft">{body}</p>
            </Block>
          ))}
        </Carousel>
      </div>
      <div>
        <Button variant="secondary" onClick={() => setOpen(true)}>
          Mở popup khen ({tone === "light" ? "sáng" : "tối"})
        </Button>
        <Dialog
          open={open}
          onOpenChange={setOpen}
          variant="celebrate"
          container={host}
          title="Buổi học hôm nay xong rồi"
          description="Thẻ của buổi này đang được chuẩn bị, xong sẽ báo bạn."
          media={<Mascot pose="chucmung" size="lg" />}
        >
          <div className="grid grid-cols-2 gap-3">
            <Button onClick={() => setOpen(false)}>Về trang chủ</Button>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Học tiếp môn này
            </Button>
          </div>
        </Dialog>
      </div>
    </div>
  );
}

export function TiersPreview() {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lead">Tầng khối, băng thẻ, popup khen (DESIGN-V3)</h2>
      <div className="grid gap-6 xl:grid-cols-2">
        <Tiers tone="light" />
        <Tiers tone="dark" />
      </div>
    </section>
  );
}
