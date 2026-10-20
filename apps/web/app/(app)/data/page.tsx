"use client";

/**
 * Data sources page.
 *
 * What it does:
 * 1. Lists every data source configured for the current business with
 *    last-sync status, last error, and a "Sync now" action.
 * 2. Lets the user add a source — a CSV/XLSX file from the configured
 *    allowed directory, or a SQL table described by an env-var name.
 *    The credential value is never sent to the server, and the server
 *    never sends it back.
 * 3. Shows run history per source: rows read / added / skipped as
 *    duplicate / rejected.
 *
 * The page never calculates money. It only renders server-computed
 * numbers, and every status carries a text label (never colour alone).
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import {
  Plus,
  PlugZap,
  Trash2,
  PlayCircle,
  FileSpreadsheet,
  Database,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  ShieldAlert,
  Pencil,
} from "lucide-react";

import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import {
  Business,
  DataSource,
  type DataSourceT,
  DataSourceTestResult,
  Freshness,
  type FreshnessT,
  SyncRun,
  SyncRunList,
  type SyncRunT,
  type SyncScheduleT,
  type DataSourceTypeT,
} from "@/lib/schemas";
import { useWorkspace } from "@/components/WorkspaceContext";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";

const SOURCES_PATH = "/api/sources";

const CREDENTIAL_BANNER =
  "File sources must live under the server-configured allowed directory. " +
  "SQL credentials are stored only as env-var names on the server — the value " +
  "is never sent to or returned by this page.";

// ---------------------------------------------------------------------------
// Status helpers — text-first, never colour alone
// ---------------------------------------------------------------------------

type SourceStatus = DataSourceT["last_status"];

const STATUS_LABEL: Record<SourceStatus, string> = {
  never_run: "Not synced yet",
  ok: "OK",
  partial: "Partial — some rows rejected",
  failed: "Failed",
};

function StatusBadge({ status }: { status: SourceStatus }) {
  const tone =
    status === "ok"
      ? "ok"
      : status === "failed"
        ? "bad"
        : status === "partial"
          ? "warn"
          : "neutral";
  const Icon =
    status === "ok"
      ? CircleCheck
      : status === "failed"
        ? CircleAlert
        : status === "partial"
          ? ShieldAlert
          : CircleDashed;
  return (
    <Badge tone={tone}>
      <Icon size={11} aria-hidden />
      {STATUS_LABEL[status]}
    </Badge>
  );
}

function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add-source form
// ---------------------------------------------------------------------------

const SCHEDULES: SyncScheduleT[] = ["manual", "daily", "hourly"];

const DEFAULT_MAPPING = JSON.stringify(
  {
    tx_date: "tx_date",
    amount: "amount",
    direction: "direction",
    category: "category",
    currency: "currency",
    description: "description",
    payment_status: "payment_status",
  },
  null,
  2,
);

function AddSourceCard({
  businessId,
  onCreated,
}: {
  businessId: string;
  onCreated: () => void;
}) {
  const [type, setType] = useState<DataSourceTypeT>("file");
  const [name, setName] = useState("");
  const [schedule, setSchedule] = useState<SyncScheduleT>("daily");
  const [path, setPath] = useState("");
  const [sheetName, setSheetName] = useState("");
  const [table, setTable] = useState("");
  const [schema, setSchema] = useState("");
  const [incrementalKey, setIncrementalKey] = useState("");
  const [secretRef, setSecretRef] = useState("");
  const [mapping, setMapping] = useState(DEFAULT_MAPPING);

  const create = useMutation({
    mutationFn: async () => {
      let columnMapping: Record<string, string>;
      try {
        const parsed: unknown = JSON.parse(mapping);
        if (
          typeof parsed !== "object" ||
          parsed === null ||
          Array.isArray(parsed)
        ) {
          throw new Error("Column mapping must be a JSON object.");
        }
        columnMapping = parsed as Record<string, string>;
      } catch (err) {
        throw new Error(
          err instanceof Error
            ? err.message
            : "Column mapping must be valid JSON.",
        );
      }
      const config: Record<string, unknown> = {};
      if (type === "file") {
        config.path = path.trim();
        if (sheetName.trim()) config.sheet_name = sheetName.trim();
      } else {
        config.table = table.trim();
        if (schema.trim()) config.schema = schema.trim();
      }
      return apiPost(
        SOURCES_PATH,
        {
          business_id: businessId,
          type,
          name: name.trim(),
          config,
          column_mapping: columnMapping,
          incremental_key: incrementalKey.trim() || null,
          schedule,
          enabled: true,
          secret_ref: type === "sql" ? secretRef.trim() || null : null,
        },
        DataSource,
      );
    },
    onSuccess: () => {
      setName("");
      setPath("");
      setSheetName("");
      setTable("");
      setSchema("");
      setIncrementalKey("");
      setSecretRef("");
      onCreated();
    },
  });

  const canSubmit =
    name.trim().length > 0 &&
    (type === "file" ? path.trim().length > 0 : table.trim().length > 0) &&
    (type !== "sql" || secretRef.trim().length > 0);

  return (
    <Card>
      <CardHeader title="Add a data source" />
      <CardBody className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className="text-2xs text-ink-muted">Type</span>
            <Select
              value={type}
              onChange={(e) => setType(e.target.value as DataSourceTypeT)}
            >
              <option value="file">File (CSV / XLSX)</option>
              <option value="sql">SQL database</option>
            </Select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-2xs text-ink-muted">Name</span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Daily POS exports"
              maxLength={200}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-2xs text-ink-muted">Schedule</span>
            <Select
              value={schedule}
              onChange={(e) => setSchedule(e.target.value as SyncScheduleT)}
            >
              {SCHEDULES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </label>
        </div>

        {type === "file" ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className="text-2xs text-ink-muted">
                Path (relative to the allowed directory)
              </span>
              <Input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="daily_transactions.xlsx"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-2xs text-ink-muted">
                Sheet name (XLSX only)
              </span>
              <Input
                value={sheetName}
                onChange={(e) => setSheetName(e.target.value)}
                placeholder="transactions"
              />
            </label>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <label className="flex flex-col gap-1">
              <span className="text-2xs text-ink-muted">Table</span>
              <Input
                value={table}
                onChange={(e) => setTable(e.target.value)}
                placeholder="invoices"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-2xs text-ink-muted">Schema (optional)</span>
              <Input
                value={schema}
                onChange={(e) => setSchema(e.target.value)}
                placeholder="public"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-2xs text-ink-muted">
                Incremental column
              </span>
              <Input
                value={incrementalKey}
                onChange={(e) => setIncrementalKey(e.target.value)}
                placeholder="updated_at"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-2xs text-ink-muted">
                Env-var holding the URL
              </span>
              <Input
                value={secretRef}
                onChange={(e) => setSecretRef(e.target.value)}
                placeholder="MY_DB_URL"
              />
            </label>
          </div>
        )}

        <label className="flex flex-col gap-1">
          <span className="text-2xs text-ink-muted">
            Column mapping — JSON, canonical field → source column
          </span>
          <textarea
            value={mapping}
            onChange={(e) => setMapping(e.target.value)}
            spellCheck={false}
            className="min-h-[110px] w-full rounded border border-line bg-surface-raised px-2 py-1 font-mono text-2xs outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          />
        </label>

        {create.error ? (
          <p role="alert" className="text-2xs text-bad">
            {create.error instanceof Error
              ? create.error.message
              : "Could not create the source."}
          </p>
        ) : null}

        <div className="flex justify-end">
          <Button
            onClick={() => create.mutate()}
            disabled={!canSubmit || create.isPending}
          >
            <Plus size={14} aria-hidden />
            {create.isPending ? "Creating…" : "Create source"}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Run history
// ---------------------------------------------------------------------------

function RunHistoryTable({ sourceId }: { sourceId: string }) {
  const runs = useQuery({
    queryKey: ["source-runs", sourceId],
    queryFn: () =>
      apiGet(`${SOURCES_PATH}/${sourceId}/runs?limit=20`, SyncRunList),
    refetchInterval: 5_000,
  });

  if (runs.isLoading) return <LoadingBlock rows={2} />;
  if (runs.error) {
    return (
      <ErrorState
        title="Could not load run history"
        description={
          runs.error instanceof Error ? runs.error.message : undefined
        }
      />
    );
  }
  const items = runs.data?.items ?? [];
  if (items.length === 0) {
    return <p className="text-2xs text-ink-muted">No runs recorded yet.</p>;
  }
  return (
    <Table>
      <THead>
        <TR>
          <TH>Started</TH>
          <TH>Status</TH>
          <TH>Trigger</TH>
          <TH align="right">Read</TH>
          <TH align="right">Added</TH>
          <TH align="right">Duplicate</TH>
          <TH align="right">Rejected</TH>
        </TR>
      </THead>
      <TBody>
        {items.map((r: SyncRunT) => (
          <TR key={r.id}>
            <TD>{new Date(r.started_at).toLocaleString()}</TD>
            <TD>{r.status}</TD>
            <TD>{r.trigger}</TD>
            <TD align="right">{r.rows_read}</TD>
            <TD align="right">{r.rows_added}</TD>
            <TD align="right">{r.rows_skipped_duplicate}</TD>
            <TD align="right">{r.rows_rejected}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Source row
// ---------------------------------------------------------------------------

function SourceRow({
  source,
  onChanged,
}: {
  source: DataSourceT;
  onChanged: () => void;
}) {
  const [showRuns, setShowRuns] = useState(false);

  const sync = useMutation({
    mutationFn: () => apiPost(`${SOURCES_PATH}/${source.id}/sync`, {}, SyncRun),
    onSuccess: onChanged,
  });
  const remove = useMutation({
    mutationFn: () => apiDelete(`${SOURCES_PATH}/${source.id}`),
    onSuccess: onChanged,
  });
  const toggle = useMutation({
    mutationFn: () =>
      apiPatch(
        `${SOURCES_PATH}/${source.id}`,
        { enabled: !source.enabled },
        DataSource,
      ),
    onSuccess: onChanged,
  });
  const test = useMutation({
    mutationFn: () => apiPost(`${SOURCES_PATH}/${source.id}/test`, {}, DataSourceTestResult),
  });

  const Icon = source.type === "file" ? FileSpreadsheet : Database;

  return (
    <Card>
      <CardBody className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <Icon
              size={18}
              className="mt-0.5 shrink-0 text-ink-muted"
              aria-hidden
            />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{source.name}</span>
                <Badge>{source.schedule}</Badge>
                {!source.enabled ? <Badge tone="warn">disabled</Badge> : null}
              </div>
              <p className="mt-0.5 text-2xs text-ink-muted">
                Incremental column:{" "}
                {source.incremental_key || "none (files use row hashes)"}
              </p>
              <p className="text-2xs text-ink-muted">
                Last sync:{" "}
                {source.last_sync_at
                  ? new Date(source.last_sync_at).toLocaleString()
                  : "never"}
              </p>
              {source.last_error_summary ? (
                <p className="mt-1 text-2xs text-bad">
                  Last error: {source.last_error_summary}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={source.last_status} />
            <Button
              variant="secondary"
              onClick={() => test.mutate()}
              disabled={test.isPending}
            >
              <PlugZap size={14} aria-hidden />
              {test.isPending ? "Testing…" : "Test"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => toggle.mutate()}
              disabled={toggle.isPending}
            >
              <Pencil size={14} aria-hidden />
              {source.enabled ? "Disable" : "Enable"}
            </Button>
            <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
              <PlayCircle size={14} aria-hidden />
              {sync.isPending ? "Syncing…" : "Sync now"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              aria-label={`Delete ${source.name}`}
            >
              <Trash2 size={14} aria-hidden />
            </Button>
          </div>
        </div>

        {test.data ? (
          <div className="rounded border border-line bg-surface-sunken px-3 py-2">
            <p className="text-2xs font-medium">
              Test result:{" "}
              {test.data.status === "ok"
                ? "OK"
                : `Failed — ${test.data.last_message ?? "see server logs"}`}
            </p>
            {test.data.headers.length > 0 ? (
              <p className="mt-1 text-2xs text-ink-muted">
                Columns found: {test.data.headers.slice(0, 8).join(", ")}
                {test.data.headers.length > 8 ? "…" : ""}
              </p>
            ) : null}
            {test.data.sample_rows.slice(0, 3).map((s, i) => (
              <p key={i} className="mt-0.5 truncate text-2xs text-ink-muted">
                · {s}
              </p>
            ))}
            <p className="mt-1 text-2xs text-ink-muted">
              Rows in the preview batch: {test.data.row_count_preview}
            </p>
          </div>
        ) : null}

        <div>
          <button
            type="button"
            className="text-2xs text-accent hover:underline"
            aria-expanded={showRuns}
            onClick={() => setShowRuns((v) => !v)}
          >
            {showRuns ? "Hide run history" : "Show run history"}
          </button>
          {showRuns ? (
            <div className="mt-2">
              <RunHistoryTable sourceId={source.id} />
            </div>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Freshness strip
// ---------------------------------------------------------------------------

function FreshnessStrip({ businessId }: { businessId: string }) {
  const freshness = useQuery({
    queryKey: ["freshness", businessId],
    queryFn: () =>
      apiGet(`/api/businesses/${businessId}/freshness`, Freshness),
    enabled: businessId.length > 0,
    refetchInterval: 5_000,
  });

  if (freshness.isLoading) return <LoadingBlock rows={2} />;
  if (freshness.error) {
    return (
      <ErrorState
        title="Could not load data freshness"
        description={
          freshness.error instanceof Error ? freshness.error.message : undefined
        }
      />
    );
  }
  const f = freshness.data as FreshnessT | undefined;
  if (!f) return null;

  if (f.source_count === 0) {
    return (
      <Card>
        <CardHeader title="Data freshness" />
        <CardBody>
          <p className="text-sm text-ink-muted">
            No data sources connected yet. Add one below and the dashboard,
            alerts, financing options and interpretations will pick up new rows
            after the next sync.
          </p>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title="Data freshness" />
      <CardBody className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div>
          <p className="text-2xs text-ink-muted">Status</p>
          <div className="mt-1">
            <StatusBadge status={f.last_status} />
          </div>
          <p className="mt-1 text-2xs text-ink-muted">{f.headline}</p>
        </div>
        <div>
          <p className="text-2xs text-ink-muted">Last sync</p>
          <p className="mt-1 text-sm font-medium">{f.last_sync_text}</p>
          {f.last_sync_at ? (
            <p className="text-2xs text-ink-muted">
              {new Date(f.last_sync_at).toLocaleString()}
            </p>
          ) : null}
        </div>
        <div>
          <p className="text-2xs text-ink-muted">
            Connected sources ({f.source_count})
          </p>
          <ul className="mt-1 flex flex-col gap-0.5">
            {f.sources.map((s) => (
              <li key={s.id} className="text-2xs text-ink-muted">
                {s.name} — {s.last_sync_text}
                {s.is_stale ? (
                  <Badge tone="warn" className="ml-1">
                    stale
                  </Badge>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DataPage() {
  const { businessId } = useWorkspace();
  const qc = useQueryClient();

  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });
  const effectiveId = businessId ?? businesses.data?.[0]?.id ?? "";

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ["sources"] });
    qc.invalidateQueries({ queryKey: ["freshness"] });
  };

  const sources = useQuery({
    queryKey: ["sources", effectiveId],
    queryFn: () =>
      apiGet(
        `${SOURCES_PATH}?business_id=${encodeURIComponent(effectiveId)}`,
        z.array(DataSource),
      ),
    enabled: effectiveId.length > 0,
  });

  const items = sources.data ?? [];

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="rounded border border-line bg-surface-sunken px-3 py-2 text-2xs text-ink-muted">
        {CREDENTIAL_BANNER}
      </p>

      <FreshnessStrip businessId={effectiveId} />

      {effectiveId ? (
        <AddSourceCard businessId={effectiveId} onCreated={refreshAll} />
      ) : null}

      {sources.isLoading ? <LoadingBlock rows={4} /> : null}

      {sources.error ? (
        <ErrorState
          title="Could not load data sources"
          description={
            sources.error instanceof Error ? sources.error.message : undefined
          }
        />
      ) : null}

      {!sources.isLoading && !sources.error && effectiveId && items.length === 0 ? (
        <EmptyState
          title="No data sources configured for this business"
          description="Add one with the form above. New rows from a connected source appear on the dashboard after the next sync."
        />
      ) : null}

      <div className="flex flex-col gap-3">
        {items.map((s) => (
          <SourceRow key={s.id} source={s} onChanged={refreshAll} />
        ))}
      </div>
    </div>
  );
}