"use client";

import { Menu } from "@base-ui/react/menu";
import { useState } from "react";

import { authMessage } from "@/lib/auth-errors";
import { signOut } from "@/lib/sign-out";
import { browserStorage, chooseTheme, readTheme, type Theme } from "@/lib/theme";

// Design system v3.1 §5: a 40px rose circle with the initials; the menu shows the email,
// Chế độ hiển thị (Sáng / Tối / Theo hệ thống, §3.6) and Đăng xuất. Base UI gives Esc to close, arrow keys and focus back to the button (§11).

const ITEM =
  "flex h-11 w-full items-center justify-between rounded-control px-3 text-left text-body font-medium text-ink outline-none data-[highlighted]:bg-rose-50 data-[highlighted]:outline-2 data-[highlighted]:-outline-offset-2 data-[highlighted]:outline-focus";

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
    chooseTheme(value, browserStorage(), document.documentElement);
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
    <Menu.Root onOpenChange={(open) => open && setTheme(readTheme(browserStorage()))}>
      <Menu.Trigger
        aria-label="Tài khoản"
        className="inline-flex size-10 items-center justify-center rounded-full bg-rose-100 text-meta font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        {initials(email)}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="end" sideOffset={8}>
          <Menu.Popup className="z-(--z-menu) flex w-[300px] flex-col rounded-sheet bg-raised p-2 text-ink shadow-over">
            <p className="m-0 truncate px-3.5 py-2.5 text-meta text-ink-soft">{email}</p>
            <Menu.Separator className="my-2 h-px bg-line" />
            <Menu.Group>
              <Menu.GroupLabel className="px-3.5 pt-1 pb-1.5 text-meta text-ink-soft">
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
              <p role="alert" className="m-0 px-3.5 py-2 text-meta text-partial">
                {authMessage("unavailable")}
              </p>
            )}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
