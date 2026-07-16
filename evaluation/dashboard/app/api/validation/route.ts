import { NextResponse } from "next/server";
import { latestValidationSummary } from "@/lib/validation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const afterRaw = url.searchParams.get("after");
  const afterMs = afterRaw ? Date.parse(afterRaw) : 0;
  return NextResponse.json({
    validation: await latestValidationSummary(
      Number.isFinite(afterMs) ? afterMs : 0,
    ),
  });
}
