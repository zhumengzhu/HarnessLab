import { useMemo } from "react";
import hljs from "highlight.js/lib/core";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import JSON5 from "json5";
import "highlight.js/styles/github-dark.min.css";

hljs.registerLanguage("json", json);
hljs.registerLanguage("javascript", javascript);

function highlightLanguage(source: string): "json" | "javascript" {
  if (source.includes("//") || source.includes("/*")) {
    return "javascript";
  }
  return "json";
}

export function JsonHighlight({ source }: { source: string }) {
  const html = useMemo(() => {
    if (!source.trim()) return "";
    const lang = highlightLanguage(source);
    try {
      return hljs.highlight(source, { language: lang }).value;
    } catch {
      return hljs.highlightAuto(source).value;
    }
  }, [source]);

  return (
    <pre className="json-hl">
      <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  );
}

const SETTINGS_SECTION_COMMENTS: Record<string, string> = {
  version: "Config schema version",
  model: "Provider credentials and model names",
  serve: "Web UI host / port",
  policy: "Shell profile and safety",
  tools: "fetch_url, web_search, skills, hooks",
  loop: "Planning mode and budget limits",
  limits: "Runtime token / timeout caps",
  model_backend: "Active provider backend",
  workspace: "Resolved workspace path",
  deepseek_thinking: "DeepSeek thinking mode (disabled | enabled)",
  deepseek_reasoning_effort: "DeepSeek effort when thinking enabled (high | max)",
};

/** Fallback when disk config is unavailable — annotated JSON5 via json5 library. */
export function settingsToJson5Text(data: unknown): string {
  if (!data || typeof data !== "object") {
    return JSON5.stringify(data, null, 2);
  }
  const obj = data as Record<string, unknown>;
  const lines: string[] = ["{"];
  const keys = Object.keys(obj);
  keys.forEach((key, idx) => {
    const comment = SETTINGS_SECTION_COMMENTS[key];
    if (comment) {
      lines.push(`  // ${comment}`);
    }
    const block = JSON5.stringify(obj[key], null, 2);
    const indented = block
      .split("\n")
      .map((line, lineIdx) => (lineIdx === 0 ? line : `  ${line}`))
      .join("\n");
    const comma = idx < keys.length - 1 ? "," : "";
    lines.push(`  ${JSON5.stringify(key)}: ${indented}${comma}`);
  });
  lines.push("}");
  return lines.join("\n");
}
