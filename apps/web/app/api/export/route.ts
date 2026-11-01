import type { NextRequest } from "next/server";

import { coreFetch } from "@/lib/core";
import { errorResponse, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";

// T9.5, US-10 AC8: "Tải dữ liệu (CSV)" on /stats. A plain GET link, so the browser downloads the
// file; the session cookie becomes the bearer token and only core-api's CSV body is passed on.
export async function GET(request: NextRequest) {
  const session = request.cookies.get(SESSION_COOKIE)?.value;
  if (!session) return errorResponse("signed_out", 401);
  let response: Response;
  try {
    response = await coreFetch(
      "/v1/export.csv",
      { headers: { authorization: `Bearer ${session}`, accept: "text/csv" } },
      15_000,
    );
  } catch (error) {
    return unavailable("export", error);
  }
  if (response.status === 401) return errorResponse("signed_out", 401);
  if (!response.ok) return errorResponse("unavailable", 503);
  return new Response(response.body, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="essity.csv"',
      "cache-control": "no-store",
    },
  });
}
