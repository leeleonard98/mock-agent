"""search_attractions — deterministic, in-memory attraction catalog (T3).

In a real system this would hit a vendor API. For the test we ship a small
hard-coded catalog so the agent has something to reason over and tests are
deterministic. Add cities/attractions freely.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.tools.registry import registry

# city -> list of attractions, ordered "best first"
_CATALOG: dict[str, list[dict[str, Any]]] = {
    "tokyo": [
        {"name": "Senso-ji Temple", "category": "culture", "rating": 4.6},
        {"name": "Shibuya Crossing", "category": "city", "rating": 4.5},
        {"name": "Tsukiji Outer Market", "category": "food", "rating": 4.4},
        {"name": "Ueno Park", "category": "nature", "rating": 4.3},
        {"name": "Akihabara", "category": "shopping", "rating": 4.2},
        {"name": "Meiji Shrine", "category": "culture", "rating": 4.6},
        {"name": "TeamLab Planets", "category": "art", "rating": 4.5},
    ],
    "kyoto": [
        {"name": "Fushimi Inari Shrine", "category": "culture", "rating": 4.7},
        {"name": "Arashiyama Bamboo Grove", "category": "nature", "rating": 4.5},
        {"name": "Kinkaku-ji (Golden Pavilion)", "category": "culture", "rating": 4.6},
        {"name": "Gion District", "category": "culture", "rating": 4.4},
        {"name": "Nishiki Market", "category": "food", "rating": 4.3},
        {"name": "Philosopher's Path", "category": "nature", "rating": 4.4},
    ],
    "osaka": [
        {"name": "Osaka Castle", "category": "culture", "rating": 4.4},
        {"name": "Dotonbori", "category": "food", "rating": 4.5},
        {"name": "Universal Studios Japan", "category": "theme park", "rating": 4.6},
        {"name": "Shinsekai", "category": "city", "rating": 4.2},
    ],
}


class SearchAttractionsArgs(BaseModel):
    city: str = Field(min_length=1, description="City name (case-insensitive)")
    limit: int = Field(default=5, ge=1, le=20, description="Max attractions to return")


def search_attractions(city: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return up to `limit` attractions for `city` (empty list if unknown city)."""
    key = city.strip().lower()
    items = _CATALOG.get(key, [])
    return [dict(a) for a in items[:limit]]


registry.register(
    name="search_attractions",
    description="Search popular attractions in a city. Returns name, category, rating.",
    func=search_attractions,
    args_model=SearchAttractionsArgs,
)
