// @vitest-environment jsdom
// T1.18: the baseline form as the user meets it (US-11 AC1, AC2, AC3; DESIGN.md §6.2).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { BaselineForm } = await import("@/components/baseline/baseline-form");

type Sent = { path: string; body: unknown };

/** The browser's fetch to web's own routes: records each call, answers with `reply`. */
function fakeWeb(reply: (path: string) => Response = () => Response.json({ next: "/subjects/new" })) {
  const sent: Sent[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init: RequestInit = {}) => {
      sent.push({ path, body: init.body ? JSON.parse(String(init.body)) : undefined });
      return reply(path);
    }),
  );
  return sent;
}

const gpa = () => screen.getByLabelText("GPA hiện tại (thang 4)") as HTMLInputElement;
const days = () =>
  screen.getByLabelText("Kỳ trước, bạn học xong bao nhiêu ngày trước khi thi?") as HTMLInputElement;
const unknown = () => screen.getByLabelText("Không nhớ") as HTMLInputElement;
const save = () => fireEvent.click(screen.getByRole("button", { name: "Lưu và tiếp tục" }));

function fill(gpaText: string, daysText: string) {
  fireEvent.change(gpa(), { target: { value: gpaText } });
  fireEvent.change(days(), { target: { value: daysText } });
}

describe("BaselineForm (T1.18)", () => {
  beforeEach(() => {
    go.mockReset();
    render(<BaselineForm />);
  });
  afterEach(cleanup);

  it("US-11 AC1: two fields and a \"Không nhớ\" box, nothing else to type", () => {
    const form = gpa().closest("form") as HTMLFormElement;
    const typed = form.querySelectorAll("input:not([type=checkbox]), select, textarea");
    expect(typed).toHaveLength(2);
    expect(unknown().type).toBe("checkbox");
    expect(form.getAttribute("method")).toBe("post"); // review plan R2
  });

  it("US-11 AC1, AC2: a save sends the two numbers and goes where the route says", async () => {
    const sent = fakeWeb();
    fill("2,85", "3");

    save();

    await waitFor(() => expect(go).toHaveBeenCalledWith("/subjects/new"));
    expect(sent).toEqual([
      { path: "/api/baseline", body: { gpa_before: "2.85", prior_ready_days: 3, prior_days_unknown: false } },
    ]);
  });

  // Red when: the day count can still be typed, or is sent, once "Không nhớ" is ticked.
  it("US-11 AC1: \"Không nhớ\" empties and locks the day count, and sends prior_days_unknown", async () => {
    const sent = fakeWeb();
    fill("3", "12");

    fireEvent.click(unknown());

    expect(days().disabled).toBe(true);
    expect(days().value).toBe("0");
    save();
    await waitFor(() => expect(go).toHaveBeenCalled());
    expect(sent[0].body).toEqual({ gpa_before: "3", prior_days_unknown: true });
  });

  it("US-11 AC1: unticking \"Không nhớ\" gives the day field back", () => {
    fireEvent.click(unknown());
    fireEvent.click(unknown());

    expect(days().disabled).toBe(false);
  });

  // Red when: the range check is dropped from the form (the user would wait for core-api's 422).
  it("US-11 AC3: GPA 4.5 shows DESIGN.md §6.2's sentence under the field and sends nothing", () => {
    const sent = fakeWeb();
    fill("4.5", "3");

    save();

    expect(screen.getByText("GPA thang 4 nằm trong khoảng 0 đến 4.")).toBeTruthy();
    expect(gpa().getAttribute("aria-invalid")).toBe("true");
    expect(gpa().getAttribute("aria-describedby")).toBe("gpa-error");
    expect(sent).toHaveLength(0);
  });

  it("US-11 AC3: GPA 2.857 asks for two decimals", () => {
    fakeWeb();
    fill("2.857", "3");

    save();

    expect(screen.getByText("GPA nhập tối đa 2 chữ số sau dấu chấm, ví dụ 2.85.")).toBeTruthy();
  });

  it("US-11 AC3: 366 days shows the day sentence and sends nothing", () => {
    const sent = fakeWeb();
    fill("3", "366");

    save();

    expect(screen.getByText("Số ngày là số nguyên từ 0 đến 365.")).toBeTruthy();
    expect(days().getAttribute("aria-invalid")).toBe("true");
    expect(sent).toHaveLength(0);
  });

  it("US-11 AC3: a 422 naming a field puts that field's sentence under it", async () => {
    fakeWeb(() => Response.json({ error: "invalid", fields: ["prior_ready_days"] }, { status: 422 }));
    fill("3", "12");

    save();

    expect(await screen.findByText("Số ngày là số nguyên từ 0 đến 365.")).toBeTruthy();
    expect(go).not.toHaveBeenCalled();
  });

  it("a network failure keeps what was typed and says so", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    fill("3", "12");

    save();

    expect(await screen.findByText("Chưa gửi được. Kiểm tra kết nối rồi thử lại.")).toBeTruthy();
    expect(gpa().value).toBe("3");
    expect(days().value).toBe("12");
  });

  it("a session that ended goes to /login", async () => {
    fakeWeb(() => Response.json({ error: "signed_out" }, { status: 401 }));
    fill("3", "12");

    save();

    await waitFor(() => expect(go).toHaveBeenCalledWith("/login"));
  });

  // Red when: "Nhập sau" is a link to /today: needs_baseline stays true and nothing records the skip.
  it("US-11 AC2: \"Nhập sau\" records the skip, then goes where the route says", async () => {
    const sent = fakeWeb(() => Response.json({ next: "/today" }));

    fireEvent.click(screen.getByRole("button", { name: "Nhập sau" }));

    await waitFor(() => expect(go).toHaveBeenCalledWith("/today"));
    expect(sent).toEqual([{ path: "/api/baseline/skip", body: undefined }]);
  });

  it("review plan R3: a `next` outside the allowed pages goes to /today", async () => {
    fakeWeb(() => Response.json({ next: "//evil.example" }));
    fill("3", "12");

    save();

    await waitFor(() => expect(go).toHaveBeenCalledWith("/today"));
  });

  it("US-11 AC5: says that the baseline locks after 7 days", () => {
    expect(screen.getByText("Sau 7 ngày, mốc này sẽ không sửa được nữa.")).toBeTruthy();
  });
});
