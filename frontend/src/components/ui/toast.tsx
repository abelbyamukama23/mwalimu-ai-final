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

type ToastItem = { id: number; message: string; icon?: ReactNode };

const ToastContext = createContext<{ toast: (message: string, icon?: ReactNode) => void } | null>(
  null,
);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx.toast;
}

/**
 * Standardized toast: bottom-center, dark stone pill, icon + message, ~3s.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const toast = useCallback((message: string, icon?: ReactNode) => {
    const id = nextId.current++;
    setToasts((items) => [...items.slice(-2), { id, message, icon }]);
    setTimeout(() => {
      setToasts((items) => items.filter((t) => t.id !== id));
    }, 3000);
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
              "flex animate-rise-in items-center gap-2 rounded-full bg-console-bg px-4 py-2.5",
              "text-13 font-medium text-stone-50 shadow-overlay",
            )}
          >
            {t.icon}
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
