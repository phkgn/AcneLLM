import fs from "node:fs/promises";
import path from "node:path";
import { readJsonFile } from "./files";
import { REPORTS_ROOT, toRepoRelative } from "./paths";

export type ValidationSummary = {
  generated_at?: string;
  verdict?: "TRUSTWORTHY" | "PARTIAL" | "NOT_TRUSTWORTHY";
  conflicts_n?: number;
  per_check?: Array<{
    name?: string;
    status?: "PASS" | "FAIL" | "WARN" | "SKIPPED";
    evidence?: unknown;
    critical?: boolean;
  }>;
  human_review_queue?: unknown[];
  confidence_notes?: string[];
  tier_verdicts?: Record<string, { verdict?: string; reason?: string }>;
};

export async function latestValidationSummary(afterMs = 0) {
  const root = path.join(REPORTS_ROOT, "validation");
  try {
    const dirs = await fs.readdir(root, { withFileTypes: true });
    const candidates = await Promise.all(
      dirs
        .filter((entry) => entry.isDirectory())
        .map(async (entry) => {
          const summaryPath = path.join(root, entry.name, "summary.json");
          const stat = await fs.stat(summaryPath).catch(() => null);
          if (!stat || stat.mtimeMs < afterMs) return null;
          return {
            name: entry.name,
            path: summaryPath,
            modifiedAt: stat.mtimeMs,
          };
        }),
    );
    const latest = candidates
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
      .sort((a, b) => b.modifiedAt - a.modifiedAt)[0];
    if (!latest) return null;
    return {
      name: latest.name,
      path: toRepoRelative(latest.path),
      modifiedAt: new Date(latest.modifiedAt).toISOString(),
      summary:
        (await readJsonFile<ValidationSummary>(latest.path)) ?? {},
    };
  } catch {
    return null;
  }
}
