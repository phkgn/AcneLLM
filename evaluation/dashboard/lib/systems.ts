import fs from "node:fs";
import path from "node:path";
import yaml from "js-yaml";
import { EVALUATION_ROOT } from "./paths";

export function loadSystemLabels(): Record<string, string> {
  const root = path.join(EVALUATION_ROOT, "configs", "systems");
  return Object.fromEntries(
    fs.readdirSync(root)
      .filter((file) => /^s[0-4]\.yaml$/.test(file))
      .map((file) => {
        const config = yaml.load(fs.readFileSync(path.join(root, file), "utf8")) as Record<string, unknown>;
        const id = String(config.id ?? path.basename(file, ".yaml"));
        return [id, String(config.name ?? id)];
      }),
  );
}
