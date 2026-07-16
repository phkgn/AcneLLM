import fs from "node:fs/promises";
import path from "node:path";
import { readJsonFile } from "./files";
import { REPORTS_ROOT } from "./paths";

export async function latestRetrievalResult() {
  const root = path.join(REPORTS_ROOT, "retrieval");
  try {
    const dirs = await fs.readdir(root, { withFileTypes: true });
    const candidates = await Promise.all(
      dirs
        .filter((entry) => entry.isDirectory())
        .map(async (entry) => {
          const summaryPath = path.join(root, entry.name, "summary.json");
          const stat = await fs.stat(summaryPath).catch(() => null);
          return stat
            ? { name: entry.name, path: summaryPath, modifiedAt: stat.mtimeMs }
            : null;
        }),
    );
    const latest = candidates
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
      .sort((a, b) => b.modifiedAt - a.modifiedAt)[0];
    if (!latest) return null;
    return {
      name: latest.name,
      summary:
        (await readJsonFile<Record<string, unknown>>(latest.path)) ?? {},
    };
  } catch {
    return null;
  }
}

export async function readUnitReports() {
  const units = [
    ["normalizer", "summary.json"],
    ["intent_router", "report.json"],
    ["query_planner", "report.json"],
    ["guardrails", "report.json"],
  ] as const;
  const reports: Record<string, Record<string, unknown> | null> = {};
  await Promise.all(
    units.map(async ([name, file]) => {
      reports[name] = await readJsonFile<Record<string, unknown>>(
        path.join(REPORTS_ROOT, "unit", name, file),
      );
      if (!reports[name] && name === "normalizer") {
        reports[name] = await readJsonFile<Record<string, unknown>>(
          path.join(REPORTS_ROOT, "unit", name, "report.json"),
        );
      }
    }),
  );
  return reports;
}
