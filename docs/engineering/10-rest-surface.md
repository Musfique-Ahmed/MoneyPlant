# Chapter 10 — REST Surface

> *Every endpoint the backend exposes, what it returns, and how the frontend's Zod mirror
> keeps the two sides honest.*

All routes are mounted under `/api` (`backend/app/main.py:103-113`). Eleven routers:

```python
app.include_router(businesses_router,        prefix="/api")
app.include_router(imports_router,          prefix="/api")
app.include_router(transactions_router,     prefix="/api")
app.include_router(scenarios_router,        prefix="/api")
app.include_router(decisions_router,        prefix="/api")
app.include_router(ai_router,               prefix="/api")
app.include_router(alerts_router,           prefix="/api")
app.include_router(financing_router,        prefix="/api")
app.include_router(insights_router,         prefix="/api")
app.include_router(data_sources_router,     prefix="/api")
app.include_router(data_sources_business_router, prefix="/api")
```

Two non-router routes on the app itself:

| Route | Purpose |
|---|---|
| `GET /api/health` | Liveness probe (`main.py:68`) |
| `GET /api/config/public` | Safe boolean flags only — provider reachability, no secrets (`main.py:72`) |

Plus FastAPI's built-in `/docs` (Swagger) and `/redoc`, enabled in development.

---

## 10.1 Complete endpoint table

### Businesses — `api/businesses.py`, prefix `/api/businesses`

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `GET` | `/businesses` | — | `BusinessRead[]` |
| `POST` | `/businesses` | `{name, industry, currency, fiscal_year_start_month, min_cash_reserve, target_operating_margin, max_unsold_inventory_exposure_pct, locale?}` | `201 BusinessRead` |
| `GET` | `/businesses/{business_id}` | — | `BusinessRead` |
| `PATCH` | `/businesses/{business_id}` | partial `BusinessUpdate` | `BusinessRead` |
| `DELETE` | `/businesses/{business_id}` | — | `204` |

`DELETE` cascades: `transactions`, `scenarios`, `import_jobs`, `decisions` all
`delete-orphan` relationships. It is a hard delete, not a soft delete.

### Transactions & financial summary — `api/transactions.py`

| Method | Path | Query | Returns |
|---|---|---|---|
| `GET` | `/transactions` | `business_id`, `start?`, `end?`, `category?` | `TransactionRead[]` |
| `GET` | `/transactions/categories` | `business_id` | `string[]` (distinct categories in use) |
| `GET` | `/financial-summary` | `business_id`, `start`, `end`, `opening_cash?` | `FinancialSummary` |

`FinancialSummary` carries `data_coverage`, `warnings`, and `is_empty` alongside the
computed metrics — so the UI can distinguish "no revenue" from "we don't have enough
data to say".

### Scenarios — `api/scenarios.py`

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/scenarios/simulate` | `ScenarioInputs` (industry-specific) | `ScenarioResult` (not persisted) |
| `POST` | `/scenarios/simulate/sensitivity` | `{inputs, currency, axes?, multipliers?}` | `SensitivitySlice[]` |
| `POST` | `/scenarios` | `{business_id, name, industry, description?, inputs}` | `201 ScenarioRead` (creates v1) |
| `GET` | `/scenarios` | `business_id` | `ScenarioRead[]` |
| `GET` | `/scenarios/{scenario_id}` | — | `ScenarioRead` |
| `GET` | `/scenarios/{scenario_id}/versions` | — | `ScenarioVersionRead[]` |
| `POST` | `/scenarios/{scenario_id}/rerun` | optional `inputs` override | `ScenarioVersionRead` (new version) |
| `POST` | `/scenarios/compare` | `{scenario_ids: [1..5], business_id}` | `CompareResponse` |

Scenarios are **append-only versions**. Re-running a scenario creates
`ScenarioVersion(version_number=N+1)`; it never mutates `ScenarioVersion(N)`. The
`uq_scenario_version` unique constraint on `(scenario_id, version_number)` enforces
this at the DB level.

### Decisions — `api/decisions.py`

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/decisions/evaluate` | `{scenario_version_id}` | `201 DecisionReportRead` |
| `GET` | `/decisions` | `business_id` | `DecisionReportRead[]` |
| `GET` | `/decisions/{report_id}` | — | `DecisionReportRead` |
| `POST` | `/decisions/{report_id}/explain` | `{provider_mode?}` | `Explanation` |

