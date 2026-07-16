export function t3OutputFlags(outDir: string, resume: boolean): string[] {
  return ["--out-dir", outDir, ...(resume ? ["--resume"] : [])];
}

export function checkGateRunFlags(runDir: string): string[] {
  return ["--run-dir", runDir];
}
