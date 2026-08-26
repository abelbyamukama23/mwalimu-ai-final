"use client";

import { Laptop, Moon, Sun } from "lucide-react";
import { useToast } from "@/components/ui/toast";
import { useDevicePreferences } from "@/lib/settings/local-store";
import type { DisplayDensity, ThemeMode } from "@/lib/settings/types";
import { SettingRadioCards } from "../primitives/setting-radio-cards";
import { SettingRow } from "../primitives/setting-row";
import { SettingSelect } from "../primitives/setting-select";

const THEME_OPTIONS = [
  {
    value: "system" as ThemeMode,
    label: "System",
    description: "Matches your operating system's visual appearance.",
    icon: Laptop,
  },
  {
    value: "light" as ThemeMode,
    label: "Light",
    description: "Crisp, daylight optimized palette.",
    icon: Sun,
  },
  {
    value: "dark" as ThemeMode,
    label: "Dark",
    description: "High contrast dark palette for low-light environments.",
    icon: Moon,
  },
];

const DENSITY_OPTIONS = [
  { value: "comfortable" as DisplayDensity, label: "Comfortable (Standard)" },
  { value: "compact" as DisplayDensity, label: "Compact (Dense)" },
];

export function AppearanceSection() {
  const { preferences, setTheme, setDensity } = useDevicePreferences();
  const toast = useToast();

  const handleThemeChange = (theme: ThemeMode) => {
    setTheme(theme);
    toast(`Theme set to ${theme}`);
  };

  const handleDensityChange = (density: DisplayDensity) => {
    setDensity(density);
    toast(`Density set to ${density}`);
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h2 className="text-22 font-semibold text-ink">Appearance</h2>
        <p className="mt-1 text-13 text-ink-secondary">
          Customize the visual theme and layout density on this device.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-6 space-y-6">
        <div className="space-y-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-14 font-semibold text-ink">Theme</h3>
              <span className="text-11 font-medium text-ink-tertiary">
                (Device only)
              </span>
            </div>
            <p className="text-12 text-ink-secondary">
              Select your preferred color scheme.
            </p>
          </div>
          <SettingRadioCards
            options={THEME_OPTIONS}
            value={preferences.theme}
            onChange={handleThemeChange}
          />
        </div>

        <div className="border-t border-border-subtle pt-4">
          <SettingRow
            label="Layout Density"
            description="Adjust padding and information density across lists and cards."
            badge={{ label: "Device only", tone: "neutral" }}
          >
            <SettingSelect
              options={DENSITY_OPTIONS}
              value={preferences.density}
              onChange={handleDensityChange}
              aria-label="Layout density"
            />
          </SettingRow>
        </div>
      </div>
    </div>
  );
}
