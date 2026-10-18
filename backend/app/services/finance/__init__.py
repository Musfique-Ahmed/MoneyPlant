"""Deterministic financial engine.

Every public function here is a pure function of its arguments. There are
no I/O operations, no time-of-day dependencies, no random sampling, no LLM
calls. The engine has no awareness of FastAPI or the database; callers
parse Pydantic schemas and pass plain primitives.
"""