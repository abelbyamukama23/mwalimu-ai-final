"use client";

import { useDevicePreferences } from "@/lib/settings/local-store";

/**
 * Applies the persisted device theme (system/light/dark) to the document and
 * keeps it in sync across tabs and OS changes. Rendered once at the app root.
 */
export function ThemeController() {
  useDevicePreferences();
  return null;
}
