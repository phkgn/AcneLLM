export function lineClass(line: string): string {
  if (/^\[runall\]/.test(line)) {
    if (/\bstatus=fail\b/i.test(line)) {
      return "text-[#ff9278] font-semibold";
    }
    if (/\bstatus=ok\b/i.test(line)) {
      return "text-[#cde76c] font-semibold";
    }
    return "text-clay font-semibold";
  }
  if (/FALLBACK DETECTED|FAIL|ERROR|Traceback/i.test(line)) {
    return "text-[#ff9278]";
  }
  if (/⚠|WARN/i.test(line)) return "text-[#ffd166]";
  if (/\bOK\b|✓|passed/i.test(line)) return "text-[#cde76c]";
  if (/^\[dashboard\]|^\[command\]/.test(line)) return "text-[#80bfff]";
  return "text-[#d8ded9]";
}