> **Schema-drift watch.** `ScenarioRead` exposes `latest_version_id`; the evaluate
> endpoint wants `scenario_version_id`. The frontend resolves the first into the second
> (`decisions/page.tsx:73`). This is a known asymmetry between two related nouns. If you
> rename either, update both sides in the same PR.

### Imports — `api/imports.py`

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/imports/preview` | multipart file | `ImportPreview` |
| `POST` | `/imports/validate` | multipart file + `mapping` | `{valid_rows, issues}` |
| `POST` | `/imports/commit` | multipart file + `mapping` | `201 ImportJobRead` |
| `GET` | `/imports` | `business_id` | `ImportJobRead[]` |
| `GET` | `/imports/{job_id}` | — | `ImportJobRead` |
| `GET` | `/imports/fields/canonical` | — | `string[]` (`CANONICAL_FIELDS`) |

### AI — `api/ai.py`

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/ai/providers` | — | `[{mode, model, available}]` |
| `GET` | `/ai/health` | — | `ProviderHealth[]` (probe all three) |
| `POST` | `/ai/assistant/chat` | `{message, business_id?, _dashboard_context?}` | `{reply, provider, model, mode, unavailable?}` |

`/ai/health` is polled by the Assistant page every 60s and by the Settings page's
`ProvidersList`. It is the single source of truth for the provider chip.

### Alerts — `api/alerts.py`

| Method | Path | Query | Returns |
|---|---|---|---|
| `GET` | `/businesses/{business_id}/alerts` | `horizon_months?` | `AlertsResponse` |

### Financing — `api/financing.py`

| Method | Path | Query | Returns |
|---|---|---|---|
| `GET` | `/businesses/{business_id}/financing-options` | — | `FinancingOptionsResponse` |

Always labelled SYNTHETIC in the UI. See chapter 05 §5.9.

### Insights — `api/insights.py`

| Method | Path | Query | Returns |
|---|---|---|---|
| `GET` | `/businesses/{business_id}/dashboard-insights` | — | `DashboardInsightsResponse` (the `Visual[]` array) |

This is the densest response in the API. One call fills six charts, the KPI strip, and
the alert summary. The work happens in `insights/engine.py:899`.

### Data sources — `api/data_sources.py` (two routers)

Router 1, prefix `/api/sources`:

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/sources` | `business_id` | `DataSourceRead[]` |
| `POST` | `/sources` | `{business_id, name, type, config, column_mapping, schedule?, secret_ref?}` | `201 DataSourceRead` |
| `GET` | `/sources/{source_id}` | — | `DataSourceRead` |
| `PATCH` | `/sources/{source_id}` | partial | `DataSourceRead` |
| `DELETE` | `/sources/{source_id}` | — | `204` |
| `POST` | `/sources/{source_id}/test` | — | `SyncRunRead` (counters, no watermark update) |
| `POST` | `/sources/{source_id}/sync` | — | `SyncRunRead` |
| `GET` | `/sources/{source_id}/runs` | — | `SyncRunRead[]` |

Router 2, prefix `/api/businesses`:

| Method | Path | Returns |
|---|---|---|
| `GET` | `/businesses/{business_id}/freshness` | `Freshness` (per-source + headline) |

> `DataSourceRead` deliberately omits `secret_ref`. The credential is accepted on create
> and never returned. See chapter 04 §4.8.

---

## 10.2 Endpoint count by feature

```
   Businesses         5
   Transactions       3
   Scenarios          8
   Decisions          4
   Imports            6
   AI                 3
   Alerts             1
   Financing          1
   Insights           1
   Data sources       9
   ─────────────────────────
   Total             41  (+ 2 app-level: /health, /config/public)
