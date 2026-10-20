# Chapter 12 — Dashboard & Decision UX

> *Component-by-component walkthrough of the two pages that anchor the product —
> the dashboard and the decision detail view.*

This chapter is mostly about the UX discipline, not the chart library. The principle:
**every chart is paired with a plain-English interpretation that ships in the API
response**. The frontend never has to invent a caption.

---

## 12.1 The dashboard architecture

The dashboard page (`apps/web/app/(app)/dashboard/page.tsx`) is the only place where
six server queries run side-by-side. Here is the query → chart wiring:

```
   ┌─────────────────────────────────────────────────────────────────────────┐
   │  DashboardPage                                                          │
   │                                                                         │
   │  useQuery(["dashboard-insights", id]) ──►  Visual[]   ┌────────────┐    │
   │  useQuery(["financial-summary",  id])  ──►  Summary   │  fallback  │    │
   │  useQuery(["alerts",            id])   ──►  Alert[]   │  for       │    │
   │  useQuery(["financing-options", id])   ──►  Match[]   │  MonthSide │    │
   │  useQuery(["scenarios",         id])   ──►  Scenario[]│  Panel     │    │
   │  useQuery(["ai-health"])                ──►  Provider │            │    │
   │                                                  ▼     ▼            │    │
   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐        │    │
   │  │   KpiStrip   │  │ Synthetic    │  │  Recharts grid:      │        │    │
   │  │   (4 KPIs)   │  │ data banner  │  │  • Cash balance      │        │    │
   │  └──────────────┘  └──────────────┘  │  • Revenue/C/Profit  │        │    │
   │                                       │  • Profit vs cash   │        │    │
   │                                       │  • Cost breakdown   │        │    │
   │                                       │  • Sensitivity      │        │    │
   │                                       │  • Scenario compare │        │    │
   │                                       └──────────────────────┘        │    │
   │                                                                         │
   │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐    │    │
   │  │  AlertsPanel   │  │ FinancingPanel │  │  ScenarioCompareView   │    │    │
   │  └────────────────┘  └────────────────┘  └────────────────────────┘    │    │
   │                                                                         │
   │  ┌────────────────────────────────────────────────────────────────┐    │    │
   │  │  MonthSidePanel (on month click)                              │    │    │
   │  │  Uses month detail from cashVisual or buildMonthDetailsFrom… │    │    │
   │  └────────────────────────────────────────────────────────────────┘    │    │
   └─────────────────────────────────────────────────────────────────────────┘

   Click "Explain" anywhere → POST /ai/assistant/chat with _dashboard_context
```

Every chart receives a `Visual` object (`insights/engine.py`) that contains:

- `id`        — stable id (e.g. `cash_balance`, `revenue_costs_profit`)
- `title`     — short heading
- `what_it_shows` — 1-sentence plain English
- `what_to_notice` — 1–2 sentences, the inflections
- `why_it_matters` — 1 sentence, action implication
- `evidence`  — the data payload the chart binds to

The dashboard picks a chart component per `visual_id` and renders the explanation
*next to it*. The visual text is content, not chrome.

---

## 12.2 The KpiStrip — `components/dashboard/KpiStrip.tsx`

Four headline KPIs:

```
   ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
   │  Revenue (MoM)   │  Operating       │  Cash runway     │  Min projected   │
   │                  │  margin          │                  │  cash            │
   │  $124,500        │  12.4%           │  4.2 months      │  $42,000         │
   │  ▲ +5% vs last   │  ▲ +0.8 pt       │  ▼ −0.4 months   │  ▲ +$3,200       │
   └──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

The MoM and "vs last" deltas come from `compute_metrics` outputs over a rolling window;
the KPI strip component reads pre-formatted strings from the `Visual.evidence` payload
and never recomputes them.

---

## 12.3 The chart components

All chart components follow the same pattern:

```typescript
"use client";
import { Visual } from "@/lib/schemas";

