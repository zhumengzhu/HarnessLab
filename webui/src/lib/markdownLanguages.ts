import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import css from "highlight.js/lib/languages/css";
import go from "highlight.js/lib/languages/go";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import python from "highlight.js/lib/languages/python";
import rust from "highlight.js/lib/languages/rust";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";

const REGISTERED = new Set<string>();

export function highlightMarkdownCode(source: string, language: string | null): string {
  registerMarkdownLanguages();
  const lang = language?.trim().toLowerCase() ?? "";
  const aliases: Record<string, string> = {
    sh: "bash",
    shell: "bash",
    zsh: "bash",
    py: "python",
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    yml: "yaml",
    html: "xml",
    htm: "xml",
  };
  const resolved = aliases[lang] ?? lang;
  try {
    if (resolved && hljs.getLanguage(resolved)) {
      return hljs.highlight(source, { language: resolved }).value;
    }
    return hljs.highlightAuto(source).value;
  } catch {
    return hljs.highlightAuto(source).value;
  }
}

function registerMarkdownLanguages() {
  const pairs: Array<[string, typeof python]> = [
    ["bash", bash],
    ["css", css],
    ["go", go],
    ["java", java],
    ["javascript", javascript],
    ["json", json],
    ["markdown", markdown],
    ["python", python],
    ["rust", rust],
    ["sql", sql],
    ["typescript", typescript],
    ["xml", xml],
    ["yaml", yaml],
  ];
  for (const [name, mod] of pairs) {
    if (!REGISTERED.has(name)) {
      hljs.registerLanguage(name, mod);
      REGISTERED.add(name);
    }
  }
}
