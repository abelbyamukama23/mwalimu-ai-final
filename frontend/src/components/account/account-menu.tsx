"use client";

import {
  Buildings,
  Gear,
  Globe,
  MapPin,
  PaintBrush,
  SignOut,
  Sparkle,
  UserCircle,
} from "@phosphor-icons/react";
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
  { id: "general", icon: UserCircle, label: "Profile" },
  { id: "general", icon: Gear, label: "Settings" },
  { id: "familiar-regions", icon: MapPin, label: "Familiar regions" },
  { id: "institution", icon: Buildings, label: "Institution" },
  { id: "appearance", icon: PaintBrush, label: "Appearance" },
  { id: "language", icon: Globe, label: "Language" },
  { id: "learning", icon: Sparkle, label: "Preferences" },
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
              <Icon size={18} weight="duotone" aria-hidden className="text-ink-tertiary" /> {item.label}
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout}>
          <SignOut size={18} weight="duotone" aria-hidden className="text-ink-tertiary" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

