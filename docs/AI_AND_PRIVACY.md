# AI and Privacy — MoneyPlant

This document covers the provider abstraction, the local and API paths, what data leaves the host, how responses are validated, and what is intentionally not done.

## 1. Provider abstraction

```python
class ExplanationProvider(Protocol):
    name: str
    def explain(self, context: ExplanationContext) -> Explanation: ...
    def health_check(self) -> ProviderStatus: ...
    def get_capabilities(self) -> Capabilities: ...
```

`ExplanationContext` carries:

- `business_industry: str`
- `reporting_period: str`
- `user_question: str`
- `computed_baseline: dict`  # compact metrics only
- `computed_scenarios: list[dict]`
- `rule_evaluations: list[dict]`
- `laya_assessment: dict | None`
- `assumptions: list[str]`
- `missing_information: list[str]`
- `business_goal: str | None`

A response is validated against the `Explanation` Pydantic model. Invalid responses are returned as `Explanation(status="unavailable", reason="...")` — never coerced.

## 2. Local provider — Ollama

- **Transport:** OpenAI-compatible HTTP at `http://localhost:11434/v1` (configurable).
- **Client:** `openai.OpenAI(base_url=..., api_key="ollama")`.
- **Models supported:** any model pulled into Ollama (e.g., `llama3.1:8b`, `qwen2.5:7b`).
- **Health check:** `client.models.list()`. If it raises, the provider is `unavailable`.
- **No silent fallback to API.** If `mode=local` and the health check fails, the user sees an actionable error.
- **First-run:** the user must run `ollama serve` and `ollama pull <model>` themselves. The settings page shows the exact commands.

## 3. API providers — OpenAI, Anthropic

- **Credentials:** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` from process env. Never accepted from the client. Never echoed back in any response.
- **Timeouts:** 30 s for explanation, 60 s for the assistant chat.
- **Rate limits:** surfaced verbatim from the provider; never fabricated.
- **Context minimization:** only fields from `ExplanationContext` are sent. Raw transactions, business names, and uploaded file contents are **not** sent.
- **Status disclosure:** the privacy settings page tells the user exactly which fields are included and links to the provider's retention policy.

## 4. Provider selection

`mode` is one of `local`, `openai`, `anthropic`. Stored per-business. The factory in `backend/app/services/llm/factory.py` returns the configured provider. If the configured provider is `unavailable`, the API returns 503 with a clear reason; the UI offers a retry or a switch.

## 5. Laya integration

Laya is a separate decision layer, not the generative LLM.

```python
from laya import Router
router = Router()
result = router.predict(state=state_dict, questions=questions_list, model="multilingual", max_len=8192)
# result = {"answers": [...], "routing": {"model": "..."}}
```

We:

- Use only documented Laya functions (`predict`, `predict_batch`, `load`).
- Pass a state dictionary describing the computed scenario, rule outcomes, business goal, and assumptions.
- Pass well-formed bounded questions (e.g., "Which risk category best describes this scenario: low, medium, high?").
- Normalize the response into `LayaAssessment` (question, label, probability, model_id, raw_response).
- Handle missing checkpoints, import errors, and router failures as `unavailable`.

**Hard constraints cannot be overridden.** If the rule engine identifies a hard cash-reserve breach, the final decision status is `reject` regardless of Laya's preference. Both outputs are preserved and shown side by side.

## 6. Prompt-injection defense

Imported spreadsheets, transaction descriptions, user notes, and other business text are **untrusted**. The backend never executes instructions found in business text. Specifically:

- Model prompts are constructed by the backend from typed fields only; user-supplied text appears as data, not as instructions.
- LLM outputs are validated against a schema; the only fields the UI trusts are the validated ones.
- Authoritative actions (saving a scenario, modifying thresholds) require application-level validation; the LLM cannot mutate the database directly.

## 7. Privacy settings page

The page at `/settings/privacy` exposes:

- **Mode selector** with a plain-language explanation of each option's data flow.
- **Provider health** — a real `health_check()` call, displayed with the timestamp and latency. No green check without a successful probe.
- **What is sent** — a static disclosure per provider of which fields leave the host.
- **No silent fallback** banner — visible at all times in API mode.

## 8. Data retention

- Imported files: stored as `ImportJob` records. The original uploaded bytes are kept on disk only if the user has not configured a cleanup policy (default: keep file metadata, discard raw bytes after 30 days). Configurable.
- Generated explanations: kept with the `DecisionReport` for reproducibility. Cleared when the report is deleted.
- External API logs: outside this application's control. The settings page links to each provider's data-retention policy.

## 9. What this design is NOT

- It is not a closed system. The provider abstraction allows adding more local or API providers by writing one class.
- It is not a guarantee about provider-side retention. Users choosing an API provider are informed.
- It is not an end-to-end encrypted system. A future iteration could add homomorphic or TEE-based inference, but it is out of scope.
- It is not a model-evaluation framework. LLM responses are validated for shape, not for correctness; correctness comes from the deterministic engine.