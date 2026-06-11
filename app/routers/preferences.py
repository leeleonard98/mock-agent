"""User preferences memory (T4).

Note: PUT is intentionally unauthenticated for the prototype — same as the
rest of the app's user_id-as-string convention. A production cut would gate
this behind real auth (header/JWT). See app/memory.py for the read helper.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.memory import load_preferences  # re-export
from app.models import UserPreference

router = APIRouter(prefix="/users", tags=["preferences"])


class PreferencesPut(BaseModel):
    preferences: dict[str, Any]


class PreferencesOut(BaseModel):
    user_id: str
    preferences: dict[str, Any]


@router.get("/{user_id}/preferences", response_model=PreferencesOut)
def get_preferences(user_id: str, db: Session = Depends(get_db)) -> PreferencesOut:
    return PreferencesOut(user_id=user_id, preferences=load_preferences(db, user_id))


@router.put("/{user_id}/preferences", response_model=PreferencesOut)
def put_preferences(
    user_id: str, payload: PreferencesPut, db: Session = Depends(get_db)
) -> PreferencesOut:
    """Upsert each key in `payload.preferences`. Other keys are left untouched."""
    existing = {
        r.key: r
        for r in db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        .scalars()
        .all()
    }
    for key, value in payload.preferences.items():
        if key in existing:
            existing[key].value = value
        else:
            db.add(UserPreference(user_id=user_id, key=key, value=value))
    db.commit()
    return PreferencesOut(user_id=user_id, preferences=load_preferences(db, user_id))


__all__ = ["router", "load_preferences"]
