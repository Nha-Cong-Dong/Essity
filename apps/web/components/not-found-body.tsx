import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { PageColumn } from "@/components/shells";
import { buttonVariants } from "@/components/ui/button";

/** E-06: the 404 words (DESIGN.md voice: short, calm, one way on). Shared by the root page and the subject one. */
export const NOT_FOUND_TITLE = "Không tìm thấy trang này";
export const NOT_FOUND_HINT = "Đường dẫn có thể đã gõ sai, hoặc trang không còn nữa.";

export function NotFoundBody({ href = "/today", label = "Về trang Hôm nay" }: { href?: string; label?: string }) {
  return (
    <PageColumn width="read">
      <EmptyState
        mascot="nghi"
        title={NOT_FOUND_TITLE}
        hint={NOT_FOUND_HINT}
        action={
          <Link href={href} className={buttonVariants({ variant: "primary", size: "lg" })}>
            {label}
          </Link>
        }
      />
    </PageColumn>
  );
}
