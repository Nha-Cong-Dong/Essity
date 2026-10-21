import { redirect } from "next/navigation";

// "/" is "Phiên hôm nay" (DESIGN.md §6.3); the proxy sends a visitor without a session to /login.
export default function Home() {
  redirect("/today");
}
