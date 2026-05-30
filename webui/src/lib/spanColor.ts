/** Jaeger-style stable service → color mapping (IBM Carbon palette via CSS vars). */

const SPAN_COLOR_VARS = Array.from({ length: 20 }, (_, i) => `--span-color-${i + 1}`);

class SpanColorGenerator {
  private readonly colors: string[];
  private readonly cache = new Map<string, number>();
  private currentIdx = 0;

  constructor(colors: string[] = SPAN_COLOR_VARS.map((v) => `var(${v})`)) {
    this.colors = colors;
  }

  getColorByKey(key: string): string {
    let idx = this.cache.get(key);
    if (idx == null) {
      idx = this.currentIdx;
      this.cache.set(key, idx);
      this.currentIdx = (this.currentIdx + 1) % this.colors.length;
    }
    return this.colors[idx];
  }

  clear(): void {
    this.cache.clear();
    this.currentIdx = 0;
  }
}

export const spanColorGenerator = new SpanColorGenerator();

export function spanServiceColor(serviceName: string): string {
  return spanColorGenerator.getColorByKey(serviceName.trim() || "harnesslab");
}
