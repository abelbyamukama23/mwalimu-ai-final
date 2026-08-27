/**
 * Real chat data layer for the Mwalimu Platform API + Agent Service.
 *
 * This replaces the frontend-first mock layer. Every function talks to the
 * Platform API (control plane) with the existing authenticated client
 * (Authorization: Bearer <access>). Message submission dispatches a real Agent
 * Service run and consumes the Domain-S SSE stream (fetch + ReadableStream, since
 * native EventSource cannot attach the required Authorization header).
 *
 * The frontend NEVER holds Agent Service / internal credentials: it only uses (a)
 * the user's access token against the Platform API and (b) the short-lived stream
 * capability ticket returned by the Platform API for the specific run.
 */

import {
  ApiError,
  apiFetch,
  type Paginated,
} from "@/lib/api/client";

// ---------------------------------------------------------------------------
// Frontend-facing types
// ---------------------------------------------------------------------------

export type ChatRole = "user" | "assistant";

export type Citation = {
  resource_id: string;
  resource_name?: string;
  title?: string;
  library_id: string;
  library_name?: string;
  page_start?: number | null;
  page_end?: number | null;
  section?: string | null;
  sequence?: number;
  char_start?: number;
  char_end?: number;
  content_sha256?: string;
  chunk_id?: string | null;
  score?: number | null;
};

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  citations?: Citation[];
};

export type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
  messages: ChatMessage[];
};

// ---------------------------------------------------------------------------
// Backend wire shapes
// ---------------------------------------------------------------------------

type RawMessage = {
  id: string;
  sequence: number;
  role: string;
  content: string;
  created_at: string;
  citations?: Citation[];
};

type RawSessionListItem = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type RawSessionDetail = RawSessionListItem & {
  messages: RawMessage[];
};

type CreateRunResult = {
  id: string;
  session_id: string;
  status: string;
  streaming?: {
    sse_url: string;
    ticket: string;
    expires_in: number;
  };
};

// ---------------------------------------------------------------------------
// Pure mapping helpers (exported for unit tests)
// ---------------------------------------------------------------------------

export function mapSessionList(item: RawSessionListItem): ChatSession {
  return {
    id: item.id,
    title: item.title,
    createdAt: item.created_at,
    messages: [],
  };
}

export function mapSessionDetail(detail: RawSessionDetail): ChatSession {
  return {
    id: detail.id,
    title: detail.title,
    createdAt: detail.created_at,
    messages: detail.messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({
        id: m.id,
        role: m.role as ChatRole,
        content: m.content,
        createdAt: m.created_at,
        citations: Array.isArray(m.citations) && m.citations.length > 0 ? m.citations : undefined,
      })),
  };
}

const TERMINAL_EVENTS = new Set([
  "run.completed",
  "run.failed",
  "run.cancelled",
  "run.timed_out",
]);

/**
 * Parse one SSE block (between blank lines) into {event, data}.
 * Returns null for heart-beat/keep-alive comment blocks.
 */
export function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue; // SSE comment / keep-alive
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

