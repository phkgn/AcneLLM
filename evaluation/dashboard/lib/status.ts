export function summarizeOllamaModels(
  models: Array<{ name?: string }>,
): { modelCount: number; lookupNames: Set<string> } {
  const rawNames = models
    .map((model) => model.name)
    .filter((name): name is string => Boolean(name));
  return {
    modelCount: rawNames.length,
    lookupNames: new Set(
      rawNames.flatMap((name) => [name, name.split(":")[0]]),
    ),
  };
}