```

---

## 10.3 Error contract

Every non-2xx response is FastAPI's `{"detail": ...}` shape, except the catch-all:

```python
# main.py:115 — generic exception handler
@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": "internal_error"})
```

| Status | When | Body |
|---|---|---|
| `400` | Validation failed (Pydantic) | `{"detail": [{loc, msg, type}, …]}` |
| `404` | Unknown id | `{"detail": "Not Found"}` |
| `409` | Duplicate scenario name, or unique-constraint collision | `{"detail": "..."}` |
| `422` | Request shape wrong (FastAPI validation) | `{"detail": [{loc, msg, type}, …]}` |
| `500` | Anything unhandled | `{"detail": "internal_error"}` — never a stack trace |

The frontend's `apiSend` (`lib/api.ts`) throws `ApiError(status, detail)` on any
non-2xx. Components catch it and render the `detail` string. An unrecognised status
becomes a generic "Something went wrong" in the UI.

---

## 10.4 The Zod mirror — how drift is caught

`apps/web/lib/schemas.ts` reproduces every response schema. `lib/api.ts` parses each
response through the matching Zod schema before returning:

```typescript
// lib/api.ts:24
export async function apiGet<T>(
  path: string,
  schema: ZodSchema<T>,
  init?: RequestInit,
): Promise<T> {
  const res = await apiSend(path, { method: "GET", ...init });
  return schema.parse(res);          // ← throws on drift
}
```

The parse happens on **every** response. A renamed field fails on the first request
that touches it, in the browser console, with a precise Zod path:

```
   ZodError: [
     { path: ["scenarios", 0, "latest_version_id"], expected: string, received: undefined }
   ]
```

`lib/schemas.test.ts` is the regression net: it asserts representative payloads parse,
and asserts that malformed payloads fail.

### The mirror discipline

| Backend type | Zod mirror | Notes |
|---|---|---|
| `BusinessRead` | `Business` | `min_cash_reserve` etc. are **strings** in the schema, matching Pydantic's Decimal → str serialisation |
| `Currency` | `Currency` | 7 ISO codes |
| `Industry` | `Industry` | literal union |
| `FinancialSummary` | `FinancialSummary` | includes `data_coverage`, `warnings`, `is_empty` |
| `ScenarioResult` | `ScenarioResult` | includes `invariants_ok`, `invariants_failures` |
| `DecisionReport` | `DecisionReport` | `overall_status` is the 5-value literal union |
| `DataSourceRead` | `DataSource` | **omits `secret_ref`** by design |
| `Freshness` | `Freshness` | includes backend-generated `headline` |
| `Explanation` | `Explanation` | `status`, `summary`, `key_risks`, … |
| `ProviderHealth` | `ProviderHealth` | `status: "ok" \| "unavailable" \| "misconfigured"` |

Decimal fields cross the wire as **strings**, not numbers. `format.ts:11` re-exports
`DecimalString = z.string().regex(/^-?\d+(\.\d+)?$/)` and every money field in the
Zod schemas uses it. This is deliberate: a JSON number would already have lost precision
before Zod could reject it.

---

## 10.5 Query-key naming convention

TanStack Query keys are computed per business so a workspace switch invalidates
everything:

```typescript
// apps/web/app/(app)/dashboard/page.tsx:127-190
useQuery({
  queryKey: ["dashboard-insights", businessId],
  queryFn:  () => apiGet(`/businesses/${businessId}/dashboard-insights`, DashboardInsightsSchema),
  enabled:  Boolean(businessId),
  staleTime: 30_000,
})
```

| Page | Query keys |
|---|---|
| dashboard | `["dashboard-insights", id]`, `["financial-summary", id, …]`, `["alerts", id]`, `["financing-options", id]`, `["scenarios", id]`, `["ai-health"]` |
| data | `["sources", id]`, `["source-runs", sourceId]`, `["freshness", id]` (polls 5s) |
| simulator | `["industry-fields", industry]` |
| decisions | `["decisions", id]`, `["scenarios", id]`, `["explain", reportId]` |
| decisions/[id] | `["decision", reportId]`, `["explain", reportId]` |
| compare | `["scenarios", id]` (for the picker) |
| assistant | `["ai-health"]` (polls 60s) |
| settings | `["businesses"]`, `["ai-health"]` |

`["ai-health"]` has no business id — provider health is environment-wide, not per
workspace. Polling cadence varies by page and is documented in chapter 11.

---

## 10.6 Adding an endpoint — the checklist

1. **Pydantic request/response** in `app/schemas/<feature>.py`. Use closed enums for
   any field with a fixed set.
2. **Router handler** in `app/api/<feature>.py`. Take `db: Session = Depends(get_db)`.
   No business logic beyond orchestration — push it into `app/services/`.
3. **Register** the router in `app/main.py` if it is a new feature module.
4. **Zod mirror** in `apps/web/lib/schemas.ts`. Field-for-field with the response model.
5. **Zod test** in `apps/web/lib/schemas.test.ts` for the new shape.
6. **`apiGet`/`apiPost` wrapper usage** in the consuming page, with the schema passed in.
7. **Query key** including `businessId`.
8. **Backend test** in `backend/tests/test_api.py` or a feature-specific file.
9. **E2E spec** in `apps/web/e2e/` if it is a user-visible flow.

---

## 10.7 Removing or renaming an endpoint

```
   1. Update backend route + Pydantic models
   2. Update Zod mirror (schemas.ts)
   3. Update every apiGet/apiPost call site
   4. Update e2e specs that hit the endpoint directly
   5. Update the Zod test fixtures
   6. Update any backend tests that assert on the response shape
   7. Verify `npm run typecheck` passes (TS types are derived from the Zod schemas,
      so a stale mirror shows up as a type error)
   8. Verify `npm run test` passes (the schemas test will catch runtime-only drift)
