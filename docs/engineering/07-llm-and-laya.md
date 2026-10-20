# Chapter 07 — LLM Providers & Laya Adapter

> *The LLM's job is to explain a fixed verdict. The Laya's job is to softly score
> qualities the rules can't measure. Both fade gracefully when they're not available.*

The LLM is a *presenter*. It is the last thing the user sees, never the first thing that
matters. This chapter describes how that contract is implemented and protected.

---

## 7.1 The provider abstraction

```python
# backend/app/services/llm/base.py
class ExplanationProvider(Protocol):
    def explain(self, context: ExplanationContext) -> Explanation: ...
    def health_check(self) -> ProviderHealth: ...
    def get_capabilities(self) -> Capabilities: ...
```

Three implementations, one interface.

| Mode        | Class               | Health probe                              | Model (default)         |
|-------------|---------------------|-------------------------------------------|-------------------------|
| `local`     | `OllamaProvider`    | `GET /api/tags` on `ai_local_base_url`    | `llama3.1:8b`           |
| `openai`    | `OpenAIProvider`    | `client.models.list()`                    | `gpt-4o-mini` (configurable) |
| `anthropic` | `AnthropicProvider` | `client.messages.create` minimum probe    | `claude-3-5-sonnet-latest` (configurable) |

```
   ┌─────────────────────────────────────────────────────────────────┐
   │  /api/ai/providers           list_providers()                  │
   │  /api/ai/health              for p in list_providers():        │
   │                                p.health_check()                │
   │  /api/ai/assistant/chat       get_provider().explain(...)       │
   │                                                                  │
   │  /api/decisions/{id}/explain  get_provider().explain(...)        │
   └─────────────────────────────────────────────────────────────────┘
```

The selection rule is in `llm/factory.py:12 get_provider(mode)`:

```
   if mode is None → use Settings.ai_default_mode (default = "local")
   if mode is "local"     → OllamaProvider()
   if mode is "openai"    → OpenAIProvider()
   if mode is "anthropic" → AnthropicProvider()
   else                    → OllamaProvider()   (fallback, never a 500)
```

The unknown-mode fallback is on purpose. A user with a misconfigured `AI_DEFAULT_MODE`
should still get a working explanation path — they'll just be using the local provider
until the config is fixed.

---

## 7.2 The health contract

```python
# backend/app/services/llm/base.py:23
class ProviderStatus(str, Enum):
    OK              = "ok"               # probe succeeded, model produced a sample
    UNAVAILABLE     = "unavailable"      # probe failed cleanly (timeout, refused, 5xx)
    MISCONFIGURED   = "misconfigured"    # API key missing or invalid

class ProviderHealth(BaseModel):
    mode: ProviderMode          # "local" | "openai" | "anthropic"
    status: ProviderStatus      # closed enum above
    model: str                  # "llama3.1:8b" | "gpt-4o-mini" | ...
    latency_ms: int | None      # populated when probe ran; None otherwise
    checked_at: datetime        # server time of the probe
    reason: str | None = None   # human-readable why-not, present iff status != OK
```

Three states. **No "pending", no "unknown", no soft-success.**

```
   ┌─────────────────────────────────────────────────────────────────┐
   │   ok              ─→ the provider produced a real sample       │
   │   unavailable     ─→ probe failed; reason populated             │
   │   misconfigured   ─→ keys are missing/invalid; reason populated │
   │                                                                 │
   │   The frontend renders OK as the green chip, anything else      │
   │   as the gray "unavailable" chip with the reason shown on     │
   │   hover. The Explain button is disabled when status != OK.     │
   └─────────────────────────────────────────────────────────────────┘
```

### Why no "unknown"

The temptation to return `ok` or `unknown` for "we haven't probed yet" is real. It is
also wrong: the UI must never show a green chip it cannot stand behind. Probe on demand
when the UI needs the answer, and return one of the three real states. (`apps/web/app/(app)/assistant/page.tsx:48`
polls `/api/ai/health` every 60 seconds when the Assistant tab is open, exactly to keep
the chip honest.)

---

## 7.3 The explanation contract

```python
# backend/app/services/llm/base.py:44
class Explanation(BaseModel):
    status: Literal["ok", "unavailable"]           # was the call successful?
    reason: str | None = None                      # populated when status != ok
    provider: str                                 # "ollama" | "openai" | "anthropic"
    model: str                                     # resolved model name
    mode: ProviderMode                             # "local" | "openai" | "anthropic"

    summary: str | None = None
    recommendation: str | None = None              # pre-formatted, UI-friendly

    supporting_evidence: list[str]                # quoted numbers from inputs
    key_risks: list[str]
    assumptions: list[str]
    missing_information: list[str]
    alternatives: list[str] = []
    next_actions: list[str] = []
    limitations: list[str]                         # explicit caveats

    raw: dict | None = None                        # the raw provider response (debug)
```

