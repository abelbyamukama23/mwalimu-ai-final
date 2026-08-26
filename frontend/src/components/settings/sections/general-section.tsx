"use client";

import { UserCircle } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { useUpdateUserProfile, useUserProfile } from "@/lib/hooks/use-profile";
import type { UserProfile } from "@/lib/settings/types";
import { SettingRow } from "../primitives/setting-row";

function ProfileForm({ profile }: { profile?: UserProfile }) {
  const updateProfile = useUpdateUserProfile();
  const toast = useToast();

  const [displayName, setDisplayName] = useState(profile?.display_name || "");
  const [bio, setBio] = useState(profile?.bio || "");
  const [isSaved, setIsSaved] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await updateProfile.mutateAsync({
        display_name: displayName.trim(),
        bio: bio.trim(),
      });
      toast("Profile updated successfully");
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2000);
    } catch {
      toast("Failed to update profile.");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="rounded-lg border border-border bg-surface p-6 space-y-5">
        <div className="space-y-1.5">
          <label className="block text-11 font-medium uppercase tracking-wide text-ink-tertiary">
            Display Name
          </label>
          <Input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="e.g. Mwalimu Kenneth"
          />
          <p className="text-11 text-ink-tertiary">
            Your public name used when collaborating or receiving personalized responses.
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-11 font-medium uppercase tracking-wide text-ink-tertiary">
            Bio / Focus
          </label>
          <Textarea
            rows={2}
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            placeholder="e.g. Biology & Chemistry teacher at Alliance High School"
          />
        </div>

        <div className="flex justify-end pt-2">
          <Button
            type="submit"
            disabled={updateProfile.isPending}
          >
            {updateProfile.isPending
              ? "Saving…"
              : isSaved
                ? "Saved"
                : "Save changes"}
          </Button>
        </div>
      </div>
    </form>
  );
}

export function GeneralSection() {
  const { data: user, isLoading: loadingUser } = useCurrentUser();
  const { data: profile, isLoading: loadingProfile } = useUserProfile();

  const isLoading = loadingUser || loadingProfile;

  if (isLoading) {
    return (
      <div className="py-8 text-center text-13 text-ink-tertiary">
        Loading profile details…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-22 font-semibold text-ink">General</h2>
        </div>
        <p className="mt-1 text-13 text-ink-secondary">
          Manage your personal profile and account credentials.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-6">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-surface-sunken text-ink-tertiary border border-border">
            <UserCircle size={32} />
          </div>
          <div>
            <p className="text-14 font-semibold text-ink">
              {profile?.display_name || user?.email?.split("@")[0] || "Learner"}
            </p>
            <p className="text-12 font-mono text-ink-tertiary">{user?.email}</p>
          </div>
        </div>
      </div>

      <ProfileForm key={profile?.id ?? "default"} profile={profile} />

      {/* Account Info (Read-only System of Record attributes) */}
      <div className="rounded-lg border border-border bg-surface p-6">
        <h3 className="text-13 font-semibold text-ink uppercase tracking-wide">
          Account Details
        </h3>
        <div className="divide-y divide-border-subtle mt-2">
          <SettingRow
            label="Email Address"
            description="Primary login identifier and system of record account key."
          >
            <span className="font-mono text-12 text-ink-secondary">
              {user?.email}
            </span>
          </SettingRow>
          <SettingRow
            label="Account Created"
            description="Date this account was registered on Mwalimu."
          >
            <span className="text-12 text-ink-tertiary">
              {user?.created_at
                ? new Date(user.created_at).toLocaleDateString()
                : "—"}
            </span>
          </SettingRow>
        </div>
      </div>
    </div>
  );
}
