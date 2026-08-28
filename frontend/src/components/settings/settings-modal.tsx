"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { MagnifyingGlass, X } from "@phosphor-icons/react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  SETTINGS_SECTIONS,
  type SettingsSection,
} from "@/lib/settings-sections";
import { cn } from "@/lib/utils";
import { AppearanceSection } from "./sections/appearance-section";
import { ConnectedAccountsSection } from "./sections/connected-accounts-section";
import { FamiliarRegionsSection } from "./sections/familiar-regions-section";
import { GeneralSection } from "./sections/general-section";
import { InstitutionSection } from "./sections/institution-section";
import { LanguageSection } from "./sections/language-section";
import { LearningSection } from "./sections/learning-section";
import { PrivacySection } from "./sections/privacy-section";
import { VoiceSection } from "./sections/voice-section";

/** The eight canonical Settings sections (conversation-first, secondary config). */
const CORE_IDS = [
  "general",
  "learning",
  "language",
  "voice",
  "notifications",
  "appearance",
  "privacy",
  "connected-accounts",
] as const;

const DEFAULT_SECTION = "general";

type SettingsContextValue = { openSettings: (sectionId?: string) => void };

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function useSettingsModal() {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error("useSettingsModal must be used within SettingsModalProvider");
  }
  return ctx;
}

function SectionPanel({ section }: { section: SettingsSection }) {
  switch (section.id) {
    case "general":
      return <GeneralSection />;
    case "learning":
      return <LearningSection />;
    case "language":
      return <LanguageSection />;
    case "appearance":
      return <AppearanceSection />;
    case "voice":
      return <VoiceSection />;
    case "familiar-regions":
      return <FamiliarRegionsSection />;
    case "institution":
      return <InstitutionSection />;
    case "privacy":
      return <PrivacySection />;
    case "connected-accounts":
      return <ConnectedAccountsSection />;
    default:
      return (
        <div className="mx-auto max-w-xl">
          <div className="mb-7">
            <h2 className="text-22 font-semibold text-ink">{section.label}</h2>
            <p className="mt-1 text-13 text-ink-secondary">{section.description}</p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-6 text-center text-13 text-ink-tertiary">
            This section is coming soon.
          </div>
        </div>
      );
  }
}

function SettingsModal({
  open,
  sectionId,
  onOpenChange,
  onSelectSection,
}: {
  open: boolean;
  sectionId: string;
  onOpenChange: (open: boolean) => void;
  onSelectSection: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const isCore = (id: string) => (CORE_IDS as readonly string[]).includes(id);
  const core = SETTINGS_SECTIONS.filter((s) => isCore(s.id));
  const account = SETTINGS_SECTIONS.filter((s) => !isCore(s.id));
  const section = SETTINGS_SECTIONS.find((s) => s.id === sectionId) ?? SETTINGS_SECTIONS[0];

  const querying = query.trim().length > 0;
  const matches = (s: SettingsSection) =>
    s.label.toLowerCase().includes(query.trim().toLowerCase()) ||
    s.description.toLowerCase().includes(query.trim().toLowerCase());
  const searchable = [...core, ...account].filter(matches);

  const renderItem = (s: SettingsSection) => {
    const Icon = s.icon;
    const active = s.id === section.id;
    return (
      <button
        key={s.id}
        onClick={() => onSelectSection(s.id)}
        aria-current={active ? "true" : undefined}
        className={cn(
          "focus-ring flex w-full items-center gap-2.5 rounded-sm px-3 py-2 text-14 transition-colors duration-150",
          active
            ? "bg-active font-medium text-accent"
            : "text-ink-secondary hover:bg-surface hover:text-ink",
        )}
      >
        <Icon size={15} aria-hidden className="shrink-0" />
        <span className="flex-1 truncate text-left">{s.label}</span>
      </button>
    );
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 animate-fade-in bg-stone-900/40 data-[state=closed]:animate-fade-out" />
        <DialogPrimitive.Content
          aria-label="Settings"
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[min(78vh,700px)] w-[min(780px,calc(100vw-1.5rem))]",
            "-translate-x-1/2 -translate-y-1/2 flex-col",
            "animate-scale-in overflow-hidden rounded-lg border border-border bg-canvas shadow-overlay",
            "data-[state=closed]:animate-scale-out focus:outline-none",
          )}
        >
          {/* Mobile header */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3 md:hidden">
            <span className="text-15 font-semibold text-ink">Settings</span>
            <DialogPrimitive.Close asChild>
              <IconButton aria-label="Close settings" size="sm">
                <X size={16} />
              </IconButton>
            </DialogPrimitive.Close>
          </div>

          {/* Mobile section strip */}
          <div className="flex gap-1.5 overflow-x-auto border-b border-border px-3 py-2 md:hidden">
            {searchable.length > 0
              ? searchable.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => onSelectSection(s.id)}
                    className={cn(
                      "focus-ring shrink-0 whitespace-nowrap rounded-full border px-3 py-1.5 text-12 font-medium transition-colors duration-150",
                      s.id === section.id
                        ? "border-accent bg-accent text-white"
                        : "border-border bg-surface text-ink-secondary hover:bg-subtle",
                    )}
                  >
                    {s.label}
                  </button>
                ))
              : null}
          </div>

          <div className="flex min-h-0 flex-1">
            {/* Desktop rail */}
            <aside className="hidden w-[240px] shrink-0 flex-col border-r border-border bg-subtle/50 p-3 md:flex">
              <div className="flex items-center justify-between px-1.5 pb-2">
                <span className="text-15 font-semibold text-ink">Settings</span>
                <DialogPrimitive.Close asChild>
                  <IconButton aria-label="Close settings" size="sm">
                    <X size={16} />
                  </IconButton>
                </DialogPrimitive.Close>
              </div>
              <div className="relative">
                <MagnifyingGlass
                  size={14}
                  aria-hidden
                  className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-tertiary"
                />

                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search settings"
                  aria-label="Search settings"
                  className="h-8 pl-8 text-12"
                />
              </div>
              <nav
                aria-label="Settings sections"
                className="mt-3 flex-1 space-y-0.5 overflow-y-auto"
              >
                {(querying ? searchable : core).map(renderItem)}
                {!querying && (
                  <>
                    <Separator className="my-2" />
                    <p className="px-3 py-1 text-11 font-medium tracking-wide text-ink-tertiary">
                      ACCOUNT
                    </p>
                    {account.map(renderItem)}
                  </>
                )}
                {querying && searchable.length === 0 && (
                  <p className="px-3 py-2 text-13 text-ink-tertiary">No settings found.</p>
                )}
              </nav>
            </aside>

            {/* Content — scrolls independently of the rail */}
            <div className="min-w-0 flex-1 overflow-y-auto p-6 md:p-8">
              <SectionPanel section={section} />
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/**
 * App-wide Settings modal. Opened from the AccountMenu (and anywhere else) via
 * `useSettingsModal().openSettings(section?)`. Rendered over the current page via
 * Radix Dialog — no navigation away from the workspace.
 */
export function SettingsModalProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [sectionId, setSectionId] = useState(DEFAULT_SECTION);

  const openSettings = useCallback((id?: string) => {
    setSectionId(id ?? DEFAULT_SECTION);
    setOpen(true);
  }, []);
  const selectSection = useCallback((id: string) => setSectionId(id), []);

  const value = useMemo(() => ({ openSettings }), [openSettings]);

  return (
    <SettingsContext.Provider value={value}>
      {children}
      <SettingsModal open={open} sectionId={sectionId} onOpenChange={setOpen} onSelectSection={selectSection} />
    </SettingsContext.Provider>
  );
}
