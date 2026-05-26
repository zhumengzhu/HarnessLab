import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { highlightMarkdownCode } from "./markdownLanguages";

type MarkdownViewProps = {
  markdown: string;
  className?: string;
};

type CodeProps = ComponentPropsWithoutRef<"code"> & {
  node?: unknown;
};

function MarkdownCode({ className, children, ...props }: CodeProps) {
  const match = /language-([\w+-]+)/.exec(className ?? "");
  const code = String(children ?? "").replace(/\n$/, "");
  const isBlock = Boolean(match) || code.includes("\n");

  if (isBlock) {
    const html = highlightMarkdownCode(code, match?.[1] ?? null);
    return <code className="hljs" dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return (
    <code className={`md-inline-code${className ? ` ${className}` : ""}`} {...props}>
      {children}
    </code>
  );
}

export function MarkdownView({ markdown, className }: MarkdownViewProps) {
  if (!markdown.trim()) return null;

  return (
    <div className={className ? `markdown-view ${className}` : "markdown-view"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <pre className="md-code-block">{children}</pre>,
          code: MarkdownCode,
          a: ({ href, children, ...props }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
              {children}
            </a>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
