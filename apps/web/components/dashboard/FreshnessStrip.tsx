"use client";

/**
 * Data-freshness strip.
 *
 * Shows, for the active business:
 * - the last sync status (with a TEXT label, never colour alone),
 * - how long ago the last sync ran,
 * - a stale-data warning when the last sync is older than the schedule
 *   expects,
 * - a link to the data-sources page.
 *
 * Every string that describes staleness comes from the backend
 * (`freshness.headline`, `freshness.last_sync_text`) so the wording is
 * never invented here, and no financial figure is computed in the UI.
 */

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Clock, RefreshCw, TriangleAlert, CircleCheck } from "lucide-react";

import { apiGet } from "@/lib/api";
import { Freshness, type FreshnessT } from "@/lib/schemas";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/States";

const STATUS_LABEL: Record<FreshnessT["last_status"], string> = {
  never_run: "Not synced yet",
  ok: "Up to date",
  partial: "Partial — some rows rejected",
  failed: "Last sync failed",
};

const STATUS_TONE: Record<FreshnessT["last_status"], "neutral" | "ok" | "warn" | "bad"> = {
  never_run: "neutral",
  ok: "ok",
  partial: "warn",
  failed: "bad",
};

export function FreshnessStrip({ businessId }: { businessId: string }) {
  const freshness = useQuery({
    queryKey: ["freshness", businessId],
    queryFn: () =>
      apiGet(
        `/api/businesses/${businessId}/freshness`,
        Freshness,
      ) as Promise<FreshnessT>,
    enabled: businessId.length > 0,
    refetchInterval: 15_000,
  });

  if (freshness.isLoading) {
    return <Skeleton className="mb-4 h-16 w-full" />;
  }
  // A freshness failure must never hide the dashboard — show nothing and
  // let the rest of the page render.
  if (freshness.error || !freshness.data) return null;

  const f = freshness.data;
  const hasSources = f.source_count > 0;

  return (
    <div
      className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-surface-raised px-3 py-2 text-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-1 text-xs font-medium text-ink-muted">
          Data freshness
        </span>

        {hasSources ? (
          <>
            <Badge tone={STATUS_TONE[f.last_status]}>
              {f.last_status === "ok" ? (
                <CircleCheck size={11} aria-hidden />
              ) : f.any_stale ? (
                <TriangleAlert size={11} aria-hidden />
              ) : null}
              {STATUS_LABEL[f.last_status]}
            </Badge>
            <span className="flex items-center gap-1 text-2xs text-ink-muted">
              <Clock size={11} aria-hidden />
              Last sync: {f.last_sync_text}
            </span>
            {f.sources.reduce((n, s) => n + (s.is_stale ? 1 : 0), 0) > 0 ? (
              <span className="text-2xs text-warn">
                Stale data — one or more sources are older than their schedule.
              </span>
            ) : null}
          </>
        ) : (
          <span className="text-2xs text-ink-muted">
            No data sources connected — this dashboard shows imported data only.
          </span>
        )}
      </div>

      <Link
        href="/data"
        className="flex items-center gap-1 text-2xs text-accent hover:underline"
      >
        <RefreshCw size={11} aria-hidden />
        {hasSources ? "Manage data sources" : "Connect a data source"}
      </Link>
    </div>
  );
}

export default FreshnessStrip;