export function CashBalanceChart({ visual, hiddenSeries, … }: {
  visual: Visual;
  hiddenSeries?: Set<string>;
  onClickMonth?: (m: string) => void;
}) {
  // 1. pure render of evidence (no fetches, no math)
  // 2. accessibility: chart-level role + table fallback
  // 3. print-friendly: greyscale-safe shape markers
  return (
    <Card>
      <Card.Title>{visual.title}</Card.Title>
      <Card.Subtitle>{visual.what_it_shows}</Card.Subtitle>
      <LineChart …>{/* binding evidence */}</LineChart>
      <Caption>{visual.what_to_notice}</Caption>
      <Footnote>{visual.why_it_matters}</Footnote>
    </Card>
  );
}
```

### `CashBalanceChart.tsx`

- LineChart with two series — `Closing cash` (accent) and `Net cash movement` (info).
- Months with `is_negative` get a **circle + diagonal line marker** (not just a colour
  change) so the chart is greyscale-safe.
- Two reference lines: `y=0` and the business's `minBuffer` (`warn` colour, dashed,
  labelled "1-month buffer").
- `onClickMonth` fires from chart-level click or per-series click; the dashboard uses
  this to open `MonthSidePanel`.

### `RevenueCostsProfitChart.tsx`

- ComposedChart with three series: revenue (area), COGS (stacked bar), opex (stacked bar).
- The "profit" insight is implicit — the gap between the revenue area and the cost
  bars.

### `ProfitCashGapChart.tsx`

- BarChart of operating profit (positive in `ok`, negative in `bad`) versus net cash
  movement.
- This is the only chart that makes the "Profitable but cash-poor" alert *visible*.

### `CostBreakdownChart.tsx`

- BarChart of top expense categories as a percentage of total opex.
- 4-digit-precision cap (`formatNumber` in `lib/format.ts:47`) so a single 8.1234%
  category does not visually crowd the others.

### `SensitivityChart.tsx`

- LineChart with one line per sensitivity axis (SALES_VOLUME, SELLING_PRICE, OPEX,
  COLLECTION_DELAY).
- Default multipliers are `-25%, -10%, 0, +10%, +25%` (`sensitivity.py:24`).

### `ScenarioCompareChart.tsx`

- BarChart of one summary metric across N scenarios, baseline visibly distinct.
- The `Compare` page (`/compare`) uses its own richer table layout — this chart is the
  quick-glance one on the dashboard.

---

## 12.4 The "explanation sits next to the figure" pattern

This is the most distinctive UX choice in the product. Every chart component renders:

```
   ┌────────────────────────────────────────────────────────────────┐
   │  Title                                                          │
   │  Subtitle (1 sentence: what this shows)                         │
   │                                                                 │
   │  ┌──────────────────────────────────────────────────────┐       │
   │  │                                                       │       │
   │  │                  CHART                                │       │
   │  │                                                       │       │
   │  └──────────────────────────────────────────────────────┘       │
   │                                                                 │
   │  Caption — what to notice (1–2 sentences)                       │
   │  Footnote — why it matters (1 sentence)                         │
   └────────────────────────────────────────────────────────────────┘
```

The dashboard is therefore a *self-describing document*. A user can read top-to-bottom
without having to interpret the chart themselves; the chart is the visual evidence for
the prose that's already there.

The Explanations are server-rendered (`Visual.what_it_shows`, etc.):
`insights/engine.py:227` onward. They are *content*, and they are reproducible per
business input — same transactions, same visuals, same prose.

---

## 12.5 The explain-with-AI side panel

Clicking **Explain** on the dashboard posts to `/api/ai/assistant/chat` with a
`_dashboard_context` payload:

```typescript
// dashboard/page.tsx:258
const explain = useMutation({
  mutationFn: ({ question }) =>
    apiPost("/ai/assistant/chat", {
      message: question,
      business_id: businessId,
      _dashboard_context: {
        visuals: dashboardInsights.visuals,    // the full Visual[]
        baselines: financialSummary,
        alerts: alertsData?.alerts ?? [],
        scenarios: scenariosList,
      },
    }, AssistantReplySchema),
});
```

The LLM receives pre-rendered summary strings — never raw transactions. The Assistant
page reads the same `/api/ai/assistant/chat` endpoint but is the only place where the
user has an interactive chat session.

---

## 12.6 The Month Side Panel — `components/dashboard/MonthSidePanel.tsx`

Click any data point on `CashBalanceChart` and a side panel opens with that month's
details. Two sources, one component:

```
   source A (preferred):
     cashVisual.evidence.months[selectedMonth]
       ↑ the per-month detail the dashboard already computed
       ↑ backed by cash_balance_visual evidence

   source B (fallback):
     buildMonthDetailsFromSummary(financialSummary, selectedMonth)
       ↑ summary is horizon-wide, not monthly — this is a degradation path
       ↑ the fallback comment is in the dashboard: "Summary is horizon-wide,
         not monthly" (dashboard/page.tsx:793)
