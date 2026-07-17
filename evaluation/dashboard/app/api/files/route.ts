import fs from "node:fs/promises";
import { NextResponse } from "next/server";
import {
  EvaluationPathAccessError,
  assertRealPathInsideEvaluation,
  resolveEvaluationPath,
  resolveWhitelistedRepoVisual,
  toEvaluationRelative,
} from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const rawPath = url.searchParams.get("path") ?? "";
    const whitelistedVisual = await resolveWhitelistedRepoVisual(rawPath);
    const filePath =
      whitelistedVisual ??
      (await assertRealPathInsideEvaluation(resolveEvaluationPath(rawPath)));
    const stat = await fs.stat(filePath);
    if (!stat.isFile()) throw new Error("Path không phải file.");
    const raw = url.searchParams.get("raw") === "1";
    if (raw) {
      const extension = filePath.toLowerCase().split(".").pop() ?? "";
      const contentTypes: Record<string, string> = {
        png: "image/png",
        pdf: "application/pdf",
        html: "text/html; charset=utf-8",
      };
      const contentType = contentTypes[extension];
      if (!contentType) {
        throw new Error("Raw mode chỉ hỗ trợ PNG, PDF và HTML đã whitelist.");
      }
      if (extension === "html" && !whitelistedVisual) {
        throw new EvaluationPathAccessError(
          "Chỉ hai HTML visual đã whitelist được serve trực tiếp.",
        );
      }
      const content = await fs.readFile(filePath);
      return new NextResponse(content, {
        headers: {
          "Content-Type": contentType,
          "Cache-Control": "no-store",
          ...(extension === "html"
            ? {
                "Content-Security-Policy":
                  "sandbox allow-scripts allow-forms allow-popups",
              }
            : {}),
        },
      });
    }
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
      path: whitelistedVisual ? rawPath : toEvaluationRelative(filePath),
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
