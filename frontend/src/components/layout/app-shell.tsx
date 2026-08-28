"use client";

import { List, SidebarSimple } from "@phosphor-icons/react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { SidebarContent } from "@/components/layout/sidebar";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";

/**
 * Generic user application shell: a full-height collapsible sidebar (desktop),
 * a navigation drawer on mobile, and a main content column that fills the
 * entire viewport. There is no top header bar, so content such as the chat
 * conversation scrolls right up to the top of the browser viewport.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-dvh overflow-hidden">
      {/* Desktop sidebar (full height, collapsible to an icon rail) */}
      <aside
        className={cn(
          "hidden shrink-0 overflow-hidden border-r border-border bg-sidebar transition-[width] duration-200 ease-out lg:block",
          collapsed ? "lg:w-16" : "lg:w-[300px]",
        )}
      >
        <div
          className={cn(
            "flex h-full flex-col",
            collapsed ? "w-16" : "w-[300px]",
          )}
        >
          {/* Brand + collapse control (desktop only) */}
          <div
            className={cn(
              "flex h-14 shrink-0 items-center border-b border-border",
              collapsed ? "justify-center" : "gap-2 px-3",
            )}
          >
            {collapsed ? (
              <IconButton
                aria-label="Expand sidebar"
                onClick={() => setCollapsed(false)}
                className="text-ink-secondary hover:text-ink"
              >
                <SidebarSimple size={18} weight="duotone" />
              </IconButton>
            ) : (
              <>
                <Link
                  href="/chat/new"
                  className="focus-ring flex items-center gap-2 rounded-sm px-1 py-1"
                >
                  <span aria-hidden className="h-7 w-7 rounded-sm bg-accent" />
                  <span className="text-17 font-semibold text-ink">Mwalimu</span>
                </Link>
                <div className="flex-1" />
                <IconButton
                  aria-label="Collapse sidebar"
                  onClick={() => setCollapsed(true)}
                  className="text-ink-secondary hover:text-ink"
                >
                  <SidebarSimple size={18} weight="duotone" />
                </IconButton>
              </>
            )}
          </div>


          {!collapsed && (
            <div className="min-h-0 flex-1">
              <SidebarContent />
            </div>
          )}
        </div>
      </aside>

      {/* Mobile navigation trigger (full-height content, floating control) */}
      <IconButton
        aria-label="Open navigation"
        onClick={() => setNavOpen(true)}
        className="fixed left-3 top-3 z-30 rounded-md border border-border bg-surface/90 shadow-overlay lg:hidden"
      >
        <List size={18} weight="bold" />
      </IconButton>


      {/* Mobile navigation drawer */}
      <Drawer open={navOpen} onOpenChange={setNavOpen}>
        <DrawerContent
          side="left"
          className="w-[280px] bg-sidebar p-0"
          aria-label="Navigation"
        >
          <div onClick={() => setNavOpen(false)} className="flex h-full flex-col">
            <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-3">
              <span aria-hidden className="h-7 w-7 rounded-sm bg-accent" />
              <span className="text-17 font-semibold text-ink">Mwalimu</span>
            </div>
            <div className="min-h-0 flex-1">
              <SidebarContent />
            </div>
          </div>
        </DrawerContent>
      </Drawer>

      {/* Main content fills the entire viewport height/width */}
      <main className="min-h-0 min-w-0 flex-1">{children}</main>
    </div>
  );
}
