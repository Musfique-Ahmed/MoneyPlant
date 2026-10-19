"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { z } from "zod";
import { apiGet, apiPatch, apiPost } from "@/lib/api";
import { Business, Currency, Industry, ProviderHealth } from "@/lib/schemas";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { formatDateISO, formatMoney } from "@/lib/format";
import { useWorkspace } from "@/components/WorkspaceContext";
import { useTheme } from "next-themes";
import {
  Building2,
  Eye,
  EyeOff,
  Lock,
  Monitor,
  Moon,
  Server,
  Sparkles,
  Sun,
  TriangleAlert,
  CheckCircle2,
  XCircle,
} from "lucide-react";

const ProviderList = z.array(ProviderHealth);

const INDUSTRY_DESCRIPTIONS: Record<z.infer<typeof Industry>, string> = {
  manufacturing: "Material + production + finished inventory. Most fields; uses material_waste_pct and capacity cap.",
  retail: "Single SKU line, shrinkage, supplier credit, customer credit.",
  wholesale: "Bulk purchase, large customer payment delays, no retail shrinkage.",
  service: "Billable hours × utilization, project revenue optional, labor cost per hour.",
  food: "Like retail with perishable waste (shrinkage_pct).",
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const { businessId, setBusinessId } = useWorkspace();

  const businesses = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiGet("/api/businesses", z.array(Business)),
  });

  const activeId = businessId ?? businesses.data?.[0]?.id ?? null;
  const active = businesses.data?.find((b) => b.id === activeId) ?? null;

  const providers = useQuery({
    queryKey: ["ai-health"],
    queryFn: () => apiGet("/api/ai/health", ProviderList),
  });

  return (
    <div className="space-y-4 px-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <Badge tone="neutral">
          <Lock size={12} /> Local-first by design
        </Badge>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <BusinessesCard
          businesses={businesses.data ?? []}
          isLoading={businesses.isLoading}
          isError={!!businesses.isError}
          errorMessage={String((businesses.error as Error | undefined)?.message ?? "")}
          activeId={activeId}
          onSelect={(id) => setBusinessId(id)}
          onChanged={() => qc.invalidateQueries({ queryKey: ["businesses"] })}
        />

        <PrivacyCard />
        <AppearanceCard />
      </div>

      <Card>
        <CardHeader
          title="AI providers"
          description="Probed live. The active provider is whatever currently reports healthy."
        />
        <CardBody>
          {providers.isLoading ? (
            <Skeleton className="h-16" />
          ) : providers.isError ? (
            <ErrorState title="Could not load providers" />
          ) : !providers.data || providers.data.length === 0 ? (
            <p className="text-sm text-ink-muted">No providers are configured.</p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Mode</TH>
                  <TH>Model</TH>
                  <TH>Status</TH>
                  <TH align="right">Latency</TH>
                  <TH>Last checked</TH>
                  <TH>Detail</TH>
                </TR>
              </THead>
              <TBody>
                {providers.data.map((p) => (
                  <TR key={`${p.mode}-${p.model}`}>
                    <TD>
                      <div className="flex items-center gap-1.5 font-medium">
                        {p.mode === "local" ? <Server size={12} /> : <Sparkles size={12} />}
                        {labelFor(p.mode)}
                      </div>
                    </TD>
                    <TD className="font-mono text-xs">{p.model}</TD>
                    <TD>
                      <Badge tone={p.status === "ok" ? "ok" : p.status === "misconfigured" ? "warn" : "bad"}>
                        {p.status === "ok" ? (
                          <CheckCircle2 size={10} />
                        ) : (
                          <XCircle size={10} />
                        )}
                        {p.status}
                      </Badge>
                    </TD>
                    <TD align="right">{p.latency_ms !== null ? `${p.latency_ms} ms` : "—"}</TD>
                    <TD className="text-ink-muted">{new Date(p.checked_at).toLocaleTimeString()}</TD>
                    <TD className="text-ink-muted">{p.detail ?? "—"}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      {active && <BusinessSettingsCard business={active} onChanged={() => qc.invalidateQueries({ queryKey: ["businesses"] })} />}
    </div>
  );
}

function BusinessesCard({
  businesses,
  isLoading,
  isError,
  errorMessage,
  activeId,
  onSelect,
  onChanged,
}: {
  businesses: z.infer<typeof Business>[];
  isLoading: boolean;
  isError: boolean;
  errorMessage: string;
  activeId: string | null;
  onSelect: (id: string) => void;
  onChanged: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState<z.infer<typeof Industry>>("retail");
  const [currency, setCurrency] = useState<z.infer<typeof Currency>>("USD");
  const [fiscalStart, setFiscalStart] = useState<number>(1);
  const [reserve, setReserve] = useState<string>("0");
  const [targetMargin, setTargetMargin] = useState<string>("0.1");
  const [maxExposure, setMaxExposure] = useState<string>("0.25");

  const createMut = useMutation({
    mutationFn: () =>
      apiPost(
        "/api/businesses",
        {
          name: name.trim(),
          industry,
          currency,
          fiscal_year_start_month: fiscalStart,
          locale: "en-US",
          min_cash_reserve: reserve,
          target_operating_margin: targetMargin,
          max_unsold_inventory_exposure_pct: maxExposure,
        },
        Business
      ),
    onSuccess: () => {
      setCreating(false);
      setName("");
      onChanged();
    },
  });

  return (
    <Card>
      <CardHeader
        title="Businesses"
        description="Each business is its own workspace, scenario set, and rule thresholds."
        actions={
          <Button
            size="sm"
            variant={creating ? "secondary" : "primary"}
            onClick={() => setCreating((v) => !v)}
            iconLeft={creating ? <EyeOff size={14} /> : <Building2 size={14} />}
          >
            {creating ? "Cancel" : "New business"}
          </Button>
        }
      />
      <CardBody>
        {isLoading ? (
          <Skeleton className="h-16" />
        ) : isError ? (
          <ErrorState title="Could not load businesses" description={errorMessage} />
        ) : businesses.length === 0 ? (
          <EmptyState title="No businesses yet" description="Create one to start importing and simulating." />
        ) : (
          <ul className="space-y-2 text-sm">
            {businesses.map((b) => (
              <li
                key={b.id}
                className="flex items-center justify-between rounded border border-line p-2"
              >
                <div>
                  <div className="font-medium">{b.name}</div>
                  <div className="text-xs text-ink-muted">
                    {b.industry} · {b.currency} · fiscal start month {b.fiscal_year_start_month}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {activeId === b.id ? (
                    <Badge tone="accent">Active</Badge>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => onSelect(b.id)}>
                      Make active
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        {creating && (
          <div className="mt-4 space-y-3 border-t border-line pt-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Input
                label="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Main Street Boutique"
              />
              <Select
                label="Industry"
                value={industry}
                onChange={(e) => setIndustry(e.target.value as z.infer<typeof Industry>)}
                hint={INDUSTRY_DESCRIPTIONS[industry]}
              >
                {Object.keys(INDUSTRY_DESCRIPTIONS).map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </Select>
              <Select
                label="Currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value as z.infer<typeof Currency>)}
              >
                {["USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD"].map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
              <Input
                label="Fiscal year start month"
                type="number"
                min={1}
                max={12}
                value={fiscalStart}
                onChange={(e) => setFiscalStart(Number(e.target.value))}
              />
              <Input
                label="Minimum cash reserve"
                prefix={currency}
                value={reserve}
                onChange={(e) => setReserve(e.target.value)}
                hint="Rule threshold: closing cash must stay above this."
              />
              <Input
                label="Target operating margin"
                value={targetMargin}
                onChange={(e) => setTargetMargin(e.target.value)}
                hint="Decimal. 0.1 = 10%."
              />
              <Input
                label="Max unsold inventory exposure"
                value={maxExposure}
                onChange={(e) => setMaxExposure(e.target.value)}
                hint="Decimal share of revenue."
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setCreating(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => createMut.mutate()}
                loading={createMut.isPending}
                disabled={!name.trim()}
              >
                Create
              </Button>
            </div>
            {createMut.isError && (
              <ErrorState title="Could not create" description={String((createMut.error as Error).message)} />
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function PrivacyCard() {
  return (
    <Card>
      <CardHeader
        title="Privacy"
        description="How your data is handled. Plain language, no marketing copy."
      />
      <CardBody>
        <ul className="space-y-2 text-sm text-ink-muted">
          <li className="flex items-start gap-2">
            <Lock size={14} className="mt-0.5 shrink-0 text-ok" />
            All transactions, scenarios, and rule verdicts live in the local database. They never leave your machine unless you configure an external LLM.
          </li>
          <li className="flex items-start gap-2">
            <Eye size={14} className="mt-0.5 shrink-0 text-info" />
            In local mode (Ollama), the assistant sends only the structured business summary, not raw CSV rows.
          </li>
          <li className="flex items-start gap-2">
            <EyeOff size={14} className="mt-0.5 shrink-0 text-warn" />
            In API mode (OpenAI / Anthropic), the same structured context is sent over HTTPS. Configure your key in the backend `.env`; it is never stored in the frontend.
          </li>
          <li className="flex items-start gap-2">
            <TriangleAlert size={14} className="mt-0.5 shrink-0 text-bad" />
            There is no silent fallback. If the selected provider is unhealthy, the assistant shows an actionable error.
          </li>
        </ul>
        <p className="mt-3 text-xs text-ink-subtle">
          The green/red status in the AI providers table is a live probe, not a stored value.
        </p>
      </CardBody>
    </Card>
  );
}

function AppearanceCard() {
  // Mirror the ThemeToggle's mounted guard so the active choice is stable
  // across SSR and the first client render.
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const choices: Array<{ value: "light" | "dark" | "system"; label: string; icon: React.ReactNode }> = [
    { value: "light", label: "Light", icon: <Sun size={14} /> },
    { value: "dark", label: "Dark", icon: <Moon size={14} /> },
    { value: "system", label: "System", icon: <Monitor size={14} /> },
  ];

  return (
    <Card>
      <CardHeader
        title="Appearance"
        description="Choose how MoneyPlant looks. System follows your OS preference."
      />
      <CardBody>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Theme">
          {choices.map((c) => {
            const active = mounted && theme === c.value;
            return (
              <Button
                key={c.value}
                size="sm"
                variant={active ? "primary" : "secondary"}
                iconLeft={c.icon}
                onClick={() => setTheme(c.value)}
                role="radio"
                aria-checked={active}
                disabled={!mounted}
              >
                {c.label}
              </Button>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-ink-subtle">
          Your choice is stored locally. The top bar also has a quick toggle.
        </p>
      </CardBody>
    </Card>
  );
}

function BusinessSettingsCard({
  business,
  onChanged,
}: {
  business: z.infer<typeof Business>;
  onChanged: () => void;
}) {
  const [reserve, setReserve] = useState(business.min_cash_reserve);
  const [margin, setMargin] = useState(business.target_operating_margin);
  const [exposure, setExposure] = useState(business.max_unsold_inventory_exposure_pct);
  const [name, setName] = useState(business.name);

  const save = useMutation({
    mutationFn: () =>
      apiPatch(
        `/api/businesses/${business.id}`,
        {
          name: name.trim() || business.name,
          min_cash_reserve: reserve,
          target_operating_margin: margin,
          max_unsold_inventory_exposure_pct: exposure,
        },
        Business
      ),
    onSuccess: () => onChanged(),
  });

  return (
    <Card>
      <CardHeader
        title={`Active business: ${business.name}`}
        description={`Created ${formatDateISO(business.created_at)} · ${formatMoney(business.min_cash_reserve, business.currency)} reserve · ${(Number(business.target_operating_margin) * 100).toFixed(1)}% target margin`}
        actions={
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!save.isIdle && save.isPending}>
            Save
          </Button>
        }
      />
      <CardBody>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input
            label="Minimum cash reserve"
            prefix={business.currency}
            value={reserve}
            onChange={(e) => setReserve(e.target.value)}
            hint="Closing cash must stay above this. Used by the MIN_CASH_RESERVE rule."
          />
          <Input
            label="Target operating margin"
            value={margin}
            onChange={(e) => setMargin(e.target.value)}
            hint="Decimal. 0.1 = 10%."
          />
          <Input
            label="Max unsold inventory exposure"
            value={exposure}
            onChange={(e) => setExposure(e.target.value)}
            hint="Decimal share of revenue. Used by UNSOLD_INVENTORY_EXPOSURE."
          />
        </div>
        {save.isError && (
          <div className="mt-3">
            <ErrorState title="Save failed" description={String((save.error as Error).message)} />
          </div>
        )}
        {save.isSuccess && (
          <p className="mt-2 text-xs text-ok">
            <CheckCircle2 size={12} className="inline" /> Saved.
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function labelFor(mode: string): string {
  switch (mode) {
    case "local":
      return "Local (Ollama)";
    case "openai":
      return "OpenAI";
    case "anthropic":
      return "Anthropic";
    default:
      return mode;
  }
}
