# Chapter 04 — Data Layer & Migrations

> *SQLAlchemy 2 models, Alembic migrations, dedup, versioning, and what is intentionally
> not modeled.*

---

## 4.1 What lives where

```
   ┌────────────────────────────────────────────┐
   │  SQLAlchemy 2 models  (app/models/*)       │
   │  ─ Business                                │
   │  ─ Transaction                             │
   │  ─ Scenario + ScenarioVersion              │
   │  ─ DecisionReport + LlmExplanation         │
   │  ─ ImportJob                               │
   │  ─ DataSource + SyncRun                    │
   └─────────────────────┬──────────────────────┘
                         │  one Engine, one SessionLocal
                         ▼
   ┌────────────────────────────────────────────┐
   │  app/db/session.py                         │
   │  SessionLocal → get_db dependency          │
   └─────────────────────┬──────────────────────┘
                         ▼
   ┌────────────────────────────────────────────┐
   │  Alembic  (alembic/versions/)              │
   │  ─ 0001_initial                            │
   │  ─ 0002_data_sources                       │
   │  ─ 0003_sync_dedup_columns                 │
   └────────────────────────────────────────────┘
```

No enum tables, no view layer, no materialized views. Everything you need to reconstruct
the schema lives in `app/models/*.py`.

---

## 4.2 Conventions every model follows

```python
# every model inherits both mixins
class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"
    # columns using Numeric(20, 4) — see Principle 1
    min_cash_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0"))
    # relationships with cascade
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
```

| Convention | Where |
|---|---|
| **UUID primary key** (string UUID, not int) | `app/db/base.py` — `UUIDPrimaryKeyMixin` |
| **`created_at` and `updated_at`** server-default `func.now()` | `app/db/base.py` — `TimestampMixin` |
| **Money as `Numeric(20, 4)`** (4 dp beyond any currency needs) | every money column |
| **`back_populates` on both sides** of a relationship | `app/models/business.py` + child |
| **`cascade="all, delete-orphan"`** on parent→child, never on child→parent | every parent |
| **Indexes** on `business_id` and any column used by sync where-clauses | `Transaction.source_row_hash`, `tx_date`, `cash_flow_date` |

The numeric precision choice is deliberate. `Numeric(20, 4)` stores 16 digits of
significant value plus 4 fractional digits. The engine quantises to currency precision
(JPY 0dp, others 2dp) before persisting, so the four extra decimals absorb any rounding
intermediate without losing a single digit. If you reach for `Float` here, stop —
Principle 1.

---

## 4.3 ERD, current state

```mermaid
erDiagram
    BUSINESS ||--o{ TRANSACTION : has
    BUSINESS ||--o{ SCENARIO : has
    BUSINESS ||--o{ DECISION_REPORT : has
    BUSINESS ||--o{ IMPORT_JOB : has
    BUSINESS ||--o{ DATA_SOURCE : owns

    SCENARIO ||--o{ SCENARIO_VERSION : versions
    DECISION_REPORT ||--o| LLM_EXPLANATION : has
    DATA_SOURCE ||--o{ SYNC_RUN : runs
    IMPORT_JOB ||--o{ TRANSACTION : "produces (via source_row_hash)"
    DATA_SOURCE ||--o{ TRANSACTION : "produces (via source_row_hash)"

    BUSINESS {
        string id PK
        string name
        string industry
        string currency "default USD"
        int    fiscal_year_start_month "default 1"
        string locale "default en-US"
        numeric(20,4) min_cash_reserve "default 0"
        numeric(6,4) target_operating_margin "default 0.10"
        numeric(6,4) max_unsold_inventory_exposure_pct "default 0.20"
        timestamp created_at
        timestamp updated_at
    }

    TRANSACTION {
        string id PK
        string business_id FK
        date   tx_date
        date   cash_flow_date "nullable"
        string description "default ''"
        numeric(20,4) amount "abs"
        string currency "default USD"
        string direction "inflow|outflow"
        string category
        string payment_status "nullable"
        string customer_or_supplier "nullable"
        string source_file "nullable"
        string source_sheet "nullable"
        string source_row "nullable"
        string import_job_id "nullable"
        string source_row_hash "nullable"
        string data_source_id "nullable (NULL for manual)"
        timestamp created_at
    }

    SCENARIO {
        string id PK
        string business_id FK
        string name
        string industry
        text   description "default ''"
        string status "default 'draft'"
        timestamp created_at
        timestamp updated_at
    }

    SCENARIO_VERSION {
        string id PK
        string scenario_id FK
        int    version_number
        text   inputs_json
        string engine_version "default '0.1.0'"
        text   result_json "nullable"
        timestamp calculation_timestamp "nullable"
        timestamp created_at
    }

    DECISION_REPORT {
        string id PK
        string business_id FK
        string scenario_version_id FK
        string overall_status "PROCEED|PROCEED_WITH_CAUTION|REVISE|INSUFFICIENT_DATA|REJECT"
        json   rule_evaluations
        json   laya_assessments "nullable"
        text   binding_constraints
        text   key_risks
        text   recommendation
        text   caveats "nullable"
        timestamp created_at
    }

    LLM_EXPLANATION {
        string id PK
        string decision_report_id FK "unique 1:1"
        string provider
        string model
        string mode "local|openai|anthropic"
        text   summary
        json   supporting_evidence
        text   key_risks
        text   assumptions
        text   missing_information
        text   alternatives "nullable"
        text   next_actions "nullable"
        text   limitations
        text   raw_response "nullable"
        timestamp created_at
    }

    IMPORT_JOB {
        string id PK
        string business_id FK
        string filename
        string sheet_name "nullable"
        json   mapping
        string status "preview|validating|committed|rejected"
        int    rows_added
        int    rows_skipped_duplicate
        int    rows_rejected
        text   error_summary "nullable"
        timestamp created_at
    }

    DATA_SOURCE {
        string id PK
        string business_id FK
        string name
        string type "file|sql"
        json   config
        json   column_mapping
        bool   enabled "default true"
        string schedule "manual|hourly|daily"
        string secret_ref "nullable, server-only"
        timestamp last_sync_at "nullable"
        string  last_incremental_value "nullable"
        string  file_content_sha256 "nullable"
        text    last_error_summary "nullable"
        timestamp created_at
    }

    SYNC_RUN {
        string id PK
        string data_source_id FK
        string trigger "manual|scheduled|test"
        int    rows_read
        int    rows_added
        int    rows_skipped_duplicate
        int    rows_rejected
        text   error_summary "nullable"
        timestamp started_at
        timestamp finished_at
    }
```