```

The component renders whichever source produced the data and renders an explicit
"horizon-wide approximation" notice when on source B. This is the same honesty rule
applied to chart detail: don't lie, render the source's actual granularity.

---

## 12.7 The decision detail page

`apps/web/app/(app)/decisions/[id]/page.tsx` is the second-most-complex page. It is
*also* where Principle 3 ("rules decide, LLM explains") is encoded visually.

```
┌──────────────────────────────────────────────────────────────────────┐
│  ← back    Decision report                       [Print]  [Explain] │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Verdict: REJECT                                               │  │
│  │  Recommendation:  "One or more hard constraints failed…"       │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─ Binding constraints ──────────────────────────────────────────┐   │
│  │  • NEGATIVE_CLOSING_CASH  HARD  BREACHED  actual −$4,200      │   │
│  │    "Closing cash dropped below zero at month 2…"              │   │
│  │  • MIN_CASH_RESERVE       HARD  BREACHED  actual −$4,200      │   │
│  │    "Closing cash below the configured $10,000 reserve…"        │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─ Rule evaluations (all 8) ────────────────────────────────────┐   │
│  │  Rule                                Sev   Status   Actual  T  │   │
│  │  ─────────────────────────────────────────────────────────────│   │
│  │  NEGATIVE_CLOSING_CASH              HARD  BREACHED  −$4.2k  0  │   │
│  │  MIN_CASH_RESERVE                   HARD  BREACHED  −$4.2k 10k │   │
│  │  CAPACITY_EXCEEDED                  HARD  PASSED    —       —   │   │
│  │  MATERIAL_SHORTAGE                  HARD  PASSED    —       —   │   │
│  │  MIN_PROFIT_MARGIN                  SOFT  WARNING   3.1%   10%  │   │
│  │  NEGATIVE_CONTRIBUTION_MARGIN       SOFT  WARNING   −2.0%  0%   │   │
│  │  UNSOLD_INVENTORY_EXPOSURE          SOFT  PASSED    12%    20%  │   │
│  │  MISSING_CRITICAL_DATA              BLOC  PASSED    —       —   │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─ Laya soft assessment (advisory) ──────────────────────────────┐   │
│  │  Risk category: high                                           │   │
│  │  Feasibility:   2/5                                            │   │
│  │  Aligns with goal: no                                         │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─ Assumptions / Caveats / Missing info ────────────────────────┐   │
│  │  • …                                                           │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─ LLM explanation (lazy, on click) ────────────────────────────┐   │
│  │  [click to load]                                               │   │
│  │  ↑ after click:                                                │   │
│  │  ⚠ "The LLM can only explain. Rule verdicts and binding        │   │
│  │     constraints above are authoritative."                       │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### Specific UX discipline

1. **Verdict first.** The status badge and recommendation appear at the top of the
   page, before any explanations.

2. **Hard rules promoted.** Binding constraints are listed *above* the full rule table.
   A user who skims only the top half sees everything that decided the verdict.

3. **Severity tags are always visible.** Each row in the rule table shows `HARD` /
   `SOFT` / `BLOCKER` next to status. There is no way to mistake the weight of a result.

4. **Laya is visibly advisory.** A small chip on the panel reads *"Advisory"*. The
   three answers are listed without actions attached.

5. **LLM loads on click, not on render.** `POST /decisions/{id}/explain` is fired
   only when the user clicks the button (`page.tsx:67`). The page is fully readable
   without any LLM call, and the LLM has no impact on what is shown if it never gets
   called.