/** Consume a Domain-S SSE stream, forwarding deltas and citations, until a terminal event. */
async function consumeSse(
  url: string,
  ticket: string,
  onDelta?: (text: string) => void,
  onCitations?: (citations: Citation[]) => void,
): Promise<void> {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${ticket}` },
  });
  if (!response.ok || !response.body) {
    throw new ApiError(
      response.status,
      response.status === 401
        ? "The stream authorization expired. Please try again."
        : `The response stream could not be opened (${response.status}).`,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx = buffer.indexOf("\n\n");
      while (idx !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const parsed = parseSseBlock(block);
        if (parsed) {
          if (parsed.event === "run.delta") {
            try {
              const data = JSON.parse(parsed.data) as { delta?: string };
              if (onDelta && typeof data.delta === "string") onDelta(data.delta);
            } catch {
              /* ignore malformed delta payloads */
            }
          } else if (parsed.event === "run.completed") {
            try {
              const data = JSON.parse(parsed.data) as { citations?: Citation[] };
              if (onCitations && Array.isArray(data.citations) && data.citations.length > 0) {
                onCitations(data.citations);
              }
            } catch {
              /* ignore malformed completion payload */
            }
          }
          if (TERMINAL_EVENTS.has(parsed.event)) return;
        }
        idx = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

async function pollRunUntilTerminal(runId: string): Promise<void> {
  for (let i = 0; i < 60; i += 1) {
    const run = await apiFetch<{ status: string }>(`/api/v1/runs/${runId}/`);
    if (["completed", "failed", "cancelled", "timed_out"].includes(run.status)) {
      return;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

/**
 * Wait until the run's assistant message has been persisted to the transcript.
 *
 * The SSE terminal event fires before the Agent Service's completion callback
 * (Domain D) writes the answer into the session, so immediately fetching the
 * session can still return only the user message. Poll briefly so the response
 * is visible without forcing a manual reload.
 */
async function waitForAssistantMessage(sessionId: string): Promise<void> {
  for (let i = 0; i < 30; i += 1) {
    const session = await apiGetSession(sessionId).catch(() => null);
    if (session && session.messages.some((m) => m.role === "assistant")) {
      return;
    }
    await new Promise((r) => setTimeout(r, 400));
  }
}

/** Dispatch a prompt as a run, streaming deltas, and wait for the result. */
async function sendMessageAndStream(
  sessionId: string,
  prompt: string,
  onDelta?: (text: string) => void,
  scope?: string,
  onCitations?: (citations: Citation[]) => void,
): Promise<void> {
  const run = await apiFetch<CreateRunResult>(
    `/api/v1/sessions/${sessionId}/runs/`,
    {
      method: "POST",
      body: {
        prompt,
        tool_allowlist: ["knowledge_search", "calculator"],
        knowledge_scope: scope ?? "relevant",
      },
    },
  );

  if (run.streaming?.sse_url && run.streaming?.ticket) {
    // Use the browser-side SSE transport: fetch cannot send a custom header
    // through native EventSource, so we stream via ReadableStream.
    await consumeSse(run.streaming.sse_url, run.streaming.ticket, onDelta, onCitations);
  } else {
    await pollRunUntilTerminal(run.id);
  }
  await waitForAssistantMessage(sessionId);
}

// ---------------------------------------------------------------------------
// Public API — mirrors the previous mock-chat.ts signatures
// ---------------------------------------------------------------------------

/** List the authenticated user's sessions (persisted), newest first. */
export async function apiListSessions(): Promise<ChatSession[]> {
  const all: RawSessionListItem[] = [];
  let page = 1;
  for (;;) {
    const data = await apiFetch<Paginated<RawSessionListItem>>(
      `/api/v1/sessions/?page=${page}`,
    );
    all.push(...data.results);
    if (!data.next) break;
    page += 1;
  }
  return all.map(mapSessionList);
}

/** Create a session only (no run). The caller dispatches the first prompt. */
export async function apiCreateSession(message: string): Promise<ChatSession> {
  const title = message.trim().slice(0, 60) || "New chat";
  const created = await apiFetch<RawSessionListItem>("/api/v1/sessions/", {
    method: "POST",
    body: { title },
  });
  return mapSessionList(created);
}

/** Retrieve a session (with its transcript) or null if it does not exist. */
export async function apiGetSession(id: string): Promise<ChatSession | null> {
  try {
    const data = await apiFetch<RawSessionDetail>(`/api/v1/sessions/${id}/`);
    return mapSessionDetail(data);
  } catch (err) {
    if (err instanceof Error && "status" in err && (err as ApiError).status === 404) {
      return null;
    }
    throw err;
  }
}

/** Send a message in an existing session (streaming deltas); returns the session. */
export async function apiSendMessage(
  sessionId: string,
  content: string,
  onDelta?: (text: string) => void,
  scope?: string,
  onCitations?: (citations: Citation[]) => void,
): Promise<ChatSession> {
  await sendMessageAndStream(sessionId, content.trim(), onDelta, scope, onCitations);
  const data = await apiFetch<RawSessionDetail>(`/api/v1/sessions/${sessionId}/`);
  return mapSessionDetail(data);
}

/** Rename or archive/unarchive a conversation. Returns the updated summary. */
export async function apiUpdateSession(
  sessionId: string,
  patch: { title?: string; status?: "active" | "archived" },
): Promise<ChatSession> {
  const data = await apiFetch<RawSessionListItem>(`/api/v1/sessions/${sessionId}/`, {
    method: "PATCH",
    body: patch,
  });
  return mapSessionList(data);
}

/** Permanently delete a conversation and its transcript. */
export async function apiDeleteSession(sessionId: string): Promise<void> {
  await apiFetch(`/api/v1/sessions/${sessionId}/`, { method: "DELETE" });
}
