"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Composer, type ComposerHandle } from "@/components/chat/composer";
import type { KnowledgeScope } from "@/components/chat/knowledge-scope-popover";
import { SuggestionChips } from "@/components/chat/suggestion-chips";
import { useCreateSession } from "@/lib/chat/use-chat";

const SUGGESTIONS = [
  "Explain a concept",
  "Create a lesson",
  "Search my libraries",
  "Analyze a document",
  "Help me revise",
] as const;

/**
 * New chat. Sending creates a session via the mock chat layer (frontend-first;
 * swap to the sessions API when it lands) and navigates to the conversation.
 */
export default function NewChatPage() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<KnowledgeScope>("relevant");
  const composerRef = useRef<ComposerHandle>(null);
  const createSession = useCreateSession();

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || createSession.isPending) return;
    createSession.mutate(trimmed, {
      onSuccess: (session) => {
        // Stash the prompt + knowledge scope so the conversation view can dispatch it.
        sessionStorage.setItem(
          `mwalimu.pending.${session.id}`,
          JSON.stringify({ prompt: trimmed, scope }),
        );
        router.push(`/chat/${session.id}`);
      },
    });
  };

  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-10">
      <div className="w-full max-w-[680px] animate-rise-in">
        <h1 className="mb-6 text-center text-28 font-semibold text-ink">
          How can Mwalimu help you today?
        </h1>

        <Composer
          ref={composerRef}
          value={value}
          onChange={setValue}
          onSubmit={handleSubmit}
          scope={scope}
          onScopeChange={setScope}
          running={createSession.isPending}
        />

        <div className="mt-5">
          <SuggestionChips
            suggestions={SUGGESTIONS}
            onSelect={(s) => {
              composerRef.current?.setValue(s);
              composerRef.current?.focus();
            }}
          />
        </div>
      </div>
    </div>
  );
}
