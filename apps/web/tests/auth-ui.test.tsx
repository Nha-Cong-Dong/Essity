// @vitest-environment jsdom
// T1.24 (US-12 AC1, AC5, AC6; D2, D3, D7, D8): the sign-in and sign-up screens of the approved
// mockup docs/design/screens-html/auth-v2.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { LoginForm } = await import("@/components/auth/login-form");
const { RegisterForm } = await import("@/components/auth/register-form");
const { emailProblem, usernameProblem } = await import("@/lib/username");
const { authMessage } = await import("@/lib/auth-errors");
const { CHECK_EMAIL_TITLE, FORGOT_PASSWORD_SENT } = await import("@/lib/auth-copy");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
beforeEach(() => go.mockReset());

type Call = { url: string; body?: unknown };
/** A fetch that answers each route in turn and records what it was asked. */
function fakeFetch(answer: (call: Call) => Response | Promise<Response>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const call = { url, body: init?.body ? JSON.parse(String(init.body)) : undefined };
      calls.push(call);
      return answer(call);
    }),
  );
  return calls;
}

const IDENTIFIER = "Tên đăng nhập hoặc email";

function signIn(identifier = "an", password = "x") {
  fireEvent.change(screen.getByLabelText(IDENTIFIER), { target: { value: identifier } });
  fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
}