The shape is the *consumer contract*. Whether a provider is OpenAI or Ollama, the
explanation that the dashboard renders is structurally identical.

---

## 7.4 The `ExplanationContext` payload — what crosses the wire

```python
# backend/app/services/llm/base.py:62
class ExplanationContext(BaseModel):
    business_industry: str
    reporting_period: str
    user_question: str | None
    computed_baseline: dict              # financial summary, pre-quantised strings
    computed_scenarios: list[dict]       # list of result snapshots, pre-quantised
    rule_evaluations: list[dict]         # the 8 RuleEvaluation records (no LLM)
    laya_assessment: dict | None = None
    assumptions: list[str]
    missing_information: list[str]
    business_goal: str | None = None
```

Notice what is *not* in there:

- **No raw transactions.** Every number is a *pre-rendered summary*. The model cannot
  reconstruct the underlying ledger.
- **No PII.** Customer / supplier strings are scrubbed or never included.
- **No file paths, no source files.** The model has nothing to leak if it hallucinates.

The `computed_*` payloads come from `insights/engine.py` and `services/finance/`'s
formatters — they are strings with currency and unit suffixes already attached.

---

## 7.5 The "explain" pipeline

```
POST /api/decisions/{id}/explain
        │
        ▼
   load DecisionReport + LlmExplanation (if any)
        │
        ├─► if cached and provider unchanged → return cached Explanation
        │
        ▼ otherwise:
   build ExplanationContext:
        · business_industry from Business.industry
        · reporting_period from current month
        · rule_evaluations from DecisionReport.rule_evaluations (verbatim)
        · computed_baseline + computed_scenarios from
          insights/engine.py:build_summary_for_context(...)
        · laya_assessment from DecisionReport.laya_assessments
        · user_question from request body (optional)
        │
        ▼
   provider.health_check()
        │
        ├─► status != OK → return Explanation{status:"unavailable", reason:...}
        │
        ▼ otherwise:
   provider.explain(context)
        │
        ├─► structured prompt asking for the shape of `Explanation`
        ├─► extract JSON; fall back to "unavailable" on parse failure
        ▼
   persist LlmExplanation row (1:1 with DecisionReport)
        │
        ▼
   return Explanation
```

The provider implementations (`ollama_provider.py`, `openai_provider.py`,
`anthropic_provider.py`) each share the same prompt template (see
`OllamaProvider.explain`): a structured "respond with this JSON shape" instruction,
plus a small cap on input tokens and a deterministic temperature where the provider
allows. If the response fails to parse as JSON, the call returns
`Explanation(status="unavailable", reason="parse_failed:...")` and never raises.

### Caching

A successful `Explanation` is persisted as a row in `llm_explanations` keyed to the
decision report id. A repeat call with the same `provider_mode` returns the cached
record. The "Explain" button on the UI is therefore an idempotent action in the
common case — the user can click it freely without re-charging the LLM provider.

---

## 7.6 The Assistant chat

`POST /api/ai/assistant/chat` is the other LLM endpoint. It is the only place
end-users have a freeform conversation with the model.

```
   request:
      { message: str, business_id?: UUID, _dashboard_context?: {...} }
   response:
      { reply: str, provider: str, model: str, mode: str, suggestions?: list[str] }
```

The `_dashboard_context` is an optional payload injected by the UI that carries the
*current* dashboard's pre-rendered summary strings. It is structurally identical to
`ExplanationContext.computed_*` fields.

```
   ┌─────────────────────────────────────────────────────────────────┐
   │  what the LLM gets in /assistant/chat:                         │
   │                                                                 │
   │    {                                                            │
   │      message: "Why did cash drop in March?",                   │
   │      business_industry: "manufacturing",                        │
   │      computed_baseline: {...summary strings...},                │
   │      computed_scenarios: [...],                                 │
   │      alerts: [...],                                             │
   │      financing: {...}                                           │
   │    }                                                            │
   │                                                                 │
   │    ↑ no raw transactions, no source files, no PII               │
   └─────────────────────────────────────────────────────────────────┘
```

The chat endpoint also performs a `health_check` first and returns
`{ reply: "AI assistant is currently unavailable", unavailable: true, ... }` when
the provider is down — never a 503, never a stack trace, never a fabricated answer.

---

## 7.7 Laya adapter

The Laya adapter implements a soft-assessment service that scores scenarios on
qualitative dimensions the rules can't see. It is optional — `laya` is a separately
installed Python package. When missing, the adapter returns
`status="unavailable"` answers and the verdict is unaffected.

```
   ┌─────────────────────────────────────────────────────────────────┐
   │   Laya is a system that responds to natural-language            │
   │   questions with structured answer kinds:                       │
   │                                                                 │
   │      CHOICE   →  one of {low, medium, high}                      │
   │      SCORE    →  an integer 1..5                                │
   │      NOUL     →  one of {yes, no, unclear}                      │
   │                                                                 │
   │   MoneyPlant always asks the same three default questions:    │
   │                                                                 │
   │      Q1: risk_category     → low / medium / high                │
   │      Q2: feasibility_score → 1..5                               │
   │      Q3: aligns_with_goal  → yes / no / unclear                 │
   │                                                                 │
   │   The answers are stored on the DecisionReport as advisory     │
   │   scores, never as inputs to overall_status.                   │
   └─────────────────────────────────────────────────────────────────┘
```

### Adapter contract

```python
# backend/app/services/laya/adapter.py:98
def assess_scenario(
    result_dict: dict,
    rule_evaluations: list[dict],
    business_goal: str | None,
) -> list[LayaAssessment]:
    """
    Returns N LayaAssessment records (N == len(default_questions(industry))).
    Never raises. On import failure or provider error: returns records with
    status='unavailable' and a synthetic rationale.
    """
```

The three records are returned in display order:

```
  Risk category:  low / medium / high    (CHOICE)
  Feasibility:    1..5                   (SCORE)
  Aligns with goal: yes / no / unclear   (NOUL)
```

Each carries a `rationale` string the Laya provider returned alongside the answer.

### Fallback policy

```python
# backend/app/services/laya/adapter.py:109
if not settings.has_laya:
    return [
        LayaAssessment(
            question=q,
            status="unavailable",
            rationale="Soft assessment is not configured for this environment.",
        )
        for q in default_questions(industry)
    ]
```

The `has_laya` flag is determined by `Settings.has_laya` (`config.py:96`), which
checks both an API key (if remote) and the model name/device configuration. The
adapter never raises `ImportError` to the caller.

---

## 7.8 Provider factory and the dependency inversion

The factory is a small file, but it is the only seam in the LLM contract:

```python
# backend/app/services/llm/factory.py:25
def list_providers() -> list[ExplanationProvider]:
    return [OllamaProvider(), OpenAIProvider(), AnthropicProvider()]
```

Each provider is **stateless and per-call**. There is no connection pooling across
requests; the factories construct a new client per `explain()` call. That trades a bit
of throughput for the *absence of state*: a worker restart cannot strand a request
on a dead client.

### What this means in practice

- Adding a fourth provider is one file plus one branch in `get_provider`.
- A provider that needs secrets does so via `Settings.has_*` — the secret value is
  read on each call inside the provider. There is no shared "secret cache".
- A provider that fails its own health check returns `Explanation(status="unavailable")`
  inside `explain()` itself, bypassing the framework's `health_check()` step.

---

## 7.9 The "explain" prompt template (conceptual)

All three providers use a common prompt skeleton:

```
   ROLE
     You are the presenter for a finance copilot. A rule engine has already
     decided that a scenario is {overall_status}. Your job is to explain, in
     clear language, why. You MUST NOT contradict the verdict, change the
     verdict, or make recommendations about whether to proceed.

   INPUT
     business_industry: {industry}
     reporting_period: {period}
     computed_baseline: {baseline}
     computed_scenarios: {scenarios}
     rule_evaluations: {rules}
     laya_assessment: {laya or null}
     assumptions: {assumptions}
     missing_information: {missing_information}
     business_goal: {goal or null}

   TASK
     Respond in JSON:
       { "summary":         one sentence, the bottom line,
       { "recommendation":  short paragraph, what the user should do next,
       { "supporting_evidence": quoted numbers/facts,
       { "key_risks":       bullets,
       { "assumptions":     bullets,
       { "missing_information": bullets,
       { "alternatives":    bullets,
       { "next_actions":    bullets,
       { "limitations":     bullets describing what the rule engine cannot decide }

   CONSTRAINTS
     · Do not invent numbers. Use only what is in the INPUT.
     · Never recommend a different overall_status.
     · Be specific. Cite fields when relevant.
```