> **Note on `Transaction.import_job_id` and `data_source_id`** — these are nullable
> strings (not foreign keys) because one transaction may be produced by *either* a
> manual CSV import *or* a sync run, and the historical record needs to survive even
> if the producing job is deleted. The unique constraint is on
> `(business_id, source_row_hash)` instead — see §4.5.

---

## 4.4 Numeric columns: the precision guarantee

Why `Numeric(20, 4)` and not `Numeric(20, 2)` or `Float`?

```
  USD at 2dp: max ~ $1 trillion ($10^12), 12 + 2 = 14 digits
  EUR / GBP / INR / CAD / AUD at 2dp: same
  JPY at 0dp: max ¥10 trillion, 13 + 0 = 13 digits

  So 20 digits of integer-space is comfortably 7 digits beyond the largest plausible value.
  The 4 fractional digits are *intermediate precision*:
  we quantise to 2dp (or 0dp) before INSERT but the schema is honest about
  "this column can hold unrounded operations if you want to skip a quantize call".

  Float would be wrong because (a) 0.1 is not representable, (b) comparsion is brittle,
  (c) sums of 1e6 rows drift. See Principle 1.
```

---

## 4.5 The idempotency contract

Manual uploads and scheduled syncs are both expected to be **safely re-runnable**.

```
         ┌───────────────┐
         │  raw row      │
         │  (CSV / XLSX  │
         │   / SQL row)  │
         └──────┬────────┘
                │  map to canonical tuple
                ▼
         ┌────────────────────────────────────────────────┐
         │  serialize: business_id + canonical-fields     │
         │  hash: SHA-256 hex                             │
         └────────────────────┬───────────────────────────┘
                              │
                              ▼
         ┌────────────────────────────────────────────────┐
         │  uniqueness check (inside transaction)         │
         │  ─ in-memory set of known hashes               │
         │  ─ DB unique index:                             │
         │    uq_transactions_business_source_row_hash     │
         └────────────────────┬───────────────────────────┘
                ┌─────────────┴─────────────┐
                ▼                            ▼
         duplicate → count              new → INSERT
         rows_skipped_duplicate         rows_added
                │                            │
                └─────────────┬──────────────┘
                              ▼
                    COMMIT (with SAVEPOINT
                     per insert so a unique-constraint
                     race rolls back only the offending row)
```

The exact watermark policy per connector:

| Connector | Watermark | Recompute rule |
|---|---|---|
| File (csv/xlsx) | `DataSource.file_content_sha256` | Recomputed on every run; if unchanged, no new inserts beyond the dedup index |
| SQL (incremental) | `DataSource.incremental_value` | Set from `rows[-1]` after a successful insert; never *decreases* — the service.py:213 guard rejects a watermark regress |

The **SAVEPOINT pattern** in `service.py:289` is worth understanding in detail:

```python
# service.py — pseudocode sketch
def run_sync(db, source_id, trigger):
    source = ...
    raw = connector.read_rows()
    try:
        for raw_row in raw:
            canonical = map_row(raw_row, source.column_mapping)
            row_hash = sha256(canonical_tuple)
            if row_hash in seen_hashes:
                counters.duplicate += 1; continue
            try:
                with db.begin_nested():       # SAVEPOINT
                    db.add(Transaction(... row_hash=row_hash))
                    counters.added += 1
                    seen_hashes.add(row_hash)
            except IntegrityError:            # race with parallel sync
                counters.duplicate += 1        # the other inserter won
    finally:
        SyncRun(status=ok_or_partial, counters=...).save()
```

