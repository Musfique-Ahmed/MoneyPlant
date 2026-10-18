"""Security primitives.

Authentication is intentionally not implemented in MVP. The single-tenant
trust boundary is documented in ``docs/IMPLEMENTATION_STATUS.md``. This
module exists to provide a place for future auth code without scattering
imports.
"""

from __future__ import annotations


def is_demo_mode() -> bool:
    """Return True when the application is running without authentication.

    Used by the API surface to omit sensitive workspace operations in the
    public OpenAPI description, and by the frontend to enable the
    "single-tenant" banner on the privacy settings page.
    """
    return True
