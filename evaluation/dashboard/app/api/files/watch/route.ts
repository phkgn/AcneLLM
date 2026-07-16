import { NextResponse } from "next/server";
import {
  assertRealPathInsideEvaluation,
  resolveEvaluationPath,
} from "@/lib/paths";
import { createTailStream, SSE_HEADERS } from "@/lib/sse";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const filePath = await assertRealPathInsideEvaluation(
      resolveEvaluationPath(url.searchParams.get("path") ?? ""),
    );
    return new Response(createTailStream(filePath, request.signal), {
      headers: SSE_HEADERS,
    });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }
}
