"use client";

import Link from "next/link";
import { MessageSquare } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { CitationChips } from "@/components/chat/citations";
import { Composer, type ComposerHandle } from "@/components/chat/composer";
import { GroundingIndicator } from "@/components/chat/grounding-indicator";
import type { KnowledgeScope } from "@/components/chat/knowledge-scope-popover";
import { MarkdownContent } from "@/components/chat/markdown";
import { SuggestionChips } from "@/components/chat/suggestion-chips";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import type { Citation } from "@/lib/chat/chat-api";
import { useSendMessage, useSession } from "@/lib/chat/use-chat";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "Explain a concept",
  "Create a lesson",
  "Help me revise",
  "Draft a lesson plan",
] as const;

function Bubble({
  role,
  content,
  citations,
}: {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}) {
  return (
    <div className={cn("flex", role === "user" ? "justify-end" : "justify-start")}>
      <div
        className={
          role === "user"
            ? "max-w-[85%] rounded-md bg-subtle px-4 py-2.5 text-14 leading-relaxed text-ink"
            : "max-w-[92%] overflow-hidden"
        }
      >
        {role === "user" ? (
          content
        ) : (
          <div>
            <GroundingIndicator citations={citations} />
            <MarkdownContent content={content} />
            <CitationChips citations={citations} />
          </div>
        )}
      </div>
    </div>
  );
}

/** Live streaming assistant bubble that blends with the canvas. */
function StreamingBubble({
  content,
  citations,
}: {
  content: string;
  citations?: Citation[];
}) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] overflow-hidden">
        <GroundingIndicator citations={citations} />
        <MarkdownContent content={content} />
        <span
          aria-hidden
          className="ml-0.5 inline-block h-4 w-0.5 animate-pulse rounded-full bg-accent align-text-bottom"
        />
        <CitationChips citations={citations} />
      </div>
    </div>
  );
}

/**
 * Conversation view. Renders a session transcript, streams assistant responses
 * token-by-token, and offers a composer to continue.
 */
export function ChatView({ sessionId }: { sessionId: string }) {
  const { data: session, isLoading } = useSession(sessionId);
  const sendMessage = useSendMessage(sessionId);

  const [value, setValue] = useState("");
  const [scope, setScope] = useState<KnowledgeScope>("relevant");
  const [streaming, setStreaming] = useState(false);
  const [liveText, setLiveText] = useState("");
  const [liveCitations, setLiveCitations] = useState<Citation[]>([]);
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const composerRef = useRef<ComposerHandle>(null);
  const dispatchedRef = useRef(false);

  const resetStreaming = useCallback(() => {
    setStreaming(false);
    setLiveText("");
    setLiveCitations([]);
    setPendingUser(null);
  }, []);

  const runSend = useCallback(
    (content: string, scope?: string) => {
      setPendingUser(content);
      setLiveText("");
      setLiveCitations([]);
      setStreaming(true);
      sendMessage.mutate(
        {
          content,
          scope,
          onDelta: (delta) => setLiveText((prev) => prev + delta),
          onCitations: (cits) => setLiveCitations(cits),
        },
        { onSettled: resetStreaming },
      );
    },
    [sendMessage, resetStreaming],
  );

  // Dispatch a just-created session's first prompt once the conversation mounts.
  useEffect(() => {
    if (!session || dispatchedRef.current) return;
    const raw = sessionStorage.getItem(`mwalimu.pending.${sessionId}`);
    if (!raw) return;
    const timer = window.setTimeout(() => {
      sessionStorage.removeItem(`mwalimu.pending.${sessionId}`);
      dispatchedRef.current = true;
      try {
        const pending = JSON.parse(raw) as { prompt: string; scope?: string };
        runSend(pending.prompt, pending.scope);
      } catch {
        runSend(raw);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [session, sessionId, runSend]);

  if (isLoading) {
    return (
      <div className="flex h-full flex-col gap-4 px-6 py-10 md:px-12">
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-6 w-4/5" />
        <Skeleton className="h-6 w-2/3" />
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <EmptyState
          icon={MessageSquare}
          title="Conversation not found"
          body="This conversation doesn’t exist or was cleared. Start a new one to continue."
          action={
            <Link href="/chat/new">
              <Button>New chat</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const isBusy = sendMessage.isPending;

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || isBusy) return;
    setValue("");
    runSend(trimmed, scope);
  };

  const showSuggestions = session.messages.length === 0 && !isBusy && pendingUser === null;

  return (
    <div className="flex h-full flex-col">
      {/* Transcript — continuous canvas, scrolls to the top of the viewport. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6 pt-6 md:px-12 md:pt-8">
        <div className="mx-auto flex max-w-[760px] flex-col gap-4">
          {session.messages.map((message) => (
            <Bubble
              key={message.id}
              role={message.role}
              content={message.content}
              citations={message.citations}
            />
          ))}

          {streaming && (
            <>
              {pendingUser && <Bubble role="user" content={pendingUser} />}
              <StreamingBubble content={liveText} citations={liveCitations} />
            </>
          )}
        </div>
      </div>

      {/* Floating composer — visually part of the conversation. */}
      <div className="shrink-0 px-6 pb-6 pt-2 md:px-12">
        <div className="mx-auto max-w-[760px]">
          <Composer
            ref={composerRef}
            value={value}
            onChange={setValue}
            onSubmit={handleSubmit}
            scope={scope}
            onScopeChange={setScope}
            running={isBusy}
          />
          {showSuggestions && (
            <div className="mt-3">
              <SuggestionChips
                suggestions={SUGGESTIONS}
                onSelect={(s) => {
                  composerRef.current?.setValue(s);
                  composerRef.current?.focus();
                }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
