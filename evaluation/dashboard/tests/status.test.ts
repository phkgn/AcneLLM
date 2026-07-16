import assert from "node:assert/strict";
import test from "node:test";
import { summarizeOllamaModels } from "../lib/status.ts";

test("counts Ollama model records without double-counting tag aliases", () => {
  const summary = summarizeOllamaModels([
    { name: "acnellm-v2-q4:latest" },
    { name: "qwen25-base-acnesys:latest" },
  ]);

  assert.equal(summary.modelCount, 2);
  assert.equal(summary.lookupNames.has("acnellm-v2-q4"), true);
  assert.equal(summary.lookupNames.has("qwen25-base-acnesys:latest"), true);
});