6. **Disclaimer is always visible.** The block above the LLM section ("The LLM can
   only explain. …") is rendered even after a successful explanation completes —
   the disclaimer is part of the LLM panel, not a setup step.

7. **Print is just the verdict.** `.no-print` hides the toolbar, the buttons, the LLM
   panel. What prints is the verdict, the recommendation, the rule table, and the
   caveats. Nothing else.

---

## 12.8 The decision list — `decisions/page.tsx`

A simpler page:

- Two queries: `["decisions", id]` and `["scenarios", id]`
- Action: "Evaluate" requires picking a scenario first; the click reads
  `sc.latest_version_id` (line 73) and sends it as `scenario_version_id` to
  `POST /decisions/evaluate` — the same asymmetry called out in chapter 10.
- Verdict cells render through a single `STATUS_LABELS` / `STATUS_TONES` table (lines
  22-36):

```
   PROCEED              → ok  badge + "Proceed"
   PROCEED_WITH_CAUTION → info badge + "Proceed with caution"
   REVISE               → warn badge + "Revise assumptions"
   INSUFFICIENT_DATA    → neutral badge + "Insufficient data"
   REJECT               → bad badge + "Do not proceed"
```

---

## 12.9 The Simulator page

`apps/web/app/(app)/simulator/page.tsx` is a form-driven scenario builder:

- Inputs are industry-aware (`fieldsFor(industry)` at line 254). Manufacturing inputs
  differ from retail/service inputs.
- "Run" → `POST /scenarios/simulate` (does NOT persist).
- "Save" → `POST /scenarios` (creates v1, returns `ScenarioRead`).
- `ResultPanel` (line 175) renders the `ScenarioResult` rows with `tone()` colouring
  negative numbers red (line 245).

The Engine version is visible in the UI: `Engine 0.1.0 (deterministic)` (line 82),
so the user always knows which engine version produced the result they are looking at.

---

## 12.10 The Compare page

`apps/web/app/(app)/compare/page.tsx` lets the user pick 1–5 scenarios and renders
side-by-side:

- Per-scenario metrics from `POST /scenarios/compare`.
- A second "differences vs baseline" table where the baseline is the first scenario
  picked (line 75).
- USD-only is hard-coded in the formatter (`compare/page.tsx:146`, `:152`); see
  chapter 14 for the multi-currency limitation.

The local `Comparison` / `ComparisonRow` Zod schemas mirror the backend row format,
plus a `_delta` / `_delta_pct` pair of keys for diffs.

---

## 12.11 The Data page

`apps/web/app/(app)/data/page.tsx` is the heaviest data UI:

```
   ┌────────────────────────────────────────────────────────────────────┐
   │  CREDENTIAL_BANNER — credentials are never sent or returned        │
   │  BANNER: "Data is SYNTHETIC"                                       │
   │                                                                    │
   │  Freshness strip (polls /freshness every 5s):                     │
   │    ● source 1 — synced 14m ago (ready)                              │
   │    ● source 2 — synced 2d ago (ready)                               │
   │    ⚠ source 3 — error: path_outside_root (28h ago)                  │
   │                                                                    │
   │  AddSourceCard (form per source type):                             │
   │    file:   path, sheet name, incremental column                    │
   │    sql:    URL, SELECT statement, incremental column                │
   │    schedule: manual / hourly / daily                                │
   │    column_mapping JSON                                              │
   │    secret_ref (NOT rendered in DataSourceRead)                      │
   │                                                                    │
   │  SourceRow per source:                                              │
   │    ┌────────────────────────────────────────────────┐               │
   │    │ Name  …  Schedule  …  Last sync  …             │               │
   │    │ [Test] [Disable] [Sync now] [Edit] [Delete]    │               │
   │    │                                                │               │
   │    │ Recent runs (sub-table polling 5s):            │               │
   │    │   2026-10-20 14:21   added 12  dup 0  rej 0     │               │
   │    │   2026-10-20 14:16   added 0   dup 12 rej 0    │               │
   │    └────────────────────────────────────────────────┘               │
   └────────────────────────────────────────────────────────────────────┘
```

Specific patterns to copy:

1. **Status badge uses text + icon, never colour alone.** A colour-blind user reads
   `Error` and a warning triangle, not a red dot. (data/page.tsx:73-103)

2. **`FreshnessStrip` polls every 5s.** This is the only pageload polling in the app
   outside the Assistant page. `source-runs` sub-table also polls 5s while a sync is
   in flight.

3. **Credentials are bannered explicitly.** The `CREDENTIAL_BANNER` plus the
   schematic disclaimer above the form make it clear that `secret_ref` is server-side
   even if a user pastes one.

---

## 12.12 The Assistant page

`apps/web/app/(app)/assistant/page.tsx` is a chat UI over the LLM provider:

```
   ┌────────────────────────────┬──────────────────────────────────────┐
   │   Chat transcript          │   Provider status                     │
   │                            │     ● Ollama — status: unavailable   │
   │   [user] Why did cash      │            reason: ollama not reachable│
   │          drop in March?    │     ● OpenAI — status: ok            │
   │                            │            model: gpt-4o-mini         │
   │   [assistant]              │            latency: 412ms             │
   │   March saw a larger       │     ● Anthropic — status: misconfig  │
   │   supplier payout land     │            reason: ANTHROPIC_API_KEY │
   │   on day 14, before the    │                                      │
   │   customer payments of     │   Capabilities                       │
   │   day 30…                  │     ● can explain decisions           │
   │                            │     ● can summarise dashboard         │
   │   [Suggest]                │     ● cannot override rules           │
   │   chips:                   │     ● cannot see raw transactions     │
   │   - "What is my runway?"   │                                      │
   │   - "Should I take a       │   "What it will not do"               │
   │      loan?"                │     ● make money decisions            │
   │   - "Explain the March     │     ● access raw data                  │
   │      shortfall"            │     ● override rule verdicts           │
   │                            │                                      │
   │   [Send]                   │                                      │
   └────────────────────────────┴──────────────────────────────────────┘
```

The right rail — *"What it will not do"* — is the user-facing embodiment of Principle 3.
It restates the architectural boundary in the language a stakeholder can read.

---

## 12.13 The Settings page

Four cards, each self-contained:

```
   ┌─ Businesses management ────────────────────────────────────────┐
   │  Name | Industry | Currency | Fiscal Month | Reserve | Margin  │
   │  [Create]                                                      │
   │  Existing businesses (table)                                  │
   │     … [Edit] [Delete]                                          │
   └────────────────────────────────────────────────────────────────┘

   ┌─ AI provider status ──────────────────────────────────────────┐
   │  ProvidersList (rows for each mode, live from /ai/health)    │
   └────────────────────────────────────────────────────────────────┘

   ┌─ Privacy card ───────────────────────────────────────────────┐
   │  copy explaining data flow + AI policy                       │
   └────────────────────────────────────────────────────────────────┘

   ┌─ Appearance ────────────────────────────────────────────────┐
   │  [Light]  [Dark]  [System]   (guarded by mounted flag)       │
   └────────────────────────────────────────────────────────────────┘
```

A `mounted` SSR-guard prevents the theme toggle from mismatching on first paint — same
discipline as the root layout's `suppressHydrationWarning`.

---

## 12.14 Common UX patterns at a glance

| Pattern | Where it appears |
|---|---|
| Three fetch states (`Loading` / `Error` / `Empty`) | every panel in the app |
| Status badge as text + colour, never colour alone | data, decisions, alerts, settings |
| Synthetic-data banner | dashboard, anywhere a demo workspace is selected |
| Pre-rendered explanation next to a chart | every chart on the dashboard |
| LLM disclaimer visible alongside LLM output | decision detail, assistant |
| Greyscale-safe markers (shape + colour, not just colour) | cash balance line chart |
| Print-friendly selectors | dashboard (`body *`), decision detail (`.no-print`) |
| Polling only where freshness matters | `freshness` (5s), `ai-health` (60s) |
| Optimistic mutations only for chat | assistant only — never for financial mutations |

---

*Next: [Chapter 13 — Local development runbook](13-local-runbook.md)*