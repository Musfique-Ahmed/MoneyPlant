# Chapter 01 — Design Principles

> *The five rules the codebase actually enforces. Every code-review nitpick you've ever
> seen in this repo comes from one of these.*

If you only read one chapter of this documentation, read this one. The five principles
below are not aspirations — they are constraints enforced by the test suite, the type
checker, and the architecture itself. Most "weird" things in the code exist because at
least one of these principles says it has to.

---

## The five principles

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   1. Money is Decimal. Floats are wrong. If your code computes money,        │
│      it uses decimal.Decimal and quantises to currency precision.           │
│                                                                             │
│   2. Numbers come from the engine. The frontend cannot invent a metric,     │
│      cannot compute a chart, cannot decide a verdict. It renders numbers     │
│      the backend already computed.                                          │
│                                                                             │
│   3. Rules decide, the LLM explains. The verdict is final at the moment      │
│      the eight rules vote; the LLM receives the verdict as part of its      │
│      context and may only describe it.                                      │
│                                                                             │
│   4. Failures degrade, they do not lie. A missing LLM returns a graceful    │
│      "unavailable" — never a fabricated answer. A failed importer returns    │
│      rows_read/rows_added counters and a sanitised error summary, never     │
│      a leaked SQL fragment or credential.                                   │
│                                                                             │
│   5. Boundaries fail loudly. Pydantic on the backend edge, Zod on the        │
│      frontend edge. Drift between them throws at first request, not on     │
│      the third prod incident.                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Principle 1 — Money is Decimal

> *If your code computes money, it uses `decimal.Decimal`, not `float`.*

### What this looks like in code

Every money value passes through `backend/app/services/finance/money.py:43 quantize()`
before crossing a layer. `quantize` knows about seven ISO currencies (`USD`, `EUR`, `GBP`,
`INR`, `CAD`, `AUD` at 2dp; `JPY` at 0dp) and rounds `ROUND_HALF_UP`. The arithmetic
primitives — `add`, `sub`, `mul`, `div` — *all* quantise their results, which is why
`Decimal(1)/Decimal(8)` returns `0.13` for USD but `0.12500…` does not leak into a
display string.

```python
# backend/app/services/finance/money.py:43
def quantize(value: Decimal, currency: str) -> Decimal:
    places = PRECISION[currency]    # e.g. 2 for USD, 0 for JPY
    return value.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
```

### Why

Floating-point arithmetic silently corrupts money. A `float` of `0.1 + 0.2` is
`0.30000000000000004`; a `float` of `19.99 * 100` is not `1999.0`. For a product whose
entire purpose is to be trusted with a business's books, that class of bug is fatal.

### How this shows up in the codebase

- SQL columns are `Numeric(20, 4)` — four more decimals than any currency needs, so no
  rounding happens at the storage layer. (`backend/app/models/business.py:21`,
  `backend/app/models/transaction.py:24`)
- The frontend parser for numeric inputs uses a strict regex: `/^-?\d+(\.\d+)?$/`
  (`apps/web/lib/format.ts:11`). Anything that does not look like a Decimal string is
  rejected before it leaves the client.
- `safe_div_str` (`backend/app/services/finance/money.py:73`) returns `None` on divide-by-zero
  rather than raising. Money ratios in the UI tolerate `NaN`-as-`None` more gracefully
  than they tolerate red error banners.
- Floats still exist in the code, but only at *boundaries* (request decoding into Decimal,
  Pandas internals during ingestion). They never reach the engine functions themselves.

### Reviewer checklist

- ✅ `Decimal` typed parameters at service boundaries
- ✅ `quantize` applied after every arithmetic operation
- ✅ `PRECISION[currency]` used, never a hard-coded `2`
- ❌ `float(value)` in any service function under `app/services/finance/`
- ❌ Money compared with `==` without a scale-normalised wrapper
- ❌ `Decimal(value, float=...)` constructors — coerce via `str(value)` instead

---

## Principle 2 — Numbers come from the engine

> *The frontend cannot invent a metric, cannot compute a chart, cannot decide a verdict.*

