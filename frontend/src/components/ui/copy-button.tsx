"use client";

import { Check, Copy } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

/** Copy text to the clipboard with a fallback for restricted contexts. */
async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to legacy path */
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "0";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

/** Icon-only copy button with a transient "copied" confirmation. */
export function CopyButton({
  text,
  className,
  label = "message",
}: {
  text: string;
  className?: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const onCopy = async () => {
    const ok = await copyToClipboard(text);
    if (!ok) return;
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1600);
  };

  return (
    <button
      type="button"
      aria-label={copied ? "Copied" : `Copy ${label}`}
      title={copied ? "Copied" : "Copy"}
      onClick={onCopy}
      className={cn(
        "focus-ring inline-flex size-6 shrink-0 items-center justify-center rounded-sm text-ink-tertiary transition-colors hover:bg-subtle hover:text-ink",
        className,
      )}
    >
      {copied ? (
        <Check size={14} weight="bold" className="text-success-fg" />
      ) : (
        <Copy size={14} weight="duotone" />
      )}
    </button>
  );
}

