# MoneyPlant — Engineering Documentation

> **Status:** Living document · maintained alongside the code
> **Scope:** `backend/` (FastAPI) + `apps/web/` (Next.js) + `sample_data/` + supporting scripts
> **Audience:** Engineers joining the project, and reviewers evaluating a change.

---

## What this is

MoneyPlant is a **finance copilot for small and mid-sized businesses**. It ingests a
business's own financial records, runs deterministic projections over "what if" scenarios,
applies a rule-first decision engine to each scenario, and renders the result as dashboards,
comparisons, and — only where it earns its place — a natural-language explanation.

This documentation explains **how the system is built and why it is built that way**. It is
written for two overlapping audiences at once:

- **Engineers** who need to navigate the codebase, understand invariants, and extend it safely.
- **Reviewers** who need to evaluate whether a design choice is sound without reading every file.

To serve both, each chapter leads with *what the system does and why*, then drills into
*how it does it*, with `file:line` evidence throughout. If you are here to make a change, jump
to the relevant chapter and read the "Extending this" note at the end.

---

## The one-paragraph version

A two-process monorepo. A **FastAPI** backend owns all persistence and all financial math; a
**Next.js 14** frontend talks to it only over JSON. The defining constraint is that **every
number the user sees is computed in exact decimal arithmetic by deterministic code**. The LLM
is a *presenter*, never a *calculator* and never a *judge* — it explains a verdict that already
exists, and is structurally prevented from changing it.

---

## Table of contents

### Foundations

| # | Chapter | What it covers |
|---|---------|----------------|
| 00 | [Orientation & how to read the code](00-orientation.md) | Where things live, the mental model, first-day workflow |
| 01 | [Design principles](01-design-principles.md) | The five rules the codebase actually enforces, and why |
| 02 | [System architecture](02-system-architecture.md) | Process model, data flow, request lifecycle, diagrams |
| 03 | [Technology stack & repository layout](03-stack-and-layout.md) | Every dependency with evidence, plus the directory map |

### Backend

| # | Chapter | What it covers |
|---|---------|----------------|
| 04 | [Data layer & migrations](04-data-layer.md) | SQLAlchemy 2 models, Alembic, dedup, versioning |
| 05 | [Financial engine](05-financial-engine.md) | `Decimal` primitives, periods, metrics, inventory, invariants |
| 06 | [Rule engine & decision aggregation](06-rules-and-decisions.md) | The 8 rules, hard/soft precedence, the Laya boundary |
| 07 | [LLM providers & Laya adapter](07-llm-and-laya.md) | Provider abstraction, health probing, the "explain only" contract |

### Data in

| # | Chapter | What it covers |
|---|---------|----------------|
| 08 | [Ingestion pipeline](08-ingestion.md) | CSV/XLSX parsing, mapping, validation, idempotent commit |
| 09 | [Connected data sources & sync](09-sync.md) | Connectors, dedup, scheduler, SQL safety |
| 10 | [REST surface](10-rest-surface.md) | Every endpoint, the frontend's Zod mirror |

### Frontend

| # | Chapter | What it covers |
|---|---------|----------------|
| 11 | [Web architecture](11-web-architecture.md) | App Router, TanStack Query, workspace state, validation |
| 12 | [Dashboard & decision UX](12-dashboard-and-decisions.md) | Component-by-component, the "explanation sits next to the figure" pattern |

### Operations

| # | Chapter | What it covers |
|---|---------|----------------|
| 13 | [Local development runbook](13-local-runbook.md) | Getting both processes running, seeding, common failures |
| 14 | [Testing, deployment & known gaps](14-testing-and-ops.md) | Test layers, env vars, deployment posture, limitations |

---

## Conventions used in this documentation

- **`file:line`** citations — e.g. `backend/app/services/rules/engine.py:438` — point at the
  exact source. Line numbers reflect commit `f01314a` on `main`; they will drift, so treat
  them as a starting point and search by symbol when they no longer resolve.
- **Diagrams** — Mermaid blocks render natively in GitHub, VS Code, and most Markdown
  viewers. ASCII diagrams are used where Mermaid is awkward (layered stacks, wireframes).
- **"Why" blocks** — shaded callouts labelled *Why* capture design rationale a code reader
  could not infer from the code itself. These are for reviewers.

---

## Related documents (outside this set)

| Document | Scope |
|----------|-------|
| [`../PRODUCT_SPEC.md`](../PRODUCT_SPEC.md) | What the product is for, who it serves |
| [`../FINANCIAL_MODEL.md`](../FINANCIAL_MODEL.md) | Every formula, sign convention, and rounding rule |
| [`../AI_AND_PRIVACY.md`](../AI_AND_PRIVACY.md) | Provider abstraction, what data leaves the host |
| [`../SECURITY_SELF_ASSESSMENT.md`](../SECURITY_SELF_ASSESSMENT.md) | Security posture, threat surface |
| [`../DESIGN_DECISIONS.md`](../DESIGN_DECISIONS.md) | UI visual contract, design tokens |
| [`../IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md) | What is built vs. planned |
| [`../TEST_PLAN.md`](../TEST_PLAN.md) | Test strategy in detail |