import { NextResponse } from "next/server";
import {
  DATASET_KEYS,
  ReviewConflictError,
  type DatasetKey,
  exportApprovedDataset,
} from "@/lib/dataset-review";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const dataset = url.searchParams.get("dataset");
    if (!DATASET_KEYS.includes(dataset as DatasetKey)) {
      throw new Error("Chọn đúng một dataset D2/D3/D4/D5/D6/D7 để export.");
    }
    const version = (url.searchParams.get("version") ?? "v1.0").trim();
    if (!/^[a-zA-Z0-9._-]+$/.test(version)) {
      throw new Error("dataset_version không hợp lệ.");
    }
    const exported = await exportApprovedDataset(
      dataset as DatasetKey,
      version,
    );
    const content = exported.rows
      .map((row) => JSON.stringify(row))
      .join("\n");
    return new NextResponse(`${content}${content ? "\n" : ""}`, {
      headers: {
        "Content-Type": "application/x-ndjson; charset=utf-8",
        "Content-Disposition": `attachment; filename="${exported.filename}"`,
        "X-Approved-Rows": String(exported.rows.length),
      },
    });
  } catch (error) {
    if (error instanceof ReviewConflictError) {
      return NextResponse.json(
        { error: error.message, summary: error.summary },
        { status: 409 },
      );
    }
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }
}
