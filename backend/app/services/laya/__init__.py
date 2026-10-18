"""Laya adapter.

Wraps the documented Laya Python API:

    from laya import Router
    router = Router()
    result = router.predict(state, questions, model="multilingual", max_len=8192)

We never invent Laya functions beyond what the upstream package
documents. Missing checkpoints, import errors, and router failures all
produce ``LayaAssessment(status="unavailable", ...)`` — never fabricated
labels.
"""