describe("LoginForm (AC5, AC6)", () => {
  it("AC5: one field 'Tên đăng nhập hoặc email' sent as identifier, no Email field", async () => {
    const calls = fakeFetch(() => Response.json({ next: "/" }));
    render(<LoginForm />);
    expect(screen.queryByLabelText("Email")).toBeNull();
    signIn(" an.nguyen ", "password-marker");
    await waitFor(() => expect(go).toHaveBeenCalledWith("/"));
    expect(calls[0].body).toEqual({ identifier: "an.nguyen", password: "password-marker" });
  });

  it("AC5: a wrong login is one role=alert box with the one sentence", async () => {
    fakeFetch(() => Response.json({ error: "invalid_credentials" }, { status: 401 }));
    render(<LoginForm />);
    signIn();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Tên đăng nhập, email hoặc mật khẩu không đúng.");
    expect(authMessage("invalid_credentials")).toBe("Tên đăng nhập, email hoặc mật khẩu không đúng.");
  });

  it("AC6: after a 429 the box says the minutes from Retry-After and the button stays locked", async () => {
    fakeFetch(() => Response.json({ error: "rate_limited" }, { status: 429, headers: { "retry-after": "720" } }));
    render(<LoginForm />);
    signIn();
    expect((await screen.findByRole("alert")).textContent).toContain("Thử lại sau 12 phút.");
    expect((screen.getByRole("button", { name: "Đăng nhập" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("a wrong sign-in moves focus to the identifier field", async () => {
    fakeFetch(() => Response.json({ error: "invalid_credentials" }, { status: 401 }));
    render(<LoginForm />);
    signIn();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText(IDENTIFIER)));
  });

  it("while sending the fields are readOnly (not disabled) and the form is aria-busy", async () => {
    let finish: (reply: Response) => void = () => {};
    fakeFetch(() => new Promise<Response>((resolve) => (finish = resolve)));
    const { container } = render(<LoginForm />);
    signIn();
    const id = screen.getByLabelText(IDENTIFIER) as HTMLInputElement;
    await waitFor(() => expect(id.readOnly).toBe(true));
    expect(id.disabled).toBe(false);
    expect(container.querySelector("form")?.getAttribute("aria-busy")).toBe("true");
    finish(Response.json({ error: "invalid_credentials" }, { status: 401 }));
    await waitFor(() => expect(id.readOnly).toBe(false));
  });

  it("'Quên mật khẩu?' sits under the password field, 44px tall; Google and its divider are off", () => {
    const { container } = render(<LoginForm />);
    const link = screen.getByRole("link", { name: "Quên mật khẩu?" });
    expect(link.className).toContain("min-h-11");
    const password = container.querySelector("#password");
    expect(password && link.compareDocumentPosition(password) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    expect(screen.queryByText(/Google/)).toBeNull();
    expect(screen.queryByText("hoặc")).toBeNull();
  });
});

describe("RegisterForm (AC1, AC5)", () => {
  it("AC1: four fields in order, the optional one last, and no phone", () => {
    const { container } = render(<RegisterForm />);
    const names = [...container.querySelectorAll("input")].map((input) => input.name);
    expect(names).toEqual(["username", "email", "password", "name"]);
    expect(screen.getByLabelText("Họ và tên (không bắt buộc)")).toBeTruthy();
    expect(screen.queryByLabelText(/điện thoại/i)).toBeNull();
    expect(container.textContent).toContain("Essity gọi bạn bằng tên này. Bỏ trống thì dùng tên đăng nhập.");
  });

  it("lowercases the username as it is typed", () => {
    render(<RegisterForm />);
    const field = screen.getByLabelText("Tên đăng nhập") as HTMLInputElement;
    fireEvent.change(field, { target: { value: "An.Nguyen" } });
    expect(field.value).toBe("an.nguyen");
  });

  it("on blur with text, a malformed name gets its rule and no availability call", async () => {
    const calls = fakeFetch(() => Response.json({ available: true, reason: null }));
    render(<RegisterForm />);
    const field = screen.getByLabelText("Tên đăng nhập");
    fireEvent.change(field, { target: { value: "an nguyen" } });
    fireEvent.blur(field);
    expect(await screen.findByText("Chỉ dùng chữ không dấu, số, _ và .")).toBeTruthy();
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(calls).toHaveLength(0);
  });

  it("on blur, an empty field says nothing and asks nothing", () => {
    const calls = fakeFetch(() => Response.json({ available: true, reason: null }));
    render(<RegisterForm />);
    fireEvent.blur(screen.getByLabelText("Tên đăng nhập"));
    expect(calls).toHaveLength(0);
    expect(screen.queryByText(/Tên này đã có người dùng/)).toBeNull();
  });

  it("on blur, a well-formed name is checked and a taken one says 'Tên này đã có người dùng.'", async () => {
    const calls = fakeFetch(() => Response.json({ available: false, reason: "taken" }));
    render(<RegisterForm />);
    const field = screen.getByLabelText("Tên đăng nhập");
    fireEvent.change(field, { target: { value: "an.nguyen" } });
    fireEvent.blur(field);
    expect(await screen.findByText("Tên này đã có người dùng.")).toBeTruthy();
    expect(calls[0].url).toBe("/api/auth/username-available?username=an.nguyen");
  });

  it("a reserved name is told apart from a taken one", async () => {
    fakeFetch(() => Response.json({ available: false, reason: "reserved" }));
    render(<RegisterForm />);
    const field = screen.getByLabelText("Tên đăng nhập");
    fireEvent.change(field, { target: { value: "admin" } });
    fireEvent.blur(field);
    expect(await screen.findByText("Tên này không dùng được. Chọn tên khác.")).toBeTruthy();
  });

  it("a rate-limited availability check does not block the form", async () => {
    fakeFetch(() => Response.json({ error: "rate_limited" }, { status: 429 }));
    render(<RegisterForm />);
    const field = screen.getByLabelText("Tên đăng nhập");
    fireEvent.change(field, { target: { value: "an.nguyen" } });
    fireEvent.blur(field);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(field.getAttribute("aria-invalid")).toBeNull();
    expect((screen.getByRole("button", { name: "Tạo tài khoản" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("a failed availability check says nothing", async () => {
    const calls = fakeFetch(() => Response.json({ error: "unavailable" }, { status: 503 }));
    render(<RegisterForm />);
    const field = screen.getByLabelText("Tên đăng nhập");
    fireEvent.change(field, { target: { value: "an.nguyen" } });
    fireEvent.blur(field);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(field.getAttribute("aria-invalid")).toBeNull();
  });

  it("AC5: the server's 409 still shows 'Tên này đã có người dùng.' under the username", async () => {
    fakeFetch(() => Response.json({ error: "username_taken" }, { status: 409 }));
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Tên đăng nhập"), { target: { value: "an.nguyen" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "password-marker-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo tài khoản" }));
    expect(await screen.findByText("Tên này đã có người dùng.")).toBeTruthy();
    expect(screen.getByLabelText("Tên đăng nhập").getAttribute("aria-describedby")).toBe("username-error");
  });

  it("sends the trimmed Họ và tên as display_name only when filled", async () => {
    const calls = fakeFetch(() => Response.json({ next: "/check-email" }));
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Tên đăng nhập"), { target: { value: "an.nguyen" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText("Mật khẩu"), { target: { value: "password-marker-123" } });
    fireEvent.change(screen.getByLabelText("Họ và tên (không bắt buộc)"), { target: { value: " Nguyễn An " } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo tài khoản" }));
    await waitFor(() => expect(go).toHaveBeenCalledWith("/check-email"));
    expect(calls[0].body).toEqual({
      username: "an.nguyen",
      email: "a@example.com",
      password: "password-marker-123",
      display_name: "Nguyễn An",
    });
  });

  it("a refused sign-up moves focus to the first field in error, which names its error", async () => {
    fakeFetch(() => Response.json({ error: "username_taken" }, { status: 409 }));
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Tên đăng nhập"), { target: { value: "an.nguyen" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo tài khoản" }));
    const field = screen.getByLabelText("Tên đăng nhập");
    await waitFor(() => expect(document.activeElement).toBe(field));
    expect(document.getElementById(field.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "Tên này đã có người dùng.",
    );
  });

  it("a Họ và tên over the limit gets focus and its sentence", async () => {
    fakeFetch(() => Response.json({ error: "display_name_invalid" }, { status: 422 }));
    render(<RegisterForm />);
    fireEvent.click(screen.getByRole("button", { name: "Tạo tài khoản" }));
    const field = screen.getByLabelText("Họ và tên (không bắt buộc)");
    await waitFor(() => expect(document.activeElement).toBe(field));
    expect(document.getElementById("name-error")?.textContent).toBe("Họ và tên dài tối đa 60 ký tự.");
  });

  it("AC6: a 429 shows the minutes from Retry-After", async () => {
    fakeFetch(() => Response.json({ error: "rate_limited" }, { status: 429, headers: { "retry-after": "3600" } }));
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Tên đăng nhập"), { target: { value: "an.nguyen" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo tài khoản" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Thử lại sau 60 phút.");
  });
});

describe("username and email rules, one sentence per rule", () => {
  it.each([
    ["an nguyen", "Chỉ dùng chữ không dấu, số, _ và ."],
    ["1an", "Bắt đầu bằng một chữ cái."],
    ["a..b", "Không dùng hai dấu chấm liền nhau."],
    ["ab", "Tên đăng nhập cần 3–20 ký tự."],
    ["a".repeat(21), "Tên đăng nhập cần 3–20 ký tự."],
  ])("%s", (name, sentence) => expect(usernameProblem(name)).toBe(sentence));

  it("accepts a legal name and an email like an@gmail.com, refuses an@gmail", () => {
    expect(usernameProblem("an.nguyen_2")).toBeNull();
    expect(emailProblem("an@gmail.com")).toBeNull();
    expect(emailProblem("an@gmail")).toBe("Email chưa đúng dạng, ví dụ an@gmail.com");
  });
});

describe("check-email titles", () => {
  it("both 'check your email' screens share one title", () => {
    expect(CHECK_EMAIL_TITLE).toBe("Kiểm tra email của bạn");
    expect(FORGOT_PASSWORD_SENT.title).toBe(CHECK_EMAIL_TITLE);
  });
});
