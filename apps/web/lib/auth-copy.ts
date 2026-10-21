// The sentences of "Hãy kiểm tra email của bạn" after "Quên mật khẩu" (T1.14). The user writes
// this text (docs/PROGRESS.md, M1 decisions); until then it is the canvas's sign-up text.
export const FORGOT_PASSWORD_SENT = {
  title: "Hãy kiểm tra email của bạn",
  /** Followed by the masked address. */
  sentTo: "Đã gửi link tới",
  body: "Mở email và bấm vào link để tiếp tục. Nếu không thấy, xem cả mục thư rác.",
} as const;
