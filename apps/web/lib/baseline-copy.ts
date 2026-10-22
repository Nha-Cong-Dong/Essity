import type { BaselineError } from "@/lib/baseline-input";

// The baseline screen's refusals (DESIGN.md §6.2). The GPA range sentence is DESIGN's; the
// others were chosen by the user on 22/10 (plan K7).
export const BASELINE_MESSAGES: Record<BaselineError, string> = {
  gpa_range: "GPA thang 4 nằm trong khoảng 0 đến 4.",
  gpa_decimals: "GPA nhập tối đa 2 chữ số sau dấu chấm, ví dụ 2.85.",
  days_range: "Số ngày là số nguyên từ 0 đến 365.",
};
