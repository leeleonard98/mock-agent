"""User memory helpers (T4).

`load_preferences` is the pure-data accessor; the HTTP router and the
planner agent both depend on this module so they don't depend on each other.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserPreference


def load_preferences(db: Session, user_id: str) -> dict[str, Any]:
    """Return all (key, value) preferences for `user_id` as a flat dict."""
    rows = (
        db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
        .scalars()
        .all()
    )
    return {r.key: r.value for r in rows}
