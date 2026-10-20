# Chapter 11 — Web Architecture

> *Next.js App Router, TanStack Query for server state, Zustand for exactly one piece of
> client state, and a Zod mirror that makes API drift loud.*

The frontend is a thin, honest renderer. It owns layout, interaction, and presentation.
It does not own a single financial number.

---

## 11.1 The route tree

```
   apps/web/app/
   ├── layout.tsx                 ← root: <html>, Inter font, dark-mode class
   ├── page.tsx                   ← static landing (hero + 4 pillars)
   ├── providers.tsx              ← QueryClientProvider + ThemeProvider
   │
   └── (app)/                     ← route group: the application
       ├── layout.tsx             ← wraps children in <AppShell>
       │
       ├── dashboard/page.tsx     ← 6 queries, 6 charts, KPI strip, alerts
       ├── data/page.tsx          ← DataSource CRUD + import + freshness
       ├── simulator/page.tsx     ← industry-aware scenario builder
       ├── decisions/
       │   ├── page.tsx           ← list + evaluate
       │   └── [id]/page.tsx      ← detail + explain
       ├── compare/page.tsx       ← 1–5 scenarios side by side
       ├── financing/page.tsx     ← thin shell → <FinancingPanel>
       ├── assistant/page.tsx     ← chat + provider status
       └── settings/page.tsx      ← business CRUD, privacy, providers, appearance
```

The `(app)` group name is a Next.js convention: parentheses mean "do not affect the URL
path". `/app/dashboard` is served at `/dashboard`.

### Root layout — `app/layout.tsx`

```typescript
export const metadata = { title: "…", description: "…" };

<html lang="en" className={inter.variable} suppressHydrationWarning>
  <body className="min-h-screen bg-surface text-ink antialiased">
    <Providers>{children}</Providers>
  </body>
</html>
```

`suppressHydrationWarning` is on `<html>` because `next-themes` writes a class to it
before React hydrates. Without it, every page load logs a hydration mismatch.

`Providers` (`app/providers.tsx`) is a client component holding two contexts:

```typescript
"use client";

export function Providers({ children }) {
  const [client] = useState(() => createQueryClient());   // built once
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}
```

`useState(() => …)` rather than `createQueryClient()` directly: constructing a new
`QueryClient` on every render would discard the cache on every render.

---

## 11.2 State: three kinds, three owners

This is the most important discipline in the frontend. There are exactly three kinds of
state and each has exactly one owner.

```
┌────────────────────────────────────────────────────────────────────────┐
│  SERVER STATE      → TanStack Query                                    │
│                     anything that came from /api and can go stale      │
│                     queries: ["dashboard-insights", id], ["scenarios",…]│
│                     owner: useQuery / useMutation                      │
├────────────────────────────────────────────────────────────────────────┤
│  GLOBAL CLIENT     → Zustand (WorkspaceContext)                       │
│                     exactly one field: the active business id          │
│                     { businessId: string | null, setBusinessId: fn }   │
│                     owner: components/WorkspaceContext.tsx             │
├────────────────────────────────────────────────────────────────────────┤
│  LOCAL UI STATE    → useState / useReducer                             │
│                     selectedMonth, dialog open, chat draft,            │
│                     selected scenario ids, form fields                 │
│                     owner: the component that renders them             │
└────────────────────────────────────────────────────────────────────────┘
```

**There is no Redux. There is no Context for server data. There is no local state that
duplicates a query result.**

The classic failure this prevents:

```
   ❌  const [alerts, setAlerts] = useState<Alert[]>([])
       useEffect(() => { fetch(...).then(d => setAlerts(d)) }, [businessId])
       // → stale on refetch, no loading state, no error state, races on switch

   ✅  const { data, isLoading, error } = useQuery({
         queryKey: ["alerts", businessId],
         queryFn:  () => apiGet(`/businesses/${businessId}/alerts`, AlertsSchema),
         enabled:  Boolean(businessId),
       })
       // → cache keyed by business, loading + error states for free,
       //   switching business invalidates automatically
```

### `WorkspaceContext` — a Zustand store, not a React Context