This means a *concurrent* sync run will roll back only the row(s) it lost the race on. The
overall counters (`rows_read`, `rows_added`, `rows_skipped_duplicate`, `rows_rejected`)
are the durable truth, not "did the whole batch succeed".

---

## 4.6 Migrations

Three migrations exist. Each one is **forward-only with a downgrade** as a safety net.

| File | Adds |
|---|---|
| `alembic/versions/0001_initial.py` | `businesses`, `transactions`, `scenarios`, `scenario_versions`, `decision_reports`, `llm_explanations`, `import_jobs` |
| `alembic/versions/0002_data_sources.py` | `data_sources`, `sync_runs`, plus `data_source_id` and `secret_ref` on `data_sources` |
| `alembic/versions/0003_sync_dedup_columns.py` | `uq_transactions_business_source_row_hash` unique index, `transaction.source_row_hash` column, `data_source.file_content_sha256`, `data_source.incremental_value` |

### How to add a migration

```bash
# create a revision (in your activated backend venv)
cd backend
alembic revision -m "add_landing_signal_to_business"

# edit the file Alembic produced under alembic/versions/
# implement upgrade() AND downgrade()
# test both:
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

### What to put in a migration

| Do | Don't |
|---|---|
| Add nullable columns with sane defaults | Add `NOT NULL` columns without backfill |
| Backfill in a separate migration if data transformation is required | Materialise data mid-migration on a production table |
| Match `Numeric(20, 4)` for any new money column | Reach for `Float` "just for this one" |
| Add unique constraints only after the underlying column is populated | Add `UNIQUE` on a column with nulls that you mean to be unique |
| Provide an explicit downgrade | Leave downgrade as `pass` (downgrades are how you debug a bad deploy) |

---

## 4.7 What is intentionally not modeled

| Concern | Why absent | Workaround |
|---|---|---|
| **Users** | Pilot product. Single tenant. | The "active business" is held in `WorkspaceContext`. |
| **Permissions / roles** | Single user. | The destructive paths (delete business, delete data source) guard at the route layer with a confirmation, not auth. |
| **Tags / categories** | Categories are free-text `String(64)` denormalised onto `Transaction.category`. | Want better search? Add it in a service-layer index, not a new table. |
| **Audit log** | Not a regulated product; rule evaluations and decision results are already immutable versions. | If added, it should be a single append-only `audit_event` table with a `(actor_id, ts, kind, payload)` shape. |
| **Currency conversion** | Each business picks one currency at creation (`business.currency`). | Mixed-currency analysis would require either multi-currency transaction storage or a `transactions.currency` value that the metrics layer normalises — neither is built. The current UI compares in USD only on the `Compare` page; `compare/page.tsx` lines 146, 152 hard-code `"USD"` deliberately. |
| **Soft delete on transactions** | Combined with idempotent-import dedup, a typo is effectively permanent. | The product team is aware; documented as a known gap. |

---

## 4.8 Pydantic mirrors — the contract

For every ORM model that crosses the wire, a matching Pydantic schema is the *primary
contract*. The ORM model is internal; the schema is the boundary.

```python
# app/schemas/business.py — illustrative shape
class BusinessRead(BaseModel):
    id: str
    name: str
    industry: str       # closed enum on the field — not free text
    currency: str       # 7 codes, validated
    min_cash_reserve: Decimal
    target_operating_margin: Decimal
    max_unsold_inventory_exposure_pct: Decimal
    # … no created_at in the public read; no internal watermarks
```

The mirror that matters: `apps/web/lib/schemas.ts:18 Business` reproduces this shape
field-for-field. Drift throws at first request, not later.

The exceptions (intentional gaps in the schema):

- `BusinessRead` does **not** expose `created_at` / `updated_at` — internal timestamps
  shouldn't drive UI logic.
- `DataSourceRead` does **not** expose `secret_ref` — the credential is server-side.
  (`lib/schemas.ts:396`)
- `Transaction` does **not** expose `source_row_hash` — it's an internal idempotency key,
  not a UI element.

---

## 4.9 Extending this

A checklist for the common additions.

**Adding a new money column to `Business`:**

1. `app/models/business.py` — `Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0"))`
2. New Alembic migration under `alembic/versions/`, with both directions.
3. `app/schemas/business.py` — add the field to `BusinessRead` and `BusinessUpdate`.
4. `apps/web/lib/schemas.ts` — add the matching field to `Business` (test `schemas.test.ts`).
5. If it affects engine thresholds (e.g. a new reserve rule): update
   `app/services/rules/engine.py` rule + add to the `RULES` list in display order.

**Adding a new transaction field that gates ingest:**

1. `Transaction` model + migration
2. `app/services/ingestion/csv.py` `canonical_fields()` — add to canonical map
3. `app/services/ingestion/csv.py` + `xlsx.py` — handle the new column
4. `app/schemas/transaction.py` + Zod mirror in `apps/web/lib/schemas.ts`

**What this should never become:** ORM models that bypass `engine/` and reach into
SQLAlchemy directly from a router. The function-call discipline here is what makes the
engine pure.

---

*Next: [Chapter 05 — Financial engine](05-financial-engine.md)*