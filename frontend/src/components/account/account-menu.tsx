"use client";

import {
  Building01Icon,
  Globe02Icon,
  Location01Icon,
  Logout01Icon,
  PaintBrush01Icon,
  Settings01Icon,
  SparklesIcon,
  UserCircleIcon,
} from "hugeicons-react";
import type { ReactNode } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import { useSettingsModal } from "@/components/settings/settings-modal";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** Account-menu entries → Settings modal sections. */
const MENU = [
  { id: "general", icon: UserCircleIcon, label: "Profile" },
  { id: "general", icon: Settings01Icon, label: "Settings" },
  { id: "familiar-regions", icon: Location01Icon, label: "Familiar regions" },
  { id: "institution", icon: Building01Icon, label: "Institution" },
  { id: "appearance", icon: PaintBrush01Icon, label: "Appearance" },
  { id: "language", icon: Globe02Icon, label: "Language" },
  { id: "learning", icon: SparklesIcon, label: "Preferences" },
] as const;

/**
 * Bottom-left account control. Opens a popover menu — it never navigates the
 * whole app away from the conversation. Choosing a settings entry opens the
 * Settings modal over the current page.
 */
export function AccountMenu({ trigger }: { trigger: ReactNode }) {
  const { openSettings } = useSettingsModal();
  const { user, logout } = useAuth();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-64">
        <DropdownMenuLabel className="border-b border-border pb-2.5">
          <span className="block truncate text-13 font-medium text-ink">
            {user?.email ?? "Signed in"}
          </span>
        </DropdownMenuLabel>
        {MENU.map((item) => {
          const Icon = item.icon;
          return (
            <DropdownMenuItem key={item.label} onClick={() => openSettings(item.id)}>
              <Icon size={16} aria-hidden className="text-ink-tertiary" /> {item.label}
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout}>
          <Logout01Icon size={16} aria-hidden className="text-ink-tertiary" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
