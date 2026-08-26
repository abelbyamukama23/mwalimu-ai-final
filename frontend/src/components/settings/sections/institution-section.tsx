"use client";

import { Building2, CheckCircle2, ShieldCheck, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useMemberships } from "@/lib/hooks/use-memberships";

export function InstitutionSection() {
  const { data: memberships, isLoading } = useMemberships();

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-22 font-semibold text-ink">Institution</h2>
          <Badge tone="info">Synced to account</Badge>
        </div>
        <p className="mt-1 text-13 text-ink-secondary">
          Connect with your school, university, or educational organization to access shared libraries and curriculum resources.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-6 space-y-5">
        <h3 className="text-13 font-semibold text-ink uppercase tracking-wide">
          Connected Institutions
        </h3>

        {isLoading ? (
          <div className="py-6 text-center text-13 text-ink-tertiary">
            Loading institution memberships…
          </div>
        ) : !memberships || memberships.length === 0 ? (
          <div className="rounded-md border border-border bg-surface-sunken p-6 text-center space-y-2">
            <Building2 size={24} className="mx-auto text-ink-tertiary" />
            <p className="text-14 font-semibold text-ink">No Institution Connected</p>
            <p className="text-12 text-ink-secondary max-w-md mx-auto leading-relaxed">
              You are currently using Mwalimu in independent personal mode. You can create personal libraries and chat freely.
              If your school uses Mwalimu, an administrator will invite your account email.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {memberships.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between py-4"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-surface-sunken border border-border text-ink-secondary">
                    <Building2 size={18} />
                  </div>
                  <div>
                    <p className="text-14 font-semibold text-ink">
                      {m.institution.name}
                    </p>
                    <p className="text-11 font-mono text-ink-tertiary">
                      slug: {m.institution.slug}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Badge
                    tone={m.role === "administrator" ? "accent" : "neutral"}
                    className="capitalize"
                  >
                    {m.role === "administrator" ? (
                      <ShieldCheck size={12} className="mr-1 inline" />
                    ) : (
                      <User size={12} className="mr-1 inline" />
                    )}
                    {m.role}
                  </Badge>
                  <Badge
                    tone={m.status === "active" ? "success" : "warning"}
                    className="capitalize"
                  >
                    <CheckCircle2 size={11} className="mr-1 inline" />
                    {m.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
