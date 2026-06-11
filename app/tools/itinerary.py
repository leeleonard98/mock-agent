"""generate_itinerary — distribute attractions across days (T3).

Round-robin assignment so each day gets at least one attraction (assuming
attractions >= days) and no attraction is repeated.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.tools.registry import registry


class _Attraction(BaseModel):
    name: str
    category: str | None = None
    rating: float | None = None


class GenerateItineraryArgs(BaseModel):
    city: str = Field(min_length=1)
    days: int = Field(ge=1, le=30)
    attractions: list[_Attraction] = Field(default_factory=list)


def generate_itinerary(
    city: str, days: int, attractions: list[dict[str, Any]] | list[_Attraction]
) -> dict[str, Any]:
    # Normalise to dicts (works whether the caller passed dicts or pydantic models)
    items: list[dict[str, Any]] = [
        a if isinstance(a, dict) else a.model_dump() for a in attractions
    ]

    plan: list[dict[str, Any]] = [{"day": d + 1, "attractions": []} for d in range(days)]
    for i, a in enumerate(items):
        plan[i % days]["attractions"].append(a)

    return {"city": city, "days": plan}


registry.register(
    name="generate_itinerary",
    description=(
        "Distribute a list of attractions across N days into a day-by-day plan."
    ),
    func=generate_itinerary,
    args_model=GenerateItineraryArgs,
)
