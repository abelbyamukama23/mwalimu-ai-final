import { Info } from "lucide-react";

const STATS = ["Active users", "Institution libraries", "Pending access requests", "Queries this month"] as const;

/**
 * Console dashboard placeholder. Analytics/metrics endpoints do not exist in the
 * Platform API, so cards render "—" instead of fabricated numbers.
 */
export default function ConsoleDashboardPage() {
  return (
    <div className="px-6 py-10 md:px-10">
      <div className="mb-8">
        <h1 className="text-22 font-semibold text-ink">Dashboard</h1>
        <p className="mt-1 text-13 text-ink-secondary">
          An overview of Mwalimu across your institution.
        </p>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {STATS.map((label) => (
          <div
            key={label}
            className="rounded-md border border-border bg-surface px-5 py-4"
          >
            <p className="mb-1.5 text-12 text-ink-tertiary">{label}</p>
            <p className="text-28 font-semibold text-ink">—</p>
          </div>
        ))}
      </div>

      <div className="flex max-w-3xl items-start gap-3 rounded-md border border-info-bg bg-info-bg/40 px-4 py-3.5">
        <Info size={16} aria-hidden className="mt-0.5 shrink-0 text-info-fg" />
        <p className="text-13 leading-relaxed text-ink-secondary">
          Usage metrics require analytics endpoints the Platform API does not expose yet.
          Users, Libraries, Resources, and Context management land in Phase 5 against the
          existing memberships, libraries, resources, and context APIs.
        </p>
      </div>
    </div>
  );
}
