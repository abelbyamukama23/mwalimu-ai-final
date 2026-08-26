"use client";

import { useToast } from "@/components/ui/toast";
import {
  useUpdateUserPreferences,
  useUserPreferences,
} from "@/lib/hooks/use-preferences";
import { useDevicePreferences } from "@/lib/settings/local-store";
import type { UiLanguage } from "@/lib/settings/types";
import { SettingRow } from "../primitives/setting-row";
import { SettingSelect } from "../primitives/setting-select";

const UI_LANGUAGES = [
  { value: "en" as UiLanguage, label: "English (US/UK)" },
  { value: "sw" as UiLanguage, label: "Kiswahili" },
  { value: "fr" as UiLanguage, label: "Français" },
];

const RESPONSE_LANGUAGES = [
  { value: "en", label: "English" },
  { value: "sw", label: "Kiswahili (Kiswahili Sanifu)" },
  { value: "bilingual_en_sw", label: "Bilingual (English + Kiswahili)" },
  { value: "fr", label: "Français" },
];

export function LanguageSection() {
  const { preferences: devicePrefs, setUiLanguage } = useDevicePreferences();
  const { data: userPrefs, isLoading } = useUserPreferences();
  const updatePreferences = useUpdateUserPreferences();
  const toast = useToast();

  const handleUiLangChange = (lang: UiLanguage) => {
    setUiLanguage(lang);
    toast("Interface language updated on this device");
  };

  const handleResponseLangChange = async (lang: string) => {
    try {
      await updatePreferences.mutateAsync({ response_language: lang });
      toast("AI response language updated");
    } catch {
      toast("Failed to update AI response language.");
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h2 className="text-22 font-semibold text-ink">Language</h2>
        <p className="mt-1 text-13 text-ink-secondary">
          Configure interface translation and pedagogical response languages.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-6 divide-y divide-border-subtle">
        <SettingRow
          label="Interface Language"
          description="Language used for buttons, menus, and application labels."
          badge={{ label: "Device only", tone: "neutral" }}
        >
          <SettingSelect
            options={UI_LANGUAGES}
            value={devicePrefs.uiLanguage}
            onChange={handleUiLangChange}
            aria-label="Interface language"
          />
        </SettingRow>

        <SettingRow
          label="AI Explanation Language"
          description="Target language Mwalimu uses when answering questions and formulating analogies."
          badge={{ label: "Synced to account", tone: "info" }}
        >
          <SettingSelect
            options={RESPONSE_LANGUAGES}
            value={userPrefs?.response_language || "en"}
            onChange={handleResponseLangChange}
            disabled={isLoading || updatePreferences.isPending}
            aria-label="AI Explanation language"
          />
        </SettingRow>
      </div>
    </div>
  );
}
