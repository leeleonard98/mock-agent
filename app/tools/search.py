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
    "paris": [
        {"name": "Eiffel Tower", "category": "landmark", "rating": 4.6},
        {"name": "Louvre Museum", "category": "art", "rating": 4.7},
        {"name": "Notre-Dame Cathedral", "category": "culture", "rating": 4.5},
        {"name": "Montmartre & Sacré-Cœur", "category": "culture", "rating": 4.5},
        {"name": "Musée d'Orsay", "category": "art", "rating": 4.7},
        {"name": "Seine River Cruise", "category": "city", "rating": 4.4},
        {"name": "Luxembourg Gardens", "category": "nature", "rating": 4.5},
    ],
    "new york": [
        {"name": "Central Park", "category": "nature", "rating": 4.7},
        {"name": "Statue of Liberty", "category": "landmark", "rating": 4.5},
        {"name": "Metropolitan Museum of Art", "category": "art", "rating": 4.7},
        {"name": "Times Square", "category": "city", "rating": 4.3},
        {"name": "Brooklyn Bridge", "category": "landmark", "rating": 4.6},
        {"name": "High Line", "category": "nature", "rating": 4.5},
    ],
    "london": [
        {"name": "British Museum", "category": "culture", "rating": 4.7},
        {"name": "Tower of London", "category": "landmark", "rating": 4.5},
        {"name": "Hyde Park", "category": "nature", "rating": 4.6},
        {"name": "Borough Market", "category": "food", "rating": 4.5},
        {"name": "Tate Modern", "category": "art", "rating": 4.5},
        {"name": "Westminster Abbey", "category": "culture", "rating": 4.6},
    ],
    "bangkok": [
        {"name": "Grand Palace", "category": "culture", "rating": 4.5},
        {"name": "Wat Pho", "category": "culture", "rating": 4.6},
        {"name": "Chatuchak Weekend Market", "category": "shopping", "rating": 4.4},
        {"name": "Chao Phraya River", "category": "nature", "rating": 4.3},
        {"name": "Khao San Road", "category": "city", "rating": 4.1},
    ],
    "singapore": [
        {"name": "Gardens by the Bay", "category": "nature", "rating": 4.7},
        {"name": "Marina Bay Sands SkyPark", "category": "landmark", "rating": 4.5},
        {"name": "Sentosa Island", "category": "theme park", "rating": 4.4},
        {"name": "Hawker Chan / Maxwell Food Centre", "category": "food", "rating": 4.5},
        {"name": "Chinatown Heritage Centre", "category": "culture", "rating": 4.3},
    ],
    "rome": [
        {"name": "Colosseum", "category": "landmark", "rating": 4.7},
        {"name": "Vatican Museums", "category": "art", "rating": 4.7},
        {"name": "Trevi Fountain", "category": "landmark", "rating": 4.6},
        {"name": "Roman Forum", "category": "culture", "rating": 4.5},
        {"name": "Trastevere", "category": "food", "rating": 4.4},
    ],
    "barcelona": [
        {"name": "Sagrada Família", "category": "landmark", "rating": 4.7},
        {"name": "Park Güell", "category": "art", "rating": 4.5},
        {"name": "La Rambla", "category": "city", "rating": 4.2},
        {"name": "Gothic Quarter", "category": "culture", "rating": 4.5},
        {"name": "Barceloneta Beach", "category": "nature", "rating": 4.3},
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
