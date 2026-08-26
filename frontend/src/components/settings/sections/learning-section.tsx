"use client";

import { BookOpen, Compass, Lightbulb } from "lucide-react";
import { useToast } from "@/components/ui/toast";
import {
  useUpdateUserPreferences,
  useUserPreferences,
} from "@/lib/hooks/use-preferences";
import type { ExplanationDepth, PedagogicalStyle } from "@/lib/settings/types";
import { SettingRadioCards } from "../primitives/setting-radio-cards";
import { SettingRow } from "../primitives/setting-row";
import { SettingToggle } from "../primitives/setting-toggle";

const STYLE_OPTIONS = [
  {
    value: "intuitive" as PedagogicalStyle,
    label: "Intuitive & Analogies",
    description: "Uses real-world East African context, farming analogies, and intuitive mental models.",
    icon: Lightbulb,
  },
  {
    value: "formal" as PedagogicalStyle,
    label: "Academic & Formal",
    description: "Strict curriculum terminology, formal definitions, and rigorous structure.",
    icon: BookOpen,
  },
  {
    value: "socratic" as PedagogicalStyle,
    label: "Socratic & Guiding",
    description: "Guides step-by-step with targeted questions rather than giving immediate answers.",
    icon: Compass,
  },
];

const DEPTH_OPTIONS = [
  {
    value: "concise" as ExplanationDepth,
    label: "Concise",
    description: "Short, direct summaries and bullet points.",
  },
  {
    value: "standard" as ExplanationDepth,
    label: "Standard",
    description: "Balanced explanations with contextual examples.",
  },
  {
    value: "in_depth" as ExplanationDepth,
    label: "In-Depth",
    description: "Comprehensive breakdowns exploring edge cases and foundational principles.",
  },
];

export function LearningSection() {
  const { data: preferences, isLoading } = useUserPreferences();
  const updatePreferences = useUpdateUserPreferences();
  const toast = useToast();

  const handleStyleChange = async (style: PedagogicalStyle) => {
    try {
      await updatePreferences.mutateAsync({ pedagogical_style: style });
      toast("Pedagogical style updated");
    } catch {
      toast("Failed to update learning preferences.");
    }
  };

  const handleDepthChange = async (depth: ExplanationDepth) => {
    try {
      await updatePreferences.mutateAsync({ explanation_depth: depth });
      toast("Explanation depth updated");
    } catch {
      toast("Failed to update learning preferences.");
    }
  };

  const handleMemoryToggle = async (checked: boolean) => {
    try {
      await updatePreferences.mutateAsync({ cross_session_memory: checked });
      toast(checked ? "Cross-session memory enabled" : "Cross-session memory disabled");
    } catch {
      toast("Failed to update memory preference.");
    }
  };

  if (isLoading) {
    return (
      <div className="py-8 text-center text-13 text-ink-tertiary">
        Loading learning preferences…
      </div>
    );
  }

  const currentStyle = preferences?.pedagogical_style || "intuitive";
  const currentDepth = preferences?.explanation_depth || "standard";
  const currentMemory = preferences?.cross_session_memory ?? true;

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h2 className="text-22 font-semibold text-ink">Learning</h2>
        <p className="mt-1 text-13 text-ink-secondary">
          Configure how Mwalimu explains concepts and structures answers during chat sessions.
        </p>
      </div>

      <div className="space-y-6 rounded-lg border border-border bg-surface p-6">
        {/* Style selection */}
        <div className="space-y-3">
          <div>
            <h3 className="text-14 font-semibold text-ink">Explanation Style</h3>
            <p className="text-12 text-ink-secondary">
              Guides the pedagogical approach and tone of the AI tutor.
            </p>
          </div>
          <SettingRadioCards
            options={STYLE_OPTIONS}
            value={currentStyle}
            onChange={handleStyleChange}
            disabled={updatePreferences.isPending}
          />
        </div>

        <div className="border-t border-border-subtle pt-5 space-y-3">
          <div>
            <h3 className="text-14 font-semibold text-ink">Explanation Depth</h3>
            <p className="text-12 text-ink-secondary">
              Controls the default length and detail level of responses.
            </p>
          </div>
          <SettingRadioCards
            options={DEPTH_OPTIONS}
            value={currentDepth}
            onChange={handleDepthChange}
            disabled={updatePreferences.isPending}
          />
        </div>

        <div className="border-t border-border-subtle pt-4">
          <SettingRow
            label="Cross-Session Pedagogical Memory"
            description="Allows Mwalimu to remember your past questions and mastery level across different chat sessions to reinforce learning."
          >
            <SettingToggle
              checked={currentMemory}
              onCheckedChange={handleMemoryToggle}
              disabled={updatePreferences.isPending}
              aria-label="Toggle cross-session memory"
            />
          </SettingRow>
        </div>
      </div>
    </div>
  );
}
