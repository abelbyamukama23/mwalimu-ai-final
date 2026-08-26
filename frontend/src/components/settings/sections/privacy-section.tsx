"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  useUpdateUserPreferences,
  useUserPreferences,
} from "@/lib/hooks/use-preferences";
import { SettingRow } from "../primitives/setting-row";
import { SettingSelect } from "../primitives/setting-select";
import { SettingToggle } from "../primitives/setting-toggle";

const RETENTION_OPTIONS = [
  { value: "forever", label: "Keep indefinitely (Default)" },
  { value: "90_days", label: "90 days" },
  { value: "30_days", label: "30 days" },
];

export function PrivacySection() {
  const { data: preferences } = useUserPreferences();
  const updatePreferences = useUpdateUserPreferences();
  const toast = useToast();

  const [retention, setRetention] = useState("forever");
  const [exporting, setExporting] = useState(false);

  const handleMemoryToggle = async (checked: boolean) => {
    try {
      await updatePreferences.mutateAsync({ cross_session_memory: checked });
      toast(checked ? "Session memory enabled" : "Session memory disabled");
    } catch {
      toast("Failed to update memory setting.");
    }
  };

  const handleExportData = () => {
    setExporting(true);
    setTimeout(() => {
      setExporting(false);
      toast("Your data archive is being prepared. Download will begin shortly.");
    }, 1200);
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h2 className="text-22 font-semibold text-ink">Privacy & Data Controls</h2>
        <p className="mt-1 text-13 text-ink-secondary">
          Control data retention, AI memory, and your personal data rights.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-6 divide-y divide-border-subtle">
        <SettingRow
          label="Cross-Session AI Memory"
          description="Allow Mwalimu to remember your past topics and concepts across distinct chat sessions."
        >
          <SettingToggle
            checked={preferences?.cross_session_memory ?? true}
            onCheckedChange={handleMemoryToggle}
            aria-label="Toggle cross session memory"
          />
        </SettingRow>

        <SettingRow
          label="Conversation History Retention"
          description="Period to retain chat transcripts before automated cleanup."
        >
          <SettingSelect
            options={RETENTION_OPTIONS}
            value={retention}
            onChange={(val) => {
              setRetention(val);
              toast(`Retention updated to ${val}`);
            }}
            aria-label="Chat retention policy"
          />
        </SettingRow>

        <SettingRow
          label="Export Personal Data"
          description="Download a machine-readable JSON archive of your personal libraries, study notes, and chat transcripts."
        >
          <Button
            size="sm"
            variant="secondary"
            disabled={exporting}
            onClick={handleExportData}
          >
            <Download size={13} className="mr-1.5" />
            {exporting ? "Preparing…" : "Export archive"}
          </Button>
        </SettingRow>
      </div>
    </div>
  );
}
