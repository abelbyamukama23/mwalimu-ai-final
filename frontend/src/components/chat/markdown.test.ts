import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MarkdownContent } from "./markdown";

const FIXTURE = `# Title

## Heading 2

### Heading 3

A paragraph with **bold**, *italic*, \`inline code\`, and a [link](https://example.com).

1. First
2. Second
   - Nested bullet A

- Item A
- Item B

> a blockquote

---

\`\`\`bash
echo "hello"
\`\`\`

| Name | Type |
| --- | --- |
| Kazinga | Lake |`;

function render(content: string): string {
  return renderToStaticMarkup(createElement(MarkdownContent, { content }));
}

describe("MarkdownContent", () => {
  const html = render(FIXTURE);

  it("renders headings", () => {
    expect(html).toMatch(/<h1[^>]*>Title<\/h1>/);
    expect(html).toMatch(/<h2[^>]*>Heading 2<\/h2>/);
    expect(html).toMatch(/<h3[^>]*>Heading 3<\/h3>/);
  });

  it("renders bold and italic", () => {
    expect(html).toMatch(/<strong[^>]*>bold<\/strong>/);
    expect(html).toMatch(/<em[^>]*>italic<\/em>/);
  });

  it("renders inline code as a code element", () => {
    expect(html).toMatch(/<code[^>]*>inline code<\/code>/);
  });

  it("renders ordered and nested unordered lists", () => {
    expect(html).toMatch(/<ol\b/);
    expect(html).toMatch(/<ul\b/);
    expect(html).toMatch(/<li[^>]*>Nested bullet A<\/li>/);
  });

  it("renders blockquote, horizontal rule, table, code block and link", () => {
    expect(html).toMatch(/<blockquote\b/);
    expect(html).toMatch(/<hr\b/);
    expect(html).toMatch(/<table\b/);
    expect(html).toMatch(/<th[^>]*>Name<\/th>/);
    expect(html).toMatch(/<pre\b/);
    expect(html).toMatch(/<a href="https:\/\/example\.com"/);
  });

  it("renders external links safely", () => {
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("does not expose raw markdown control characters", () => {
    expect(html).not.toContain("**bold**");
    expect(html).not.toContain("## Heading 2");
    expect(html).not.toContain("```");
  });

  it("strips none-safe javascript links", () => {
    const unsafe = render("[x](javascript:alert(1))");
    expect(unsafe).not.toMatch(/href="javascript:/);
  });
});