```

The order matters: the Zod mirror first would break the build loudly; the backend first
would break the frontend at runtime. Doing Zod first turns a silent runtime failure into
a loud type error.

---

## 10.8 Full surface, one page

```
   GET    /api/health
   GET    /api/config/public

   GET    /api/businesses
   POST   /api/businesses
   GET    /api/businesses/{business_id}
   PATCH  /api/businesses/{business_id}
   DELETE /api/businesses/{business_id}
   GET    /api/businesses/{business_id}/alerts
   GET    /api/businesses/{business_id}/financing-options
   GET    /api/businesses/{business_id}/dashboard-insights
   GET    /api/businesses/{business_id}/freshness

   GET    /api/transactions
   GET    /api/transactions/categories
   GET    /api/financial-summary

   POST   /api/scenarios/simulate
   POST   /api/scenarios/simulate/sensitivity
   POST   /api/scenarios
   GET    /api/scenarios
   GET    /api/scenarios/{scenario_id}
   GET    /api/scenarios/{scenario_id}/versions
   POST   /api/scenarios/{scenario_id}/rerun
   POST   /api/scenarios/compare

   POST   /api/decisions/evaluate
   GET    /api/decisions
   GET    /api/decisions/{report_id}
   POST   /api/decisions/{report_id}/explain

   POST   /api/imports/preview
   POST   /api/imports/validate
   POST   /api/imports/commit
   GET    /api/imports
   GET    /api/imports/{job_id}
   GET    /api/imports/fields/canonical

   GET    /api/ai/providers
   GET    /api/ai/health
   POST   /api/ai/assistant/chat

   GET    /api/sources
   POST   /api/sources
   GET    /api/sources/{source_id}
   PATCH  /api/sources/{source_id}
   DELETE /api/sources/{source_id}
   POST   /api/sources/{source_id}/test
   POST   /api/sources/{source_id}/sync
   GET    /api/sources/{source_id}/runs
```

---

*Next: [Chapter 11 — Web architecture](11-web-architecture.md)*