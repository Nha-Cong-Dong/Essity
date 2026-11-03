import type { NextRequest } from "next/server";

import { forwardCard } from "@/lib/vault-routes";

type Params = { params: Promise<{ id: string }> };

// G4: "Nguồn" of a card (a GET: no origin check).
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardCard(request, id, "GET", "sources");
}
