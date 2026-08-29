"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

type ToastTone = "default" | "success" | "error";

type ToastItem = {
  id: number;
  message: string;
  icon?: ReactNode;
  tone: ToastTone;
};

type ToastFn = (
  message: string,
  optionsOrIcon?: ReactNode | { icon?: ReactNode; tone?: ToastTone },
) => void;

const ToastContext = createContext<{ toast: ToastFn } | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx.toast;
}

function inferTone(message: string): ToastTone {
  const lower = message.toLowerCase();
  if (
    lower.includes("failed") ||
    lower.includes("error") ||
    lower.includes("cannot") ||
    lower.includes("invalid") ||
    lower.includes("deleted")
  ) {
    return "error";
  }
  if (
    lower.includes("success") ||
    lower.includes("updated") ||
    lower.includes("saved") ||
    lower.includes("created") ||
    lower.includes("enabled") ||
    lower.includes("archived") ||
    lower.includes("verified")
  ) {
    return "success";
  }
  return "default";
}

/**
 * Standardized toast: bottom-center, tone-aware pill with icons, ~3.5s.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const toast: ToastFn = useCallback((message, optionsOrIcon) => {
    const id = nextId.current++;
    let icon: ReactNode | undefined;
    let tone: ToastTone = inferTone(message);

    if (
      optionsOrIcon &&
      typeof optionsOrIcon === "object" &&
      !("props" in optionsOrIcon) &&
      !("$$typeof" in optionsOrIcon)
    ) {
      const opts = optionsOrIcon as { icon?: ReactNode; tone?: ToastTone };
      if (opts.icon) icon = opts.icon;
      if (opts.tone) tone = opts.tone;
    } else if (optionsOrIcon) {
      icon = optionsOrIcon as ReactNode;
    }

    setToasts((items) => [...items.slice(-2), { id, message, icon, tone }]);
    setTimeout(() => {
      setToasts((items) => items.filter((t) => t.id !== id));
    }, 3500);
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-6 left-1/2 z-[100] flex -translate-x-1/2 flex-col items-center gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "flex animate-rise-in items-center gap-2 rounded-full px-4 py-2.5 text-13 font-medium shadow-overlay transition-all",
              t.tone === "success" &&
                "border border-emerald-600 bg-emerald-800 text-white shadow-emerald-950/20",
              t.tone === "error" &&
                "border border-red-600 bg-red-800 text-white shadow-red-950/20",
              t.tone === "default" &&
                "bg-console-bg text-stone-50 border border-stone-700",
            )}
          >
            {t.icon ? (
              t.icon
            ) : t.tone === "success" ? (
              <span className="text-emerald-300 font-bold" aria-hidden>✓</span>
            ) : t.tone === "error" ? (
              <span className="text-red-300 font-bold" aria-hidden>⚠</span>
            ) : null}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

