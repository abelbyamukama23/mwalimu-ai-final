"use client";

import {
  ArrowLeft,
  BarChart3,
  Building2,
  FileText,
  LayoutGrid,
  Library,
  Lock,
  MapPin,
  Menu,
  Plug,
  Settings as SettingsIcon,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";

/** Phase 0 placeholder — replaced by the admin's institution from the memberships API. */
const INSTITUTION_NAME = "Mountains of the Moon University";

type ConsoleNavItem = {
  id: string;
  label: string;
  icon: LucideIcon;
  href?: string; // absent = not yet implemented (disabled, "Soon")
};

const CONSOLE_NAV: ConsoleNavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutGrid, href: "/console/dashboard" },
  { id: "users", label: "Users", icon: Users },
  { id: "libraries", label: "Libraries", icon: Library },
  { id: "access", label: "Access", icon: Lock },
  { id: "resources", label: "Resources", icon: FileText },
  { id: "context", label: "Context", icon: MapPin },
  { id: "connections", label: "Connections", icon: Plug },
  { id: "analytics", label: "Analytics", icon: BarChart3 },

  { id: "settings", label: "Settings", icon: SettingsIcon },
];

function ConsoleNavContent() {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col px-3 py-6">
      <div className="mb-1 flex items-center gap-2 px-2">
        <span
          aria-hidden
          className="flex h-7 w-7 items-center justify-center rounded-sm bg-accent"
        >
          <Building2 size={14} className="text-white" />
        </span>
        <span className="text-15 font-semibold text-white">Institution Console</span>
      </div>
      <p className="mb-5 truncate px-2 text-11 text-console-muted">{INSTITUTION_NAME}</p>

      <nav aria-label="Institution console" className="flex-1 space-y-0.5">
        {CONSOLE_NAV.map((item) => {
          const Icon = item.icon;
          const active = item.href !== undefined && pathname.startsWith(item.href);
          if (!item.href) {
            // Sections the backend does not yet serve are shown disabled — never faked.
            return (
              <span
                key={item.id}
                aria-disabled
                title="Coming in a later phase"
                className="flex cursor-not-allowed items-center gap-2.5 rounded-sm px-3 py-2 text-14 text-console-muted/60"
              >
                <Icon size={15} aria-hidden className="shrink-0" />
                {item.label}
                <span className="ml-auto text-11">Soon</span>
              </span>
            );
          }
          return (
            <Link
              key={item.id}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "focus-ring flex items-center gap-2.5 rounded-sm px-3 py-2 text-14 transition-colors duration-150",
                active
                  ? "bg-console-hover font-medium text-white"
                  : "text-console-fg hover:bg-console-hover/70 hover:text-white",
              )}
            >
              <Icon size={15} aria-hidden className="shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <Link
        href="/chat/new"
        className="focus-ring mt-4 flex items-center gap-2 rounded-sm px-3 py-2 text-12 text-console-muted transition-colors duration-150 hover:bg-console-hover/70 hover:text-console-fg"
      >
        <ArrowLeft size={14} aria-hidden /> Exit to user app
      </Link>
    </div>
  );
}

/**
 * Institution Console — a completely separate application shell with its own
 * dark navigation. Never mixed into the generic user sidebar.
 */
export function InstitutionShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="flex h-dvh overflow-hidden">
      <aside className="hidden h-full w-[240px] shrink-0 bg-console-bg lg:block">
        <ConsoleNavContent />
      </aside>

      <div className="fixed inset-x-0 top-0 z-40 flex h-14 items-center gap-2 border-b border-border bg-canvas px-3 lg:hidden">
        <IconButton aria-label="Open console navigation" onClick={() => setNavOpen(true)}>
          <Menu size={18} />
        </IconButton>
        <span className="text-15 font-semibold text-ink">Institution Console</span>
      </div>

      <Drawer open={navOpen} onOpenChange={setNavOpen}>
        <DrawerContent
          side="left"
          className="w-[260px] bg-console-bg p-0"
          aria-label="Console navigation"
        >
          <div onClick={() => setNavOpen(false)} className="h-full">
            <ConsoleNavContent />
          </div>
        </DrawerContent>
      </Drawer>

      <main className="min-w-0 flex-1 overflow-y-auto pt-14 lg:pt-0">{children}</main>
    </div>
  );
}
