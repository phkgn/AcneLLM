import fs from "node:fs/promises";
import path from "node:path";
import yaml from "js-yaml";
import { countNonEmptyLines } from "./files";
import {
  EVALUATION_ROOT,
  REPORTS_ROOT,
  toRepoRelative,
} from "./paths";
import type {
  CatalogDataset,
  CatalogExperiment,
  CatalogSystem,
} from "./types";

async function loadYaml(filePath: string): Promise<Record<string, unknown>> {
  try {
    return (yaml.load(await fs.readFile(filePath, "utf8")) ?? {}) as Record<
      string,
      unknown
    >;
  } catch {
    return {};
  }
}

async function filesIn(dir: string, extension: string): Promise<string[]> {
  try {
    return (await fs.readdir(dir, { withFileTypes: true }))
      .filter((entry) => entry.isFile() && entry.name.endsWith(extension))
      .map((entry) => path.join(dir, entry.name))
      .sort();
  } catch {
    return [];
  }
}

export async function listDatasets(): Promise<CatalogDataset[]> {
  const dir = path.join(EVALUATION_ROOT, "datasets", "v1");
  const manifestExists = await fs
    .access(path.join(dir, "MANIFEST.json"))
    .then(() => true)
    .catch(() => false);
  const files = await filesIn(dir, ".jsonl");
  return Promise.all(
    files.map(async (filePath) => ({
      name: path.basename(filePath),
      path: toRepoRelative(filePath),
      rows: await countNonEmptyLines(filePath),
      frozen: manifestExists,
    })),
  );
}

export async function listSystems(): Promise<CatalogSystem[]> {
  const files = await filesIn(
    path.join(EVALUATION_ROOT, "configs", "systems"),
    ".yaml",
  );
  return Promise.all(
    files.map(async (filePath) => {
      const config = await loadYaml(filePath);
      return {
        id: String(config.id ?? path.basename(filePath, ".yaml")),
        name: String(config.name ?? path.basename(filePath, ".yaml")),
        model: typeof config.model === "string" ? config.model : null,
        retrieval: config.retrieval === true,
        path: toRepoRelative(filePath),
      };
    }),
  );
}

export async function listExperiments(): Promise<CatalogExperiment[]> {
  const files = await filesIn(
    path.join(EVALUATION_ROOT, "configs", "experiments"),
    ".yaml",
  );
  return Promise.all(
    files.map(async (filePath) => {
      const config = await loadYaml(filePath);
      const dataset =
        typeof config.dataset === "string" ? config.dataset : null;
      const systemPaths = Array.isArray(config.systems) ? config.systems : [];
      const name = String(config.name ?? path.basename(filePath, ".yaml"));
      return {
        name,
        path: toRepoRelative(filePath),
        dataset,
        systems: systemPaths.map((item) =>
          path.basename(String(item), path.extname(String(item))),
        ),
        exists: dataset
          ? await fs
              .access(path.join(path.dirname(EVALUATION_ROOT), dataset))
              .then(() => true)
              .catch(() => false)
          : false,
      };
    }),
  );
}

export async function listReportRuns(): Promise<string[]> {
  try {
    return (await fs.readdir(REPORTS_ROOT, { withFileTypes: true }))
      .filter(
        (entry) =>
          entry.isDirectory() && !["unit", "retrieval"].includes(entry.name),
      )
      .map((entry) => entry.name)
      .sort();
  } catch {
    return [];
  }
}