```typescript
// apps/web/components/WorkspaceContext.tsx:5
import { create } from "zustand";

type WorkspaceState = {
  businessId: string | null;
  setBusinessId: (id: string) => void;
};

export const useWorkspace = create<WorkspaceState>((set) => ({
  businessId: null,
  setBusinessId: (businessId) => set({ businessId }),
}));
```

Despite the filename, this is a **Zustand store**, not React Context. The naming is
historical. The rationale:

- Exactly one workspace is active at a time — there is no tree-scoped provider value to
  thread.
- `create()` gives a module-level singleton with no provider ceremony.
- Components that need it call `useWorkspace((s) => s.businessId)` and re-render only
  when that field changes (Zustand's selector subscription).

Using a real React Context would require a provider wrapping the whole tree and would
re-render every consumer on any change. For one field, Zustand is the smaller, sharper
tool.

> **Do not "fix" this to a real Context** unless you are also introducing a second
> independently-scoped workspace (e.g. multi-tenant preview). At that point the Context
> becomes load-bearing and the rename is warranted.

---

## 11.3 The fetch layer — `lib/api.ts`

```typescript
export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

const BASE = typeof window === "undefined"
  ? (process.env.NEXT_PUBLIC_API_BASE_URL ?? "")
  : "";                                        // relative URLs in the browser

async function apiSend(path, init): Promise<unknown> { … }

export async function apiGet<T>(path, schema: ZodSchema<T>, init?): Promise<T>
export async function apiPost<T>(path, body: unknown, schema: ZodSchema<T>, init?): Promise<T>
export async function apiPatch<T>(path, body: unknown, schema: ZodSchema<T>, init?): Promise<T>
export async function apiPostForm<T>(path, form: FormData, schema: ZodSchema<T>): Promise<T>
export async function apiDelete(path: string): Promise<void>
```

Four things worth knowing:

1. **`BASE` is only used server-side.** In the browser the path is relative, so the
   frontend never hard-codes a backend hostname. This is what makes the split-deployment
   shape in chapter 02 work with no rebuild.

2. **Every response is schema-parsed.** `schema.parse(res)` on the way out. Drift fails
   loudly — see §11.4.

3. **`apiDelete` is separate** because a `204 No Content` has an empty body, and
   `schema.parse(undefined)` would throw. Deletions return `void`.

4. **Body is JSON-encoded only when `body !== undefined`** (`api.ts:67`), so
   `apiPost(path, undefined, schema)` is a valid "trigger this action" call.

---

## 11.4 The Zod mirror — the contract

```
   backend/app/schemas/*.py            apps/web/lib/schemas.ts
   ┌────────────────────┐              ┌────────────────────┐
   │  Pydantic v2       │   HTTP/JSON  │  Zod               │
   │  (source of truth) │ ───────────► │  (client mirror)   │
   └────────────────────┘              └────────────────────┘
             │                                     │
             └──────────────┬──────────────────────┘
                            ▼
                   both parse the same payload
                   disagreement = throw
```

### Money fields are strings

```typescript
// lib/format.ts:8
export const DecimalString = z.string().regex(/^-?\d+(\.\d+)?$/);
```

Every money field in `lib/schemas.ts` is `DecimalString`, not `z.number()`. This is
deliberate and load-bearing:

- Pydantic serialises `Decimal` as a string (`"1234.56"`) to preserve precision.
- If the Zod schema said `z.number()`, then `1234.56` would already have lost precision
  before Zod could object.
- `DecimalString` forces the client to treat money as text until `formatMoney` renders
  it for a human.

### The intentional omission

```typescript
// lib/schemas.ts:396 — DataSource
export const DataSourceSchema = z.object({
  id: z.string(),
  business_id: z.string(),
  name: z.string(),
  type: z.enum(["file", "sql"]),
  config: z.record(z.unknown()),
  column_mapping: z.record(z.string()),
  enabled: z.boolean(),
  schedule: z.enum(["manual", "hourly", "daily"]),
  last_sync_at: z.string().nullable(),
  // … no secret_ref — by design
});
```

Zod's default behaviour is to **strip** unknown keys, so even if the backend leaked
`secret_ref`, `DataSourceSchema.parse()` would drop it before it reached a component.
The credential boundary is enforced at the type layer.

### The regression net — `lib/schemas.test.ts`

The test file asserts:

- representative payloads parse successfully;
- malformed payloads fail with the expected Zod path;
- `DecimalString` rejects `"1,234.56"` (comma) and `"abc"`;
- the `overall_status` union rejects an unknown status.

If you change a backend schema without updating the mirror, this test fails *and*
`npm run typecheck` fails (types are inferred from the Zod schemas).

---

## 11.5 Query conventions

### Keying by business id

Every server-state query includes `businessId` in its key:

```typescript
useQuery({
  queryKey: ["decisions", businessId],
  queryFn:  () => apiGet(`/decisions?business_id=${businessId}`, DecisionsSchema),
  enabled:  Boolean(businessId),
});
```

Switching workspaces therefore invalidates every dependent query automatically. No
manual `invalidateQueries` on switch.

### Polling cadence

| Query | Cadence | Why |
|---|---|---|
| `["freshness", id]` | 5s (`data/page.tsx:560`) | Sync can complete while the page is open |
| `["source-runs", sourceId]` | 5s (`data/page.tsx:360`) | Run counters update live |
| `["ai-health"]` | 60s (`assistant/page.tsx:48`) | Provider availability changes slowly |
| everything else | default (no interval) | Cached until invalidated |

Polling is deliberately **absent** from the dashboard. The dashboard is a snapshot; the
Data page is a monitor.

### Mutations and invalidation

```typescript
const sync = useMutation({
  mutationFn: () => apiPost(`/sources/${sourceId}/sync`, undefined, SyncRunSchema),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["source-runs", sourceId] });
    queryClient.invalidateQueries({ queryKey: ["freshness", businessId] });
    queryClient.invalidateQueries({ queryKey: ["dashboard-insights", businessId] });
  },
});
```

A successful sync invalidates the run counters, the freshness strip, **and** the
dashboard. That last one is the important part: new transactions change the computed
metrics, so the dashboard must be recomputed.

### Optimistic updates — used sparingly

The assistant chat uses one (`assistant/page.tsx:66-108`):

```
   1. append a "pending" ChatTurn to local state
   2. send the mutation
   3. on success → replace the pending turn with the real reply
   4. on error   → replace the pending turn with an error turn
```

This is appropriate for chat (perceived latency matters, and the server state is not
shared). It is *not* used for financial mutations — a decision or a scenario should not
render optimistically, because the whole point is that the number is server-computed.

---

## 11.6 Styling — tokens, not classes

`tailwind.config.ts` maps Tailwind colour utilities onto CSS variables so the whole UI
re-themes from one place:

```typescript
colors: {
  surface: {
    DEFAULT: "rgb(var(--color-surface) / <alpha-value>)",
    sunken:  "rgb(var(--color-surface-sunken) / <alpha-value>)",
    raised:  "rgb(var(--color-surface-raised) / <alpha-value>)",
  },
  ink:     { DEFAULT: "…", muted: "…", subtle: "…", inverse: "…" },
  line:    "…",
  accent:  { DEFAULT: "…", hover: "…", soft: "…" },
  ok: "…", warn: "…", bad: "…", info: "…",
}
```

Rules:

- **Never** `bg-gray-100` or `text-slate-700`. Use `bg-surface-raised`, `text-ink-muted`.
- Semantic names only: `ok` / `warn` / `bad` / `info`, never `green` / `yellow` / `red`.
  A status colour change is a config change, not a code change.
- Type scale: `2xs` (11px) → `3xl` (30px) on a 1.2 ratio, base 14px.
- Two elevations only (`elev1`, `elev2`), one transition duration (150ms).

The full visual contract is in [`../DESIGN_DECISIONS.md`](../DESIGN_DECISIONS.md).

### Colour is never the only signal

Every status is conveyed by **text first, colour second**:

```typescript
// data/page.tsx:73-103 — status badge
Critical   → icon + "Critical"   + red
Warning    → icon + "Warning"    + amber
OK / Ready → icon + "Ready"      + green
```

This is an accessibility requirement, not a style preference. A colour-blind user, a
greyscale print, or a screen reader all still get the status from the text.

The same rule appears in the charts: `CashBalanceChart.tsx:88-108` marks negative
months with a **circle plus a diagonal line**, not just a red stroke, so the negative
region survives greyscale printing.

---

## 11.7 The component inventory

### UI primitives — `components/ui/`

| Component | Purpose |
|---|---|
| `Button.tsx` | variants: primary / secondary / ghost / danger; sizes |
| `Card.tsx` | surface + padding + optional title/action slot |
| `Badge.tsx` | status chip; `tone` prop maps to `ok`/`warn`/`bad`/`info` |
| `Table.tsx` | dense data table with sticky header |
| `Tabs.tsx` | accessible tab list |
| `Dialog.tsx` | modal with focus trap |
| `Input.tsx` | text / number input with label + error |
| `Select.tsx` | native select, styled |
| `States.tsx` | `Loading` / `Empty` / `ErrorState` — the three states every panel needs |
| `Kbd.tsx` | keyboard hint chip |

`States.tsx` is the one that matters most for consistency. Every panel that fetches
renders one of these three instead of inventing its own.

### Feature components

| Component | Responsibility |
|---|---|
| `AppShell.tsx` | sidebar + top bar + main scroll area |
| `WorkspaceContext.tsx` | the Zustand store |
| `ThemeToggle.tsx` | light / dark / system |
| `AlertsPanel.tsx` | alert list + severity tones; exports `_internals = { formatMoney }` for tests |
| `FinancingPanel.tsx` | financing matches + synthetic-data disclaimer |
| `dashboard/*.tsx` | one component per chart (see chapter 12) |

---

## 11.8 Error, loading, and empty states

Three states, one pattern, everywhere:

```typescript
const { data, isLoading, error, isEmpty } = useQuery({ … });

if (isLoading) return <States.Loading />;
if (error)     return <States.Error error={error} />;
if (!data?.items?.length) return <States.Empty action={<Button>…</Button>} />;
return <Panel data={data} />;
```

Concrete examples in the codebase:

- `AlertsPanel.tsx:84-86` — `CheckCircle2` + "No alerts. Cash looks within normal bounds"
- `assistant/page.tsx` — provider `unavailable` chip + empty chat state with suggestions
- `settings/page.tsx` — each card has loading / error / empty branches

### The synthetic-data banner

Every dashboard render includes a banner stating the data is synthetic for demo
businesses (`dashboard/page.tsx:75`). It is not conditional on detecting a demo
workspace. This is deliberate: a real user who imported real data should never be shown
a banner that might be wrong, and a demo user should always be reminded.

---

## 11.9 Print support

Both the dashboard and the decision detail page implement `window.print()` with a
print stylesheet:

```typescript
// dashboard/page.tsx:893
const PRINT_STYLES = `
  @media print {
    button, input, select, textarea { display: none !important; }
    .no-print { display: none !important; }
    body { background: white; color: black; }
  }`;
```

A printed dashboard or decision is a **static document**: no buttons, no inputs, no
interactive chrome. The decision detail page additionally hides its toolbar so a print
is just the verdict, the rule table, and the caveats — the authoritative parts.

---

## 11.10 Extending this

### Adding a page

1. `app/(app)/<name>/page.tsx` — must be a client component if it fetches
2. Add a nav entry to `NAV` in `AppShell.tsx:20`
3. Create the feature components under `components/<name>/`
4. Reuse `States.tsx` for the three fetch states
5. Use only design tokens for colour

### Adding a chart

1. Backend: add a `*_visual()` generator in `app/insights/engine.py`, register it in
   `build_dashboard_insights`
2. Frontend: add a component under `components/dashboard/`
3. Map the new `visual_id` in `dashboard/page.tsx:206-211`
4. Add the matching Zod schema for the evidence payload
5. Make negative/zero states greyscale-safe (shape, not just colour)

### Adding a query

1. Pick the right state owner (server / global / local — §11.2)
2. If server state: `useQuery` with `businessId` in the key
3. Pass the Zod schema to `apiGet`
4. Render the three states
5. Invalidate on the mutation that changes it

---

*Next: [Chapter 12 — Dashboard & decision UX](12-dashboard-and-decisions.md)*