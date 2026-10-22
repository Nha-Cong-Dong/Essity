import type { Metadata } from "next";
import { Be_Vietnam_Pro, Bricolage_Grotesque, JetBrains_Mono } from "next/font/google";

import { THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

// DESIGN.md §3.2. All three have a Vietnamese subset; next/font self-hosts them, so browsers
// never call Google and text never waits on a font request.
const beVietnamPro = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  // Not a variable font: list the weights in use. Italic is the "written" voice (font-hand).
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-be-vietnam-pro", // interface, body text, answers, written values
});
const bricolage = Bricolage_Grotesque({
  subsets: ["latin", "vietnamese"],
  axes: ["opsz"],
  variable: "--font-bricolage", // titles, numbers, questions, logo
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin", "vietnamese"],
  variable: "--font-jetbrains-mono", // real code only
});

export const metadata: Metadata = {
  title: "Essity",
  description: "Ôn tập theo lịch, chấm bằng AI.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const fonts = [beVietnamPro, bricolage, jetbrainsMono].map((f) => f.variable).join(" ");
  return (
    // The script may set data-theme before React hydrates <html>; only that attribute differs.
    <html lang="vi" className={`${fonts} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
