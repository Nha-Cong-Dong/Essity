import type { Metadata } from "next";
import { Bricolage_Grotesque, JetBrains_Mono, Lexend, Patrick_Hand } from "next/font/google";

import "./globals.css";

// DESIGN.md §3.2. All four have a Vietnamese subset; next/font self-hosts them, so browsers
// never call Google and text never waits on a font request.
const lexend = Lexend({
  subsets: ["latin", "vietnamese"],
  variable: "--font-lexend", // interface, body text, answers, document excerpts
});
const bricolage = Bricolage_Grotesque({
  subsets: ["latin", "vietnamese"],
  axes: ["opsz"],
  variable: "--font-bricolage", // titles, numbers, questions, logo
});
const patrickHand = Patrick_Hand({
  subsets: ["latin", "vietnamese"],
  weight: "400",
  variable: "--font-patrick-hand", // short handwritten values, pencil grading notes
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
  const fonts = [lexend, bricolage, patrickHand, jetbrainsMono].map((f) => f.variable).join(" ");
  return (
    <html lang="vi" className={`${fonts} h-full antialiased`}>
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
