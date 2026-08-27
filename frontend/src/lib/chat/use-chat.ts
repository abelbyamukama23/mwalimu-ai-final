"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiCreateSession,
  apiDeleteSession,
  apiGetSession,
  apiListSessions,
  apiSendMessage,
  apiUpdateSession,
  type ChatSession,
} from "@/lib/chat/chat-api";

const SESSIONS_KEY = ["chat", "sessions"] as const;
const sessionKey = (id: string) => ["chat", "session", id] as const;

/** All persisted sessions for the authenticated user (Platform API). */
export function useSessions() {
  return useQuery({
    queryKey: SESSIONS_KEY,
    queryFn: apiListSessions,
  });
}

/** A single persisted session + its transcript. */
export function useSession(id: string | undefined) {
  return useQuery({
    queryKey: sessionKey(id ?? "none"),
    queryFn: () => apiGetSession(id ?? ""),
    enabled: Boolean(id),
  });
}

/** Create a session (no run); the caller dispatches the first prompt. */
export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (message: string) => apiCreateSession(message),
    onSuccess: (session) => {
      queryClient.setQueryData(sessionKey(session.id), session);
      queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
    },
  });
}

/** Send a real message (dispatch a run + stream deltas), updating the cached session. */
export function useSendMessage(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      content,
      onDelta,
      scope,
      onCitations,
    }: {
      content: string;
      onDelta?: (text: string) => void;
      scope?: string;
      onCitations?: (citations: import("@/lib/chat/chat-api").Citation[]) => void;
    }) => apiSendMessage(sessionId, content, onDelta, scope, onCitations),
    onSuccess: (session) => {
      queryClient.setQueryData(sessionKey(sessionId), session);
      queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
    },
  });
}

/** Rename a conversation — updates the cached list and invalidates its detail. */
export function useRenameSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, title }: { sessionId: string; title: string }) =>
      apiUpdateSession(sessionId, { title }),
    onSuccess: (updated) => {
      queryClient.setQueryData<ChatSession[]>(SESSIONS_KEY, (old) =>
        old
          ? old.map((s) => (s.id === updated.id ? { ...s, title: updated.title } : s))
          : old,
      );
      queryClient.invalidateQueries({ queryKey: sessionKey(updated.id) });
    },
  });
}

/** Archive a conversation — hides it from the recent list. */
export function useArchiveSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      apiUpdateSession(sessionId, { status: "archived" }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
      queryClient.removeQueries({ queryKey: sessionKey(updated.id) });
    },
  });
}

/** Permanently delete a conversation and its transcript. */
export function useDeleteSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => apiDeleteSession(sessionId),
    onSuccess: (_result, sessionId) => {
      queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
      queryClient.removeQueries({ queryKey: sessionKey(sessionId) });
    },
  });
}

export type { ChatSession };
