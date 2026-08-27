"use client";

import {
  Building2,
  CheckCircle2,
  Clock,
  Plus,
  School,
  ShieldCheck,
  User,
  UserPlus,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  useCreateMembership,
  useInstitutions,
  useMemberships,
} from "@/lib/hooks/use-memberships";

export function InstitutionSection() {
  const { data: memberships, isLoading: loadingMemberships } = useMemberships();
  const { data: institutions, isLoading: loadingInstitutions } = useInstitutions();
  const createMembershipMutation = useCreateMembership();
  const toast = useToast();

  const [joiningId, setJoiningId] = useState<string | null>(null);

  // Set of connected institution IDs
  const connectedIds = useMemo(
    () => new Set((memberships ?? []).map((m) => m.institution.id)),
    [memberships],
  );

  // Institutions that the user has not yet joined
  const availableToJoin = useMemo(
    () => (institutions ?? []).filter((inst) => !connectedIds.has(inst.id)),
    [institutions, connectedIds],
  );

  const handleJoin = async (institutionId: string, institutionName: string) => {
    setJoiningId(institutionId);
    try {
      await createMembershipMutation.mutateAsync({
        institution_id: institutionId,
        role: "student",
      });
      toast(`Membership request sent for "${institutionName}".`);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to join institution.";
      toast(message);
    } finally {
      setJoiningId(null);
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-22 font-semibold text-ink">Institutions & Schools</h2>
          <Badge tone="info">Synced to account</Badge>
        </div>
        <p className="mt-1 text-13 text-ink-secondary">
          Connect with your school, university, or national educational organization to access shared curriculum libraries.
        </p>
      </div>

      {/* Connected Institutions Card */}
      <div className="rounded-lg border border-border bg-surface p-6 space-y-4">
        <h3 className="text-12 font-semibold uppercase tracking-wider text-ink-tertiary">
          Your Connected Institutions
        </h3>

        {loadingMemberships ? (
          <div className="py-6 text-center text-13 text-ink-tertiary">
            Loading institution memberships…
          </div>
        ) : !memberships || memberships.length === 0 ? (
          <div className="rounded-md border border-border bg-surface-sunken p-6 text-center space-y-2">
            <Building2 size={24} className="mx-auto text-ink-tertiary" />
            <p className="text-14 font-semibold text-ink">No Institution Connected</p>
            <p className="text-12 text-ink-secondary max-w-md mx-auto leading-relaxed">
              You are currently using Mwalimu in independent personal mode. You can create personal libraries or browse public educational institutions below.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {memberships.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between py-3.5"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-sunken border border-border text-ink-secondary">
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
                    {m.status === "active" ? (
                      <CheckCircle2 size={11} className="mr-1 inline" />
                    ) : (
                      <Clock size={11} className="mr-1 inline" />
                    )}
                    {m.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Available Institutions to Join */}
      {availableToJoin.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-6 space-y-4">
          <h3 className="text-12 font-semibold uppercase tracking-wider text-ink-tertiary">
            Available Educational Institutions
          </h3>
          <p className="text-12 text-ink-secondary">
            Join registered schools and institutes to collaborate on curriculum libraries.
          </p>

          <div className="divide-y divide-border-subtle">
            {availableToJoin.map((inst) => (
              <div
                key={inst.id}
                className="flex items-center justify-between py-3.5"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-subtle/30 text-accent border border-accent/20">
                    <School size={18} />
                  </div>
                  <div>
                    <p className="text-14 font-semibold text-ink">
                      {inst.name}
                    </p>
                    <p className="text-11 font-mono text-ink-tertiary">
                      slug: {inst.slug}
                    </p>
                  </div>
                </div>

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleJoin(inst.id, inst.name)}
                  disabled={
                    joiningId === inst.id || createMembershipMutation.isPending
                  }
                >
                  <UserPlus size={13} aria-hidden /> Join
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
