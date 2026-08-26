"use client";

import { useRef, useState, type ReactNode } from "react";
import Markdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Mwalimu-safe Markdown renderer for assistant chat responses.
 *
 * - Renders Markdown to React elements (never raw HTML injection).
 * - `urlTransform` restricts links to safe protocols; all links open in a new
 *   tab with `noopener noreferrer`.
 * - Fenced code blocks and inline code get distinct, readable treatment.
 * - Works for incomplete/progressive content during generation — ReactMarkdown
 *   renders whatever is parsable without asserting a closed document.
 */

/** Code fence block with a copy affordance and horizontal scroll for long lines. */
function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement | null>(null);

  const copy = async () => {
    const text = preRef.current?.innerText ?? "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable — no-op */
    }
  };

  return (
    <div className="group relative my-3">
      <button
        type="button"
        aria-label="Copy code"
        onClick={copy}
        className="absolute right-2 top-2 z-10 rounded-md border border-border bg-surface/80 px-2 py-1 font-mono text-11 text-ink-secondary backdrop-blur-sm transition-colors hover:border-border-strong hover:text-ink focus-ring"
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <pre
        ref={preRef}
        className="overflow-x-auto rounded-md border border-border bg-subtle px-4 py-3 font-mono text-13 leading-relaxed text-ink"
        tabIndex={0}
      >
        {children}
      </pre>
    </div>
  );
}

/** Inline code chip versus block code (inside a code fence). */
function InlineCode({ className, children }: { className?: string; children?: ReactNode }) {
  const isBlock =
    typeof className === "string" && className.includes("language-");
  return (
    <code
      className={
        isBlock
          ? "font-mono text-13 leading-relaxed"
          : "rounded-md border border-border bg-subtle px-1.5 py-0.5 font-mono text-13 text-ink"
      }
    >
      {children}
    </code>
  );
}

const components: Components = {
  h1: ({ children }) => (
    <h1 className="mt-4 mb-2 text-22 font-semibold leading-tight text-ink">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-4 mb-2 text-17 font-semibold leading-tight text-ink">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-4 mb-1.5 text-15 font-semibold leading-tight text-ink">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mt-3 mb-1 text-14 font-semibold leading-tight text-ink">{children}</h4>
  ),
  h5: ({ children }) => (
    <h5 className="mt-3 mb-1 text-14 font-medium leading-tight text-ink">{children}</h5>
  ),
  h6: ({ children }) => (
    <h6 className="mt-3 mb-1 text-14 font-medium leading-tight text-ink-secondary">
      {children}
    </h6>
  ),
  p: ({ children }) => <p className="my-2.5 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-2.5 list-disc space-y-1 pl-5 marker:text-accent/60">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2.5 list-decimal space-y-1 pl-5 marker:text-accent/60">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-accent/40 bg-active/50 px-4 py-2 text-14 italic text-ink-secondary">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-t border-border" />,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline decoration-accent/40 underline-offset-2 transition-colors hover:text-accent-hover"
    >
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
  code: InlineCode,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-13">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr className="border-b border-border">{children}</tr>,
  th: ({ children }) => (
    <th className="border border-border bg-subtle px-2.5 py-1.5 text-left font-semibold text-ink">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-border px-2.5 py-1.5 align-top text-ink">{children}</td>
  ),
  del: ({ children }) => <del className="text-ink-tertiary">{children}</del>,
};

/**
 * Render assistant Markdown content with Mwalimu-native styling.
 * Wrapped in a plain text-free container so the message bubble controls padding.
 */
export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown-body text-14 leading-relaxed text-ink">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={components}
        urlTransform={defaultUrlTransform}
      >
        {content}
      </Markdown>
    </div>
  );
}
