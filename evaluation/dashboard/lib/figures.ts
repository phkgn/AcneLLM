import type { CommandId } from "./types";

export type FigureGroupId =
  | "kb"
  | "finetune"
  | "model"
  | "usage"
  | "diagrams"
  | "eval";

export interface FigureManifestEntry {
  id: string;
  title: string;
  kind: "png" | "chart";
  file: string | null;
  data_file?: string | null;
  pdf_file?: string | null;
  chart_type: string;
  caption: string;
  source_data: string;
  status: "ok" | "skipped";
  skip_reason: string | null;
}

export interface FigureManifest {
  generated_at: string;
  generation_id?: string;
  generator?: string;
  artifact_policy?: string;
  group: string;
  figures: FigureManifestEntry[];
}

export interface FigureGroup {
  id: FigureGroupId;
  label: string;
  shortLabel: string;
  manifestPath: string | null;
  commandId: CommandId | null;
}

export const FIGURE_GROUPS: FigureGroup[] = [
  {
    id: "kb",
    label: "KB & Corpus (A)",
    shortLabel: "A",
    manifestPath: "reports/figures/kb/manifest.json",
    commandId: "figures_kb",
  },
  {
    id: "finetune",
    label: "Finetune Data (B)",
    shortLabel: "B",
    manifestPath: "reports/figures/finetune/manifest.json",
    commandId: "figures_kb",
  },
  {
    id: "model",
    label: "Model & Latency (C)",
    shortLabel: "C",
    manifestPath: "reports/figures/model/manifest.json",
    commandId: "figures_eval",
  },
  {
    id: "usage",
    label: "Usage (D)",
    shortLabel: "D",
    manifestPath: "reports/figures/usage/manifest.json",
    commandId: "figures_usage",
  },
  {
    id: "diagrams",
    label: "Diagrams (E)",
    shortLabel: "E",
    manifestPath: null,
    commandId: null,
  },
  {
    id: "eval",
    label: "Eval Results (F)",
    shortLabel: "F",
    manifestPath: "reports/figures/eval/manifest.json",
    commandId: "figures_eval",
  },
];

export function parseFigureManifest(value: unknown): FigureManifest {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Manifest không phải object.");
  }
  const raw = value as Record<string, unknown>;
  if (
    typeof raw.generated_at !== "string" ||
    typeof raw.group !== "string" ||
    !Array.isArray(raw.figures)
  ) {
    throw new Error("Manifest thiếu generated_at, group hoặc figures.");
  }
  const figures = raw.figures.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new Error("Figure entry không hợp lệ.");
    }
    const figure = item as Record<string, unknown>;
    if (
      typeof figure.id !== "string" ||
      typeof figure.title !== "string" ||
      !["png", "chart"].includes(String(figure.kind)) ||
      !["ok", "skipped"].includes(String(figure.status))
    ) {
      throw new Error("Figure entry thiếu id/title/kind/status.");
    }
    return figure as unknown as FigureManifestEntry;
  });
  return {
    generated_at: raw.generated_at,
    generation_id:
      typeof raw.generation_id === "string"
        ? raw.generation_id
        : undefined,
    generator:
      typeof raw.generator === "string" ? raw.generator : undefined,
    artifact_policy:
      typeof raw.artifact_policy === "string"
        ? raw.artifact_policy
        : undefined,
    group: raw.group,
    figures,
  };
}

export function figureArtifactPath(
  group: FigureGroupId,
  file: string,
): string {
  return `reports/figures/${group}/${file}`;
}
