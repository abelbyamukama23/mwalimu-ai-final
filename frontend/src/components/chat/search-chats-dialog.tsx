"use client";

import { useRouter } from "next/navigation";
import { MessageSquare, Search, SearchX } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
} from "@/components/ui/dialog";
import type { ChatSession } from "@/lib/chat/chat-api";

/**
 * Centered search modal over conversation history. Radix Dialog provides
 * ESC-to-close, focus trap, and scrim; the input is focused on open.
 * Filters by title or message content (case-insensitive) and navigates on
 * selection.
 */
export function SearchChatsDialog({
  open,
  onOpenChange,
  sessions,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessions: ChatSession[];
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const q = query.trim().toLowerCase();

  const results = useMemo(() => {
    if (!q) return sessions;
    return sessions.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.messages.some((m) => m.content.toLowerCase().includes(q)),
    );
  }, [q, sessions]);

  const handleOpenChange = (o: boolean) => {
    onOpenChange(o);
    if (!o) setQuery("");
  };

  const openConversation = (id: string) => {
    setQuery("");
    onOpenChange(false);
    router.push(`/chat/${id}`);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-[min(560px,calc(100vw-2rem))]">
        <DialogHeader
          title="Search chats"
          description="Find a conversation in your history."
          onClose={() => onOpenChange(false)}
        />

        <div className="relative mb-3">
          <Search
            size={15}
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-tertiary"
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations"
            aria-label="Search conversations"
            autoFocus
            className="pl-9"
          />
        </div>

        <p className="mb-1 px-1 text-11 font-medium tracking-wide text-ink-tertiary">
          {q ? "RESULTS" : "RECENT"}
        </p>

        {results.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No conversations found"
            body="Try a different keyword."
          />
        ) : (
          <ul className="space-y-0.5">
            {results.map((session) => (
              <li key={session.id}>
                <button
                  onClick={() => openConversation(session.id)}
                  className="focus-ring flex w-full items-start gap-2.5 rounded-sm px-2 py-2 text-left transition-colors duration-150 hover:bg-subtle"
                >
                  <MessageSquare
                    size={15}
                    aria-hidden
                    className="mt-0.5 shrink-0 text-ink-tertiary"
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-13 font-medium text-ink">
                      {session.title}
                    </span>
                    <span className="block truncate text-12 text-ink-tertiary">
                      {session.messages[0]?.content ?? ""}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
