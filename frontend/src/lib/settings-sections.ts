import {
  Bell,
  Building2,
  Languages,
  Link2,
  MapPin,
  Mic,
  Palette,
  Shield,
  Sparkles,
  UserCircle,
  type LucideIcon,
} from "lucide-react";

export type SettingsSectionStatus =
  | { kind: "backend"; label: string }
  | { kind: "local"; label: string }
  | { kind: "pending"; label: string };

export type SettingsSection = {
  id: string;
  label: string;
  icon: LucideIcon;
  description: string;
  status: SettingsSectionStatus;
};

/**
 * Settings IA. Every section declares honestly whether it persists to the
 * backend, persists only on this device, or is pending a backend slice.
 */
export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    id: "general",
    label: "General",
    icon: UserCircle,
    description: "Your profile, display name, and account details.",
    status: { kind: "backend", label: "Profile & Identity" },
  },
  {
    id: "learning",
    label: "Learning",
    icon: Sparkles,
    description: "How Mwalimu explains things — style, depth, and pedagogical memory.",
    status: { kind: "backend", label: "Pedagogical Grounding" },
  },
  {
    id: "language",
    label: "Language",
    icon: Languages,
    description: "Interface and pedagogical response language.",
    status: { kind: "local", label: "Device & AI response" },
  },
  {
    id: "voice",
    label: "Voice",
    icon: Mic,
    description: "Speech playback speed and spoken audio output.",
    status: { kind: "local", label: "Stored on this device only" },
  },
  {
    id: "notifications",
    label: "Notifications",
    icon: Bell,
    description: "What Mwalimu tells you about, and when.",
    status: { kind: "pending", label: "Coming soon" },
  },
  {
    id: "appearance",
    label: "Appearance",
    icon: Palette,
    description: "Theme, density, and color scheme.",
    status: { kind: "local", label: "Stored on this device only" },
  },
  {
    id: "privacy",
    label: "Privacy",
    icon: Shield,
    description: "What Mwalimu remembers and stores about you.",
    status: { kind: "backend", label: "Data Controls" },
  },
  {
    id: "connected-accounts",
    label: "Connected accounts",
    icon: Link2,
    description: "Third-party services linked to your Mwalimu workspace.",
    status: { kind: "backend", label: "OAuth Identity" },
  },
  {
    id: "familiar-regions",
    label: "Familiar regions",
    icon: MapPin,
    description:
      "Places whose farming practices, climate, and daily life you understand. Mwalimu prefers these for examples.",
    status: { kind: "backend", label: "Backed by Context API" },
  },
  {
    id: "institution",
    label: "Institution",
    icon: Building2,
    description:
      "Connect to a school or university to access shared libraries and curriculum resources.",
    status: { kind: "backend", label: "Backed by Memberships API" },
  },
];