Each provider implementation differs only in:

- Transport (httpx vs SDK client)
- Function-call request schema
- JSON extraction strategy (some return JSON natively; some need a regex extract)

The contract is the same.

---

## 7.10 Failure modes and how they surface

| Failure | Status returned | Surfaced in UI |
|---|---|---|
| Ollama not running | `Explanation{status:"unavailable", reason:"ollama not reachable"}` | "AI assistant is currently unavailable" + grayed chip |
| OpenAI 401 | `ProviderHealth{status:"misconfigured", reason:"invalid OPENAI_API_KEY"}` | Misconfigured badge + reason on hover |
| OpenAI 429 | `Explanation{status:"unavailable", reason:"rate_limited"}` | "Try again later" inline |
| LLM output not parseable as JSON | `Explanation{status:"unavailable", reason:"parse_failed"}` | "AI assistant returned an unexpected response" |
| Laya import missing | Three `LayaAssessment(status:"unavailable")` | "Soft assessment unavailable — verdict still authoritative" panel |
| Laya timeout | Same as above, with `reason:"laya_timeout"` | Same panel |

Every failure path is bounded by the contract: **either we got a real `Explanation` or
we got a `status="unavailable"` one with a reason**. We never return a 500 from the LLM
hot path. We never return a fabricated confident answer.

---

## 7.11 Configuration reference

```python
# config.py
ai_default_mode: str = "local"
ai_local_base_url: str = "http://localhost:11434/v1"
ai_local_model: str = "llama3.1:8b"

# present iff set in env
openai_api_key: str | None
anthropic_api_key: str | None

# Laya
laya_api_key: str | None
laya_model: str | None
laya_device: Literal["cpu", "cuda", "mps", "xpu"] = "cpu"

# Logging (privacy)
log_redact_financial: bool = True
```

**Privacy defaults:**

- `log_redact_financial=True` strips Decimal-shaped strings from any field whose name
  looks like a money field at log format time.
- The `/api/config/public` route returns only safe booleans — whether each provider is
  reachable, what mode is configured, never the keys.

---

## 7.12 The "explain-only" contract, stated one more time

```
   ┌─────────────────────────────────────────────────────────────────┐
   │                                                                 │
   │   The LLM is part of the system under two constraints:          │
   │                                                                 │
   │     1. it cannot see raw transactions,                          │
   │     2. it cannot change the verdict.                            │
   │                                                                 │
   │   Both constraints are enforced in code, not policy:            │
   │                                                                 │
   │     · The ExplanationContext excludes raw transactions by      │
   │       construction (Definition 7.4).                            │
   │     · The decision evaluator does not import any provider      │
   │       module (Code 6.1).                                        │
   │     · The /explain endpoint is a separate route on a separate │
   │       record, persisted after the verdict (Code 6.7).           │
   │     · The UI shows the verdict before the LLM output and an   │
   │       explicit disclaimer on the LLM output (Code 6.8).         │
   │                                                                 │
   │   These four constraints are the architectural shape that     │
   │   keeps the product honest.                                     │
   │                                                                 │
   └─────────────────────────────────────────────────────────────────┘
```

---

## 7.13 Extending this

### Adding a new LLM provider

1. Create `app/services/llm/<name>_provider.py`.
2. Implement `explain`, `health_check`, `get_capabilities` against the protocol.
3. Add `<NAME>_API_KEY` (or equivalent) to `Settings` and the `has_<name>` flag.
4. Register in `llm/factory.py:get_provider`.
5. Add a `ProviderMode` enum value.
6. Add a clear "Sonnet-style" prompt template that matches the contract.
7. Test, including the parse-failure and rate-limit paths.

### Replacing the Laya provider

The Laya boundary is much more loosely coupled than the LLM one. To replace Laya with
another soft-assessment provider:

1. Edit `app/services/laya/adapter.py` to call the new provider inside `assess_scenario`.
2. Preserve the three-default-questions contract.
3. Preserve the `status="unavailable"` fallback.
4. Update the Zod mirror for `LayaAssessment` if you change the shape.

### Removing the LLM entirely

That is also supported. With `AI_DEFAULT_MODE` left blank and no providers reachable,
both `/api/ai/health` and `/decisions/{id}/explain` return `unavailable` shapes; the
Assistant page renders an empty state; the rest of the product works unchanged. The
documentation in `docs/AI_AND_PRIVACY.md` covers the privacy implications.

---

*Next: [Chapter 08 — Ingestion pipeline](08-ingestion.md)*