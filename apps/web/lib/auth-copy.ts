// The sentences of "Kiểm tra email của bạn" after "Quên mật khẩu" (T1.14). Chosen by the
// user on 2026-10-21; "1 giờ" is RESET_PASSWORD_TTL in core-api (domain/auth/tokens.py).
/** One title for both "check your email" screens (T7.22 review): after sign-up and after "Quên mật khẩu". */
export const CHECK_EMAIL_TITLE = "Kiểm tra email của bạn";

export const FORGOT_PASSWORD_SENT = {
  title: CHECK_EMAIL_TITLE,
  /** Followed by the masked address. */
  sentTo: "Đã gửi link tới",
  body: "Mở email và bấm vào link để đặt mật khẩu mới. Link dùng được trong 1 giờ. Nếu không thấy, xem cả mục thư rác.",
} as const;
