"use client";

import { Button } from "@/components/ui/button";

const THEMES = [
  { value: "light", label: "Sáng" },
  { value: "dark", label: "Tối" },
  { value: "", label: "Theo hệ thống" },
] as const;

/** Preview only: sets <html data-theme>. The real switch lives in the account menu (T1.12). */
export function ThemeSwitch() {
  return (
    <div className="flex gap-2">
      {THEMES.map((theme) => (
        <Button
          key={theme.label}
          variant="secondary"
          onClick={() => {
            if (theme.value) {
              document.documentElement.dataset.theme = theme.value;
            } else {
              delete document.documentElement.dataset.theme;
            }
          }}
        >
          {theme.label}
        </Button>
      ))}
    </div>
  );
}
