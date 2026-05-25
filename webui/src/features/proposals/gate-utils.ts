export function summarizeGateOutput(output: string, tailLines: number = 20): string {
  const lines = output.split("\n");
  if (lines.length <= tailLines) return output;
  const tail = lines.slice(-tailLines).join("\n");
  return `...(${lines.length - tailLines} lines omitted)\n${tail}`;
}
