import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CitationChips } from "@/components/chat/citations";
import type { Citation } from "@/lib/chat/chat-api";

describe("CitationChips", () => {
  it("renders empty string when citations is undefined or empty (honest absence)", () => {
    const html1 = renderToStaticMarkup(createElement(CitationChips));
    expect(html1).toBe("");

    const html2 = renderToStaticMarkup(createElement(CitationChips, { citations: [] }));
    expect(html2).toBe("");
  });

  it("renders citation chips with resource title and section", () => {
    const citations: Citation[] = [
      {
        resource_id: "res-1",
        resource_name: "Soil Conservation Notes.pdf",
        library_id: "lib-1",
        library_name: "Amina's Agriculture Notes",
        section: "Section 4.2",
        score: 0.95,
      },
    ];

    const html = renderToStaticMarkup(createElement(CitationChips, { citations }));

    expect(html).toContain("Grounded in Sources");
    expect(html).toContain("Soil Conservation Notes.pdf");
    expect(html).toContain("· Section 4.2");
  });

  it("normalizes title using title fallback if resource_name is missing", () => {
    const citations: Citation[] = [
      {
        resource_id: "res-2",
        title: "Biology Study Guide.pdf",
        library_id: "lib-2",
        library_name: "Form 3 Notes",
        page_start: 12,
        page_end: 14,
      },
    ];

    const html = renderToStaticMarkup(createElement(CitationChips, { citations }));

    expect(html).toContain("Biology Study Guide.pdf");
    expect(html).toContain("· pp. 12–14");
  });
});
