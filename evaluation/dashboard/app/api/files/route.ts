import fs from "node:fs/promises";
import { NextResponse } from "next/server";
import {
  EvaluationPathAccessError,
  assertRealPathInsideEvaluation,
  resolveEvaluationPath,
  toEvaluationRelative,
} from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const rawPath = url.searchParams.get("path") ?? "";
    const filePath = await assertRealPathInsideEvaluation(
      resolveEvaluationPath(rawPath),
    );
    const stat = await fs.stat(filePath);
    if (!stat.isFile()) throw new Error("Path không phải file.");
    const tailRaw = url.searchParams.get("tail");
    const tail = tailRaw ? Number(tailRaw) : null;
    if (
      tail !== null &&
      (!Number.isInteger(tail) || tail < 1 || tail > 10_000)
    ) {
      throw new Error("tail phải là số nguyên từ 1 đến 10000.");
    }
    const text = await fs.readFile(filePath, "utf8");
    const content =
      tail === null ? text : text.split(/\r?\n/).slice(-tail).join("\n");
    return NextResponse.json({
      path: toEvaluationRelative(filePath),
      size: stat.size,
      modifiedAt: stat.mtime.toISOString(),
      content,
    });
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    const status =
      error instanceof EvaluationPathAccessError
        ? 403
        : code === "ENOENT"
          ? 404
          : 400;
    return NextResponse.json(
      { error: (error as Error).message },
      { status },
    );
  }
}