### What this looks like in code

Look at any chart. The component receives a shape from the backend and renders it; nothing
is computed on the client:

```
Recharts (UI)                 ← what the user sees
    ▲  "synthetic" series     ← computed server-side, not in the browser
    │                         (insights/engine.py:build_dashboard_insights)
    │  JSON with strings     ← strings, not numbers, by the time it crosses the
    │  (e.g. "12.4%")        boundary
    ▼
compute_metrics() + projection ← pure Decimal functions in services/finance
```

The dashboard page in `apps/web/app/(app)/dashboard/page.tsx` runs six
`useQuery` calls, but every derived value (`fmtPct`, `formatMoney`) is a *formatter*, not
a computation. The math has already happened on the server.

The same pattern holds for financing matches, sensitivity slices, and scenario compare rows.
Every row is a precomputed object with pre-rendered display strings.

### Why

A finance product that lets the client compute is a finance product that will show different
numbers to the same user across browsers, sessions, and devices. Even reproducible
JavaScript subtraction introduces rounding subtleties and floating-point drift. Worse, a
client-computed metric is invisible to the test suite.

### The "no-creative-math" rule

- `format.ts` only formats. It never sums, multiplies, or normalises currency values.
- `api.ts` is the *only* module that talks to the network. Every other module reads from
  TanStack Query.
- The Zod schemas in `apps/web/lib/schemas.ts` mirror the backend Pydantic models field
  for field. Adding a field on one side requires adding it on the other — at runtime.
- The explanatory captions next to every chart (`what_it_shows`, `what_to_notice`,
  `why_it_matters`) are produced server-side at `insights/engine.py:227` and onward —
  they are not UI copy.

### Reviewer checklist

- ✅ Every value rendered in the UI traces back to a backend response field
- ✅ All math under `app/services/finance/`; no business logic in API routes
- ❌ Frontend helper that does anything beyond formatting
- ❌ Local `useState` derived from another piece of state (not local UI state)
- ❌ A metric that is "approximately" what the server returns

---

## Principle 3 — Rules decide, the LLM explains

> *The verdict is final at the moment the rules vote. The LLM cannot change it.*

### What this looks like in code

The decision verdict is computed by `aggregate_status()` in
`backend/app/services/rules/engine.py:438`. The Laya adapter contributes *advisory*
scores (`backend/app/services/laya/adapter.py:98`) that appear in the decision detail
view, but they are a separate field. The LLM is gated by a separate endpoint and a
*separate model* (`/api/decisions/{id}/explain`) that produces a structured
`Explanation`, never a verdict.

```
         ┌────────────────────┐
         │  8 rules vote      │  ← engine.evaluate_rules()
         └──────────┬─────────┘
                    │
                    ▼
         ┌────────────────────┐
         │ aggregate_status() │  ← HARD BREACH wins, then INSUFFICIENT,
         │                    │     then SOFT WARNING, then PASS
         └──────────┬─────────┘
                    │ verdict: PROCEED | PROCEED_WITH_CAUTION | REVISE |
                    │           INSUFFICIENT_DATA | REJECT
                    │
    ┌───────────────┼────────────────────┐
    ▼                                     ▼
Laya (advisory)                      LLM (later, /explain)
3 fixed questions,                    receives frozen
returns scores & label                ExplanationContext,
overrides nothing.                    returns summary &
                                     key_risks, may not
                                     change verdict.
```

The four statuses (`proceed`, `proceed_with_caution`, `revise`, `insufficient_data`,
`reject`) are emitted as a closed enum and rendered in the UI with the rule verdict as
the *primary* signal — the Laya and LLM outputs are secondary.

### Why

LLM judgement in a financial product is an unreviewable risk. By making the LLM a *post-hoc
explainer* of a fixed verdict, we get two things:

1. **Determinism.** A scenario produces the same verdict forever, regardless of provider
   health, prompt drift, model version, or rate-limit state.
