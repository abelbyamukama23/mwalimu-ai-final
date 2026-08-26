import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GroundingIndicator } from "@/components/chat/grounding-indicator";
import type { Citation } from "@/lib/chat/chat-api";

describe("GroundingIndicator", () => {
  it("renders empty string when citations is undefined or empty", () => {
    const html1 = renderToStaticMarkup(createElement(GroundingIndicator));
    expect(html1).toBe("");

    const html2 = renderToStaticMarkup(createElement(GroundingIndicator, { citations: [] }));
    expect(html2).toBe("");
  });

  it("renders single-source grounding label when 1 citation is present", () => {
    const citations: Citation[] = [
      {
        resource_id: "res-1",
        resource_name: "Notes.pdf",
        library_id: "lib-1",
      },
    ];

    const html = renderToStaticMarkup(createElement(GroundingIndicator, { citations }));
    expect(html).toContain("Grounded in your study notes");
  });

  it("renders multi-source grounding label when multiple citations are present", () => {
    const citations: Citation[] = [
      { resource_id: "res-1", resource_name: "Doc1.pdf", library_id: "lib-1" },
      { resource_id: "res-2", resource_name: "Doc2.pdf", library_id: "lib-2" },
    ];

    const html = renderToStaticMarkup(createElement(GroundingIndicator, { citations }));
    expect(html).toContain("Grounded in 2 study resources");
  });
});
