// T2.14: the words of /today. DESIGN.md §6.3 holds the approved ones; the sentences marked
// data-copy="tam" where they are drawn wait for the user (risk register R09).

const WEEKDAYS = ["Chủ nhật", "thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy"];

/** "thứ Tư, 21/10" for an ISO date (a learning day: no time zone to apply). */
export function dayLabel(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return `${weekday}, ${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}`;
}

/** The backlog note's N (US-03 AC5): the sessions it takes beyond one a day (plan C2). */
export function extraSessions(sessions: number, days: number): number {
  return sessions - days;
}

export const TODAY_COPY = {
  lead: "Phiên ôn tối nay",
  questions: "câu",
  start: "Bắt đầu",
  resume: "Tiếp tục",
  subjectsTile: "Môn đang ôn",
  rested: "Hôm nay không cần ôn.",
  nextSession: "Phiên tiếp theo:",
  noSubjects: "Chưa có môn nào.",
  noSubjectsHint: "Tạo môn đầu tiên bằng tên và ngày thi.",
  createSubject: "Tạo môn",
  failed: "Không tải được phiên hôm nay.",
  failedHint: "Kiểm tra kết nối rồi thử lại.",
  retry: "Thử lại",
  afterSession: "Sau buổi học",
  whatDidYouLearn: "Hôm nay bạn học gì?",
  logSession: "Ghi buổi học",
  firstSession: "Ghi buổi học đầu tiên để app soạn câu hỏi cho bạn.",
} as const;
