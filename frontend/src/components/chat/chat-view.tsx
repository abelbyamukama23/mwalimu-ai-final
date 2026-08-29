"use client";

import Link from "next/link";
import { BubbleChatIcon } from "hugeicons-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { CitationChips } from "@/components/chat/citations";
import { Composer, type ComposerHandle } from "@/components/chat/composer";
import { GroundingIndicator } from "@/components/chat/grounding-indicator";
import type { KnowledgeScope } from "@/components/chat/knowledge-scope-popover";
import { MarkdownContent } from "@/components/chat/markdown";
import { SuggestionChips } from "@/components/chat/suggestion-chips";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
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
  const isUser = role === "user";
  return (
    <div
      className={cn(
        "group flex flex-col",
        isUser ? "items-end" : "items-start",
      )}
    >
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-md bg-subtle px-4 py-2.5 text-14 leading-relaxed text-ink"
            : "max-w-[92%] overflow-hidden"
        }
      >
        {isUser ? (
          content
        ) : (
          <div>
            <GroundingIndicator citations={citations} />
            <MarkdownContent content={content} />
            <CitationChips citations={citations} />
          </div>
        )}
      </div>
      <CopyButton
        text={content}
        label={isUser ? "message" : "response"}
        className="mt-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
      />
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
    <div className="group flex flex-col items-start">
      <div className="max-w-[92%] overflow-hidden">
        <GroundingIndicator citations={citations} />
        <MarkdownContent content={content} />
        <span
          aria-hidden
          className="ml-0.5 inline-block h-4 w-0.5 animate-pulse rounded-full bg-accent align-text-bottom"
        />
        <CitationChips citations={citations} />
      </div>
      <CopyButton
        text={content}
        label="response"
        className="mt-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
      />
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
          icon={BubbleChatIcon}
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

  const transcriptRef = useRef<HTMLDivElement>(null);
  const bottomAnchorRef = useRef<HTMLDivElement>(null);
  const [isScrolledUp, setIsScrolledUp] = useState(false);
  const userScrolledUpRef = useRef(false);

  const scrollToBottom = useCallback((smooth = true) => {
    if (bottomAnchorRef.current) {
      bottomAnchorRef.current.scrollIntoView({
        behavior: smooth ? "smooth" : "auto",
        block: "end",
      });
    }
  }, []);

  const handleScroll = useCallback(() => {
    if (!transcriptRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = transcriptRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    const scrolledUp = distanceFromBottom > 120;
    setIsScrolledUp(scrolledUp);
    userScrolledUpRef.current = scrolledUp;
  }, []);

  // Scroll on new user message or streaming tokens unless user intentionally scrolled up
  useEffect(() => {
    if (!userScrolledUpRef.current) {
      scrollToBottom(true);
    }
  }, [pendingUser, liveText, session?.messages, scrollToBottom]);

  // Initial scroll on mount
  useEffect(() => {
    if (session?.messages && session.messages.length > 0) {
      scrollToBottom(false);
    }
  }, [sessionId, scrollToBottom]);

  const showSuggestions = session.messages.length === 0 && !isBusy && pendingUser === null;

  return (
    <div className="relative flex h-full flex-col">
      {/* Transcript — continuous canvas, scrolls to the top of the viewport. */}
      <div
        ref={transcriptRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-y-auto px-6 pb-6 pt-6 md:px-12 md:pt-8 scroll-smooth"
      >
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
              {pendingUser && (
                <Bubble key="__streaming_user__" role="user" content={pendingUser} />
              )}
              <StreamingBubble
                key="__streaming_assistant__"
                content={liveText}
                citations={liveCitations}
              />
            </>
          )}

          {/* Dedicated bottom scroll anchor */}
          <div ref={bottomAnchorRef} className="h-2 shrink-0" aria-hidden />
        </div>
      </div>

      {/* Floating Scroll to Bottom button */}
      {isScrolledUp && (
        <button
          type="button"
          onClick={() => {
            userScrolledUpRef.current = false;
            setIsScrolledUp(false);
            scrollToBottom(true);
          }}
          aria-label="Scroll to latest message"
          className="focus-ring absolute bottom-28 left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full bg-surface border border-border px-3 py-1.5 text-12 font-medium text-ink shadow-md transition-all hover:bg-surface-elevated active:scale-95"
        >
          <span>Scroll to latest</span>
          <span className="text-accent text-14">↓</span>
        </button>
      )}

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

