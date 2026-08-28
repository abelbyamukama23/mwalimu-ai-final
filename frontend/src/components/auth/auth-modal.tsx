"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Cancel01Icon } from "hugeicons-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AuthPanel, type AuthInitialView } from "@/components/auth/auth-panel";
import { DialogContent } from "@/components/ui/dialog";
import { IconButton } from "@/components/ui/icon-button";

export type AuthModalConfig = {
  initialView?: AuthInitialView;
  initialEmail?: string;
};

type AuthModalContextValue = {
  openAuthModal: (config?: AuthModalConfig) => void;
  closeAuthModal: () => void;
};

const AuthModalContext = createContext<AuthModalContextValue | null>(null);

export function useAuthModal() {
  const ctx = useContext(AuthModalContext);
  if (!ctx) throw new Error("useAuthModal must be used within AuthModalProvider");
  return ctx;
}

/**
 * App-wide auth modal. Renders the SAME reusable AuthPanel used on /login, with
 * a Radix Dialog providing the backdrop, ESC close, focus trap, and focus
 * restoration. Open from any surface via `useAuthModal().openAuthModal()`.
 */
export function AuthModalProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthModalConfig | null>(null);
  const open = config !== null;

  const openAuthModal = useCallback((next?: AuthModalConfig) => setConfig(next ?? {}), []);
  const closeAuthModal = useCallback(() => setConfig(null), []);

  const value = useMemo(
    () => ({ openAuthModal, closeAuthModal }),
    [openAuthModal, closeAuthModal],
  );

  return (
    <AuthModalContext.Provider value={value}>
      {children}
      <DialogPrimitive.Root
        open={open}
        onOpenChange={(next) => {
          if (!next) closeAuthModal();
        }}
      >
        {open ? (
          <DialogContent className="w-[min(460px,calc(100vw-2rem))] border-0 shadow-overlay">
            <DialogPrimitive.Close asChild>
              <IconButton
                aria-label="Close authentication"
                size="sm"
                className="absolute right-3.5 top-3.5 z-10"
              >
                <Cancel01Icon size={16} />
              </IconButton>
            </DialogPrimitive.Close>
            <AuthPanel
              mode="modal"
              initialView={config.initialView}
              initialEmail={config.initialEmail}
              onSuccess={closeAuthModal}
            />
          </DialogContent>
        ) : null}
      </DialogPrimitive.Root>
    </AuthModalContext.Provider>
  );
}
