import assert from "node:assert/strict";
import test from "node:test";
import {
  FIGURE_GROUPS,
  figureArtifactPath,
  parseFigureManifest,
} from "../lib/figures.ts";

test("figure page exposes the complete A-F group order", () => {
  assert.deepEqual(
    FIGURE_GROUPS.map((group) => group.shortLabel),
    ["A", "B", "C", "D", "E", "F"],
  );
  assert.equal(
    FIGURE_GROUPS.find((group) => group.id === "eval")?.commandId,
    "figures_eval",
  );
});

test("figure manifests validate and artifact paths stay group-scoped", () => {
  const manifest = parseFigureManifest({
    generated_at: "2026-07-17T00:00:00Z",
    generation_id: "fresh-123",
    generator: "evaluation.generate_figures",
    artifact_policy: "fresh_compute_no_figure_reuse",
    group: "eval",
    figures: [
      {
        id: "f1",
        title: "Scores",
        kind: "chart",
        file: "f1.json",
        chart_type: "bar",
        caption: "caption",
        source_data: "report.json",
        status: "ok",
        skip_reason: null,
      },
    ],
  });
  assert.equal(manifest.figures[0].id, "f1");
  assert.equal(manifest.generation_id, "fresh-123");
  assert.equal(
    manifest.artifact_policy,
    "fresh_compute_no_figure_reuse",
  );
  assert.equal(
    figureArtifactPath("eval", manifest.figures[0].file!),
    "reports/figures/eval/f1.json",
  );
});