2. **Auditability.** A reviewer can read the eight rule evaluations, see exactly which one
   caused the rejection, and verify it. They do not have to wonder whether a temperature
   setting changed the answer.

### How this shows up in the codebase

- The decision evaluator (`app/services/decisions/evaluator.py:89 evaluate()`) is
  *unaware of the LLM*. It returns a verdict and never references an LLM provider.
- The `/api/decisions/{id}/explain` endpoint is a separate route, lazy-on-click in the UI
  (`apps/web/app/(app)/decisions/[id]/page.tsx:67`) and surfaces an explicit disclaimer
  when rendered: *"The LLM can only explain. Rule verdicts and binding constraints above
  are authoritative."*
- The provider health probe (`backend/app/services/llm/factory.py:25 list_providers()`)
  returns `ProviderHealth` with `status ∈ {ok, unavailable, misconfigured}`. There is no
  `pending` or `unknown` status — either the probe succeeded or it didn't, and the UI
  always renders an honest state.
- The `/api/ai/assistant/chat` endpoint sends a `_dashboard_context` payload that contains
  *pre-rendered* summary strings, not raw transactions (`apps/web/components/dashboard/`
  — see the dashboard's `explain` mutation at line 258).

### Reviewer checklist

- ✅ Verdict computed before any LLM call
- ✅ Verdict enum is closed
- ❌ Any code path where an LLM is allowed to change `overall_status`
- ❌ Any code path where the verdict field is optional (it shouldn't be)
- ❌ Verdict computation that depends on a network call

---

## Principle 4 — Failures degrade, they do not lie

> *A missing LLM returns a graceful `unavailable`. A failed importer returns counters
> and a sanitised error. Never raw fragments.*

### What this looks like in code

Three concrete examples:

**LLM provider down.** `OllamaProvider.health_check()` returns
`ProviderHealth(status="unavailable", mode="local", reason="ollama not reachable")`.
The `/api/ai/health` endpoint surfaces this with no 500. The UI Assistant page
(`apps/web/app/(app)/assistant/page.tsx:48`) polls every 60 seconds and renders an
empty state, never a stubbed successful answer.

**Sync error sanitisation.** When a SQL connector throws, the sync service writes
`SyncRun.error_summary = "read_failed:OperationalError"`. The raw exception, the
connection string, and any data fragment are stripped. (`backend/app/services/sync/service.py:181`)

**Laya import failure.** When the optional `laya` package is not installed, the adapter
returns three `LayaAssessment(status="unavailable", question=…, rationale="…unavailable…")`
answers. The decision evaluator happily treats these as advisory scores with explanatory
text. Nothing crashes. (`backend/app/services/laya/adapter.py:109`)

### Why

The reason is not "be polite to the user." The reason is that a finance product which
returns a confident wrong answer is strictly more dangerous than one which returns no
answer. The cost of honesty is small (a degraded UI state). The cost of confabulation
is unbounded (a business makes a real decision on a phantom number).

### How this shows up in the codebase

- `backend/app/services/llm/base.py:35 ProviderHealth` is a discriminated union over
  `status`. `unavailable` and `misconfigured` both carry a `reason` string. There is no
  "we tried and we'll hide the failure" path.
- Logs are scrubbed at format-time when `log_redact_financial = True`
  (`backend/app/core/config.py:88`). The `log` wrapper inspects the record's args and
  replaces anything that parses as Decimal in a money field with `<redacted>`.
- SQL connector allows only `SELECT` statements. Identifiers are whitelisted by regex;
  literals are bound; the LIMIT clause is appended *after* the statement is verified
  `SELECT`-only. (`backend/app/services/sync/sql_connector.py`)
- The dashboard print-friendly view injects CSS that hides every `button`, `input`, and
  `select` element — a print is never a half-functional page
  (`apps/web/app/(app)/dashboard/page.tsx:893`).
- The dashboard page includes a banner stating that **the data is synthetic** for every
  demo business (`apps/web/app/(app)/dashboard/page.tsx:75`). There is no auto-detect of
  "demo" — the banner is there for every workspace, on purpose.

### Reviewer checklist

- ✅ Provider health returns `unavailable` honestly
- ✅ All error messages sanitised
- ✅ Optional integrations degrade when missing
- ❌ Try/except that swallows the error and returns success
- ❌ A 200 response with an `error` field in the body
- ❌ Confidence reducers in a default config (defaults always "worst-case first")

---

## Principle 5 — Boundaries fail loudly

> *Pydantic on the backend edge. Zod on the frontend edge. Drift throws at first request.*

### What this looks like in code

Two layers validate every payload — one each side of the wire. Both schemas define a
closed shape; neither side allows an unknown field to silently propagate.

```
   apps/web/lib/schemas.ts            backend/app/schemas/
   ┌─────────────────────┐            ┌─────────────────────┐
   │  Zod parser         │            │  Pydantic v2 parser  │
   │  (mirrors Pydantic) │            │  (single source of   │
   │                     │  ─────────► │   truth)             │
   │                     │  HTTP/JSON  │                     │
   │                     │  ◄───────── │                     │
   └─────────────────────┘            └─────────────────────┘
                │                                │
                ▼                                ▼
        drift = loud error             drift = loud error
        at first request               at first request
```

`lib/api.ts:24 apiGet()` parses the response through a Zod schema before resolving. If the
backend renames a field, every call to `apiGet(..., SomeSchema)` fails immediately in the
browser console with a precise validation error, not at the chart.

The forward path (`apiPost / apiPatch`) is similarly guarded by Pydantic on the receiving
end — but the *real* defence is the test suite, which exercises both directions.

### Why

The Zod/Pydantic mirror is the single most expensive piece of duplication in the codebase
and the single best defence against silent regressions. When a field changes shape, every
caller of that response fails fast — both in dev and (because we hit the API on every page
load) in the first prod session after deploy.

### How this shows up in the codebase

- `apps/web/lib/schemas.test.ts:1` is a small but real test file asserting that the
  schemas parse/reject representative shapes. This is *the* safety net for the mirror.
- `apps/web/components/dashboard/AlertConfig` and the engine's `AlertConfig`
  dataclass (`backend/app/engine/alerts.py:60`) are mirrored but with different intents —
  the engine dataclass is the source of truth.
- `DecisionReport.overall_status` is a closed enum on the backend
  (`backend/app/schemas/decision.py:201`). The Zod mirror reproduces it as a literal union
  with the same five statuses. The decisions page maps statuses to UI tones through a
  single `STATUS_LABELS` table (`apps/web/app/(app)/decisions/page.tsx:22`).
- `DataSource.secret_ref` exists on the ORM model and is referenced server-side, but the
  Zod schema for `DataSourceRead` *deliberately omits the field*
  (`apps/web/lib/schemas.ts:396`). The boundary contract is "the credential cannot be
  observed from the wire response" — implemented by leaving the field out of the schema.

### Reviewer checklist

- ✅ Pydantic model + Zod mirror updated in the same PR
- ✅ Zod test added for any shape change
- ✅ Any new boundary emits a closed enum, not `str`
- ❌ A `dict` JSON shape passed unvalidated between client and server
- ❌ A field name with backend/frontend drift caught only at runtime by a customer

---

## How these principles interact

The five principles are not independent. A natural way to read them is:

| Principle | What it constrains | Where it lives in the code |
|---|---|---|
| Decimal | The *type* of money values | `services/finance/money.py` |
| Engine owns | The *location* of computation | `services/finance/*`, `engine/*`, `insights/engine.py` |
| Rules decide | The *authority* of verdicts | `services/rules/engine.py`, `services/decisions/evaluator.py` |
| Failures degrade | The *honesty* of failures | `services/llm/base.py`, `services/laya/adapter.py`, `sync/service.py` |
| Boundaries fail loudly | The *contract* of the wire | `schemas/*` + `apps/web/lib/schemas.ts` |

If you ever find yourself needing to relax one of these, stop and look at the others first.
They are calibrated against each other.

---

*Next: [Chapter 02 — System architecture](02-system-architecture.md)*