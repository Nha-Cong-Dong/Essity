"use client";

import { Menu } from "@base-ui/react/menu";
import { useState } from "react";

import { authMessage } from "@/lib/auth-errors";
import { signOut } from "@/lib/sign-out";
import { chooseTheme, readTheme, type Theme } from "@/lib/theme";

// DESIGN.md §5, canvas Shells: a pill with ☰ and the initials; the menu shows the email,
// Chế độ hiển thị (Sáng / Tối / Theo hệ thống, §3.6) and Đăng xuất. Base UI gives Esc to close, arrow keys and focus back to the button (§11).

const ITEM =
  "flex h-11 w-full items-center justify-between rounded-[8px] px-3.5 text-left text-[15px] font-medium text-ink outline-none data-[highlighted]:bg-subtle data-[highlighted]:outline-2 data-[highlighted]:-outline-offset-2 data-[highlighted]:outline-hong";

const THEMES: [Theme, string][] = [
  ["light", "Sáng"],
  ["dark", "Tối"],
  ["system", "Theo hệ thống"],
];

function initials(email: string): string {
  return email.slice(0, 2).toUpperCase();
}

export function AccountMenu({ email }: { email: string }) {
  const [leaving, setLeaving] = useState(false);
  const [failed, setFailed] = useState(false);
  // Read when the menu opens: localStorage does not exist while the server renders.
  const [theme, setTheme] = useState<Theme>("system");

  function pick(value: Theme) {
    setTheme(value);
    chooseTheme(value, localStorage, document.documentElement);
  }

  // Stays signed in, and says so, if web could not clear the cookie (review cdbaa25 #1).
  async function logout() {
    setLeaving(true);
    setFailed(false);
    if (!(await signOut())) {
      setLeaving(false);
      setFailed(true);
    }
  }

  return (
    <Menu.Root onOpenChange={(open) => open && setTheme(readTheme(localStorage))}>
      <Menu.Trigger
        aria-label="Tài khoản"
        className="inline-flex h-11 items-center gap-2.5 rounded-full border border-line bg-sheet pr-1.5 pl-3.5 text-ink shadow-elev"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <span className="inline-flex size-8 items-center justify-center rounded-full bg-hong text-[13px] font-semibold text-on-hong">
          {initials(email)}
        </span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="end" sideOffset={8}>
          <Menu.Popup className="flex w-[300px] flex-col rounded-2xl border border-line bg-sheet p-2 text-ink shadow-panel">
            <p className="m-0 truncate px-3.5 py-2.5 text-small text-ink-soft">{email}</p>
            <Menu.Separator className="my-2 h-px bg-line" />
            <Menu.Group>
              <Menu.GroupLabel className="px-3.5 pt-1 pb-1.5 text-caption text-ink-soft">
                Chế độ hiển thị
              </Menu.GroupLabel>
              <Menu.RadioGroup value={theme} onValueChange={(value: Theme) => pick(value)}>
                {THEMES.map(([value, label]) => (
                  <Menu.RadioItem key={value} value={value} closeOnClick={false} className={ITEM}>
                    {label}
                    <Menu.RadioItemIndicator className="text-hong" aria-hidden="true">
                      ✓
                    </Menu.RadioItemIndicator>
                  </Menu.RadioItem>
                ))}
              </Menu.RadioGroup>
            </Menu.Group>
            <Menu.Separator className="my-2 h-px bg-line" />
            <Menu.Item className={ITEM} disabled={leaving} closeOnClick={false} onClick={logout}>
              Đăng xuất
            </Menu.Item>
            {failed && (
              <p role="alert" className="m-0 px-3.5 py-2 text-small text-partial">
                {authMessage("unavailable")}
              </p>
            )}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
