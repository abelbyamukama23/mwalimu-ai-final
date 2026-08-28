"use client";

import { ArrowUp01Icon, StopIcon } from "hugeicons-react";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  type KeyboardEvent,
} from "react";
import { AttachmentMenu } from "@/components/chat/attachment-menu";
import {
  KnowledgeScopePopover,
  type KnowledgeScope,
} from "@/components/chat/knowledge-scope-popover";
import { cn } from "@/lib/utils";

const MAX_HEIGHT = 200;

export type ComposerHandle = { setValue: (value: string) => void; focus: () => void };

/**
 * Polished auto-growing composer.
 * Enter sends, Shift+Enter inserts a newline, send is disabled while empty,
 * and morphs into Stop while a run executes.
 */
export const Composer = forwardRef<
  ComposerHandle,
  {
    value: string;
    onChange: (value: string) => void;
    onSubmit: (value: string) => void;
    onStop?: () => void;
    running?: boolean;
    placeholder?: string;
    scope: KnowledgeScope;
    onScopeChange: (scope: KnowledgeScope) => void;
    autoFocus?: boolean;
  }
>(function Composer(
  {
    value,
    onChange,
    onSubmit,
    onStop,
    running = false,
    placeholder = "Ask Mwalimu anything…",
    scope,
    onScopeChange,
    autoFocus = true,
  },
  ref,
) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, []);

  useEffect(() => {
    resize();
  }, [value, resize]);

  useImperativeHandle(
    ref,
    () => ({
      setValue: (val: string) => {
        onChange(val);
      },
      focus: () => {
        textareaRef.current?.focus();
      },
    }),
    [onChange],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) onSubmit(value.trim());
    }
  };

  const canSend = value.trim().length > 0 && !running;

  return (
    <div
      className={cn(
        "w-full rounded-xl border border-border bg-surface px-4 pb-3 pt-3.5 shadow-composer",
        "transition-shadow duration-150 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15",
      )}
    >
      <div className="flex items-end">
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label="Message Mwalimu"
          autoFocus={autoFocus}
          className="max-h-[200px] w-full flex-1 resize-none bg-transparent text-15 leading-relaxed text-ink outline-none placeholder:text-ink-tertiary"
        />
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <AttachmentMenu />
        <div className="flex items-center gap-2">
          <KnowledgeScopePopover scope={scope} onScopeChange={onScopeChange} />
          {running ? (
          <button
            onClick={onStop}
            aria-label="Stop generating"
            className="focus-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-colors duration-150 hover:bg-accent-hover"
          >
            <StopIcon size={16} aria-hidden />
          </button>
        ) : (
          <button
            onClick={() => canSend && onSubmit(value.trim())}
            disabled={!canSend}
            aria-label="Send message"
            className={cn(
              "focus-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors duration-150",
              canSend
                ? "bg-accent text-white hover:bg-accent-hover"
                : "cursor-not-allowed bg-subtle text-ink-tertiary",
            )}
          >
            <ArrowUp01Icon size={18} aria-hidden />
          </button>
        )}
        </div>
      </div>
    </div>
  );
});

