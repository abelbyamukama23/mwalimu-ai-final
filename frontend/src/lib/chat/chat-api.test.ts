import { describe, expect, it } from "vitest";
import {
  mapSessionDetail,
  mapSessionList,
  parseSseBlock,
} from "@/lib/chat/chat-api";

describe("mapSessionList", () => {
  it("maps a backend list item to a session with an empty transcript", () => {
    const session = mapSessionList({
      id: "sess-1",
      title: "Biology",
      created_at: "2026-08-24T12:00:00Z",
      updated_at: "2026-08-24T12:00:00Z",
    });
    expect(session).toEqual({
      id: "sess-1",
      title: "Biology",
      createdAt: "2026-08-24T12:00:00Z",
      messages: [],
    });
  });
});

describe("mapSessionDetail", () => {
  it("maps a detail payload, keeping only user/assistant messages in order", () => {
    const detail = mapSessionDetail({
      id: "sess-1",
      title: "Biology",
      created_at: "2026-08-24T12:00:00Z",
      updated_at: "2026-08-24T12:00:00Z",
      messages: [
        { id: "m1", sequence: 0, role: "user", content: "Q", created_at: "t0" },
        { id: "m2", sequence: 1, role: "assistant", content: "A", created_at: "t1" },
        { id: "m3", sequence: 2, role: "system", content: "system", created_at: "t2" },
      ],
    });
    expect(detail.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(detail.messages[1].content).toBe("A");
    expect(detail.messages[1].citations).toBeUndefined();
  });

  it("maps assistant message citations when present", () => {
    const detail = mapSessionDetail({
      id: "sess-1",
      title: "Soil Science",
      created_at: "2026-08-24T12:00:00Z",
      updated_at: "2026-08-24T12:00:00Z",
      messages: [
        { id: "m1", sequence: 0, role: "user", content: "Explain erosion", created_at: "t0" },
        {
          id: "m2",
          sequence: 1,
          role: "assistant",
          content: "Erosion is runoff.",
          created_at: "t1",
          citations: [
            {
              resource_id: "res-1",
              resource_name: "Soil Notes.pdf",
              library_id: "lib-1",
              library_name: "Amina Notes",
              section: "Section 4.2",
            },
          ],
        },
      ],
    });

    expect(detail.messages[1].citations).toBeDefined();
    expect(detail.messages[1].citations?.length).toBe(1);
    expect(detail.messages[1].citations?.[0].resource_name).toBe("Soil Notes.pdf");
    expect(detail.messages[1].citations?.[0].section).toBe("Section 4.2");
  });
});

describe("parseSseBlock", () => {
  it("parses an event and data payload", () => {
    const block = 'event: run.completed\ndata: {"status":"completed"}';
    expect(parseSseBlock(block)).toEqual({
      event: "run.completed",
      data: '{"status":"completed"}',
    });
  });
  it("returns null for keep-alive comment blocks", () => {
    expect(parseSseBlock(": keep-alive")).toBeNull();
  });
  it("joins multi-line data payloads", () => {
    const block = "event: run.completed\ndata: line1\ndata: line2";
    expect(parseSseBlock(block)?.data).toBe("line1\nline2");
  });
  it("parses run.completed with citation payload", () => {
    const jsonStr = JSON.stringify({
      status: "completed",
      citations: [
        {
          resource_id: "res-1",
          resource_name: "Notes.pdf",
          title: "Notes.pdf",
          library_id: "lib-1",
          library_name: "Amina Notes",
        },
      ],
    });
    const block = `event: run.completed\ndata: ${jsonStr}`;
    const parsed = parseSseBlock(block);
    expect(parsed?.event).toBe("run.completed");
    const data = JSON.parse(parsed!.data);
    expect(data.citations).toHaveLength(1);
    expect(data.citations[0].resource_name).toBe("Notes.pdf");
  });
});
