import fs from "node:fs/promises";

export async function readJsonFile<T>(filePath: string): Promise<T | null> {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8")) as T;
  } catch {
    return null;
  }
}

export async function readJsonl(filePath: string): Promise<Record<string, unknown>[]> {
  try {
    const text = await fs.readFile(filePath, "utf8");
    const rows: Record<string, unknown>[] = [];
    for (const line of text.split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        rows.push(JSON.parse(line) as Record<string, unknown>);
      } catch {
        // The last line can be temporarily incomplete while a runner is appending.
      }
    }
    return rows;
  } catch {
    return [];
  }
}

export async function countNonEmptyLines(filePath: string): Promise<number> {
  try {
    const text = await fs.readFile(filePath, "utf8");
    return text.split(/\r?\n/).filter((line) => line.trim()).length;
  } catch {
    return 0;
  }
}

export function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
