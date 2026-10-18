# Product Specification — MoneyPlant SME Finance Copilot

## 1. Vision

MoneyPlant is a privacy-aware **financial decision copilot** for small and medium-sized enterprises. It converts a business's historical records, current assumptions, and proposed actions into understandable financial projections and decision support.

The product answers questions like:

- How financially healthy is my business this month?
- Which costs are growing and why?
- I made a profit — so why is my cash tight?
- Can I afford to purchase more raw material / inventory?
- What happens to profit and cash if I produce 15% more next quarter?
- What if customers pay 30 days later than expected?
- Should I hire more staff, buy equipment, or postpone an expense?
- Which of three options best matches my financial goals?
- What data is missing before a reliable recommendation is possible?

## 2. Target users

Primary users are **owners, operators, and finance managers of SMEs** who do not have a dedicated finance department.

The product is designed for users who:

- Maintain records in spreadsheets or simple ledgers.
- Have incomplete or inconsistent financial data.
- Need to make purchasing, production, pricing, staffing, and cash-management decisions.
- Want clear explanations rather than accounting jargon.
- Prefer to keep business records on their own machine or private infrastructure.
- Want to choose between local AI inference and a hosted API.

## 3. Industry coverage

Five industry profiles ship as first-class adapters:

1. **Manufacturing / production** — clothing, furniture, light assembly. Richest demo: material → production → finished goods → sales.
2. **Retail / inventory-based commerce** — physical or online store. Inventory cost-of-goods-sold focus.
3. **Food service / small restaurants** — recipe cost, waste, perishables.
4. **Wholesale / distribution** — bulk purchase, longer payment cycles.
5. **Professional / service** — billable hours, project pricing.

A single canonical financial data model supports all five. Industry adapters extend the scenario input schema and add validation rules.

## 4. Core product capabilities

1. **Data import** — CSV and XLSX upload, column mapping, validation, partial-import with row-level error reporting, import history.
2. **Financial dashboard** — period-over-period revenue, cost, profit, cash; trend charts; health indicators; data-quality warnings.
3. **Deterministic financial engine** — pure functions, Decimal arithmetic, versioned, testable, reproducible.
4. **Production and operating simulator** — scenario inputs by industry, real-time recalculation, assumption panel, warnings.
5. **Scenario comparison** — baseline vs N alternatives, safe handling of zero baselines, trade-off summary tied to stated goals.
6. **Rule-based decision engine** — 8 initial rules, configurable thresholds, explicit severity, hard-constraint precedence.
7. **Laya integration** — bounded structured decision assessments; cannot override hard rules.
8. **LLM explanation layer** — local (Ollama) or hosted (OpenAI, Anthropic) provider, strict response schema validation, no silent fallback.
9. **Decision report** — printable, evidence-grounded, includes assumptions, caveats, model outputs, calculation timestamp.
10. **AI assistant** — chat grounded in computed results, identifies missing data, never invents facts.
11. **Privacy and settings** — explicit mode selector, real provider health checks, plain-language data-sharing disclosure.

## 5. Non-goals (anti-claims)

The product **does not**:

- Replace a qualified accountant, auditor, lender, or financial adviser.
- Claim regulatory certification (SEC, GAAP, IFRS, etc.).
- Provide bank integrations, audited accuracy, or third-party data provenance.
- Predict future business performance with statistical certainty. Sensitivity and scenario analysis are deterministic what-ifs, not forecasts.
- Guarantee external provider data retention or confidentiality.
- Make universal "best scenario" judgments without applying stated goals and constraints.

## 6. Scope by phase

### MVP (this codebase)

- 5 industry profiles, 2 fully seeded as demo data, 3 scaffolded.
- Local-only persistence (SQLite by default; Postgres-ready via `DATABASE_URL`).
- Local LLM (Ollama) + 2 external API providers (OpenAI, Anthropic).
- Single-tenant mode (no authentication); documented demo trust boundary.
- Browser support: latest Chrome, Firefox, Safari, Edge.

### Out of scope (explicitly deferred)

- Multi-tenant authentication, RBAC, audit logs.
- Real-time bank/POS/accounting integrations.
- Tax computation, depreciation schedules, multi-currency conversion policy beyond documented per-record currency.
- Mobile native apps; the web app is responsive.
- Statistical forecasting (ARIMA, ML, etc.); only deterministic sensitivity is provided.

## 7. Honest disclosure

Every AI-generated explanation must:

- Be traceable to a computed result or an explicit user assumption.
- Distinguish historical fact from projection from model interpretation.
- State when information is missing or unavailable.
- Never fabricate revenue, profit, costs, dates, market benchmarks, or regulatory requirements.
- Surface the provider that produced it and the model used.

## 8. Glossary

| Term | Definition |
|---|---|
| **Baseline** | The current state of the business used as the starting point of a scenario. |
| **Scenario** | A named set of input assumptions that the financial engine evaluates against a baseline. |
| **Scenario version** | An immutable snapshot of scenario inputs and the engine version that produced a result. |
| **Decision report** | A structured document explaining a single decision question, its evidence, and its recommendation. |
| **Laya assessment** | A bounded structured decision label produced by the Laya `Router().predict()` call. Advisory, never authoritative. |
| **Hard constraint** | A rule whose breach cannot be overridden by Laya or the LLM (e.g., negative closing cash). |