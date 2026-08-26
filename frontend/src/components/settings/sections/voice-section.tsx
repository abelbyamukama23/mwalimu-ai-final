"use client";

import { useToast } from "@/components/ui/toast";
import { useDevicePreferences } from "@/lib/settings/local-store";
import { SettingRow } from "../primitives/setting-row";
import { SettingSelect } from "../primitives/setting-select";
import { SettingToggle } from "../primitives/setting-toggle";

const SPEECH_RATES = [
  { value: "0.75", label: "0.75x (Slower)" },
  { value: "1.0", label: "1.0x (Normal)" },
  { value: "1.25", label: "1.25x (Fast)" },
  { value: "1.5", label: "1.5x (Faster)" },
];

export function VoiceSection() {
  const { preferences, updatePreferences } = useDevicePreferences();
  const toast = useToast();

  const handleAutoPlayToggle = (checked: boolean) => {
    updatePreferences({ autoPlayAudio: checked });
    toast(checked ? "Auto-play audio enabled" : "Auto-play audio disabled");
  };

  const handleSpeechRateChange = (val: string) => {
    const rate = parseFloat(val);
    updatePreferences({ speechRate: rate });
    toast(`Speech rate set to ${rate}x`);
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h2 className="text-22 font-semibold text-ink">Voice</h2>
        <p className="mt-1 text-13 text-ink-secondary">
          Configure speech output and voice interaction preferences.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-6 divide-y divide-border-subtle">
        <SettingRow
          label="Auto-Play Audio Responses"
          description="Automatically speak answers aloud when Mwalimu finishes generating a response."
          badge={{ label: "Device only", tone: "neutral" }}
        >
          <SettingToggle
            checked={preferences.autoPlayAudio}
            onCheckedChange={handleAutoPlayToggle}
            aria-label="Toggle auto-play audio"
          />
        </SettingRow>

        <SettingRow
          label="Spoken Response Speed"
          description="Adjust the playback rate of the text-to-speech voice."
          badge={{ label: "Device only", tone: "neutral" }}
        >
          <SettingSelect
            options={SPEECH_RATES}
            value={preferences.speechRate.toString()}
            onChange={handleSpeechRateChange}
            aria-label="Speech playback rate"
          />
        </SettingRow>
      </div>
    </div>
  );
}
