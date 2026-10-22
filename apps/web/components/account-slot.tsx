import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { requireVerifiedSession } from "@/lib/session";

async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

/** The account button of AppShell, in its own Suspense so the page does not wait on it. */
export function AccountSlot() {
  return (
    <Suspense fallback={null}>
      <Account />
    </Suspense>
  );
}
