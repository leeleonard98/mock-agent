"""Tests for the tool calling system (T3)."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from app.tools import registry
from app.tools.budget import calculate_budget
from app.tools.itinerary import generate_itinerary
from app.tools.search import search_attractions


# ---------------------------------------------------------------------------
# Tool-level tests
# ---------------------------------------------------------------------------


def test_search_attractions_returns_list_of_typed_dicts() -> None:
    """search_attractions must return a non-empty list of dicts with the agreed shape."""
    result = search_attractions(city="Tokyo", limit=3)
    assert isinstance(result, list)
    assert len(result) == 3
    for item in result:
        assert {"name", "category", "rating"} <= set(item.keys())
        assert isinstance(item["name"], str) and item["name"]
        assert isinstance(item["rating"], (int, float))
        assert 0 <= item["rating"] <= 5

    # Different city should return different content (deterministic, not random)
    other = search_attractions(city="Kyoto", limit=2)
    assert len(other) == 2
    assert {a["name"] for a in result} != {a["name"] for a in other}


def test_search_attractions_supports_common_global_cities() -> None:
    """The catalog must include cities a typical user would ask about (Paris, NYC, etc.)."""
    for city in ("Paris", "New York", "London", "Bangkok", "Singapore"):
        result = search_attractions(city=city, limit=3)
        assert result, f"no attractions for {city}"
        assert len(result) >= 1


def test_calculate_budget_math_is_correct() -> None:
    """Budget math: nights * accommodation + transport + activities * days."""
    breakdown = calculate_budget(
        days=5,
        accommodation_per_night=120,
        transport_total=300,
        activities_per_day=40,
    )
    assert breakdown["accommodation"] == 4 * 120  # nights = days - 1
    assert breakdown["transport"] == 300
    assert breakdown["activities"] == 5 * 40
    assert breakdown["total"] == 4 * 120 + 300 + 5 * 40

    # Edge: 1-day trip → 0 nights of accommodation
    one_day = calculate_budget(
        days=1, accommodation_per_night=200, transport_total=50, activities_per_day=30
    )
    assert one_day["accommodation"] == 0
    assert one_day["total"] == 0 + 50 + 30


def test_generate_itinerary_produces_one_block_per_day() -> None:
    """generate_itinerary returns days with attractions assigned across them."""
    attractions = [{"name": f"A{i}", "category": "x", "rating": 4.0} for i in range(6)]
    plan = generate_itinerary(city="Tokyo", days=3, attractions=attractions)
    assert len(plan["days"]) == 3
    # Every day has at least one attraction; nothing duplicated across days
    seen: set[str] = set()
    for day in plan["days"]:
        assert day["attractions"], f"empty day: {day}"
        for a in day["attractions"]:
            assert a["name"] not in seen, "attraction duplicated across days"
            seen.add(a["name"])
    # All input attractions assigned
    assert seen == {a["name"] for a in attractions}


def test_generate_itinerary_handles_more_days_than_attractions() -> None:
    """Edge case: 5 days but only 2 attractions — every day still appears, no duplicates."""
    attractions = [{"name": "Only1", "category": "x", "rating": 4.0},
                   {"name": "Only2", "category": "y", "rating": 4.5}]
    plan = generate_itinerary(city="Sapporo", days=5, attractions=attractions)
    assert len(plan["days"]) == 5
    # Day numbers 1..5 in order
    assert [d["day"] for d in plan["days"]] == [1, 2, 3, 4, 5]
    # Exactly the 2 input attractions, no duplicates
    placed = [a for d in plan["days"] for a in d["attractions"]]
    assert len(placed) == 2
    assert {a["name"] for a in placed} == {"Only1", "Only2"}


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_lists_three_tools_and_provides_openai_schemas() -> None:
    """Registry exposes the three tools with valid OpenAI function-calling schemas."""
    names = set(registry.names())
    assert names == {"search_attractions", "calculate_budget", "generate_itinerary"}

    schemas = registry.openai_schemas()
    assert len(schemas) == 3
    for s in schemas:
        # OpenAI tool-call shape: {"type": "function", "function": {"name", "parameters", ...}}
        assert s["type"] == "function"
        fn = s["function"]
        assert fn["name"] in names
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]


def test_openai_schemas_have_no_dangling_refs() -> None:
    """Every $ref in an emitted schema must resolve inside that same schema's $defs.

    Regression guard: nested-model args (e.g. generate_itinerary's
    list[_Attraction]) used to lose their $defs and produce dangling refs.
    """
    schemas = registry.openai_schemas()
    ref_pattern = re.compile(r'"\$ref"\s*:\s*"#/\$defs/([^"]+)"')

    for s in schemas:
        params = s["function"]["parameters"]
        blob = json.dumps(params)
        refs = ref_pattern.findall(blob)
        if not refs:
            continue
        # Any ref present means $defs must exist and contain every referenced key
        assert "$defs" in params, (
            f"schema for {s['function']['name']} has $ref but no $defs: {blob}"
        )
        for ref in refs:
            assert ref in params["$defs"], f"dangling $ref to {ref} in {s['function']['name']}"


def test_registry_invoke_dispatches_to_correct_tool() -> None:
    """invoke(name, args) routes to the matching callable and validates args."""
    out = registry.invoke("search_attractions", {"city": "Osaka", "limit": 2})
    assert isinstance(out, list) and len(out) == 2

    # Unknown tool → KeyError
    with pytest.raises(KeyError):
        registry.invoke("does_not_exist", {})


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


async def test_tool_invoke_endpoint_happy_path(client: httpx.AsyncClient) -> None:
    """POST /tools/{name}/invoke executes the tool and returns its JSON result."""
    r = await client.post(
        "/tools/calculate_budget/invoke",
        json={
            "args": {
                "days": 5,
                "accommodation_per_night": 100,
                "transport_total": 200,
                "activities_per_day": 50,
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["total"] == 4 * 100 + 200 + 5 * 50


async def test_tool_invoke_unknown_tool_returns_404(client: httpx.AsyncClient) -> None:
    r = await client.post("/tools/unknown_tool/invoke", json={"args": {}})
    assert r.status_code == 404


async def test_tool_invoke_bad_args_returns_422(client: httpx.AsyncClient) -> None:
    """Missing required arg → 422 (registry validation, not 500)."""
    r = await client.post("/tools/calculate_budget/invoke", json={"args": {"days": 5}})
    assert r.status_code == 422


async def test_tool_invoke_generate_itinerary_via_http(client: httpx.AsyncClient) -> None:
    """End-to-end through the HTTP route + nested-model arg validation."""
    r = await client.post(
        "/tools/generate_itinerary/invoke",
        json={
            "args": {
                "city": "Tokyo",
                "days": 2,
                "attractions": [
                    {"name": "X", "category": "c", "rating": 4.5},
                    {"name": "Y", "category": "c", "rating": 4.0},
                    {"name": "Z", "category": "c", "rating": 3.9},
                ],
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "generate_itinerary"
    plan = body["result"]
    assert plan["city"] == "Tokyo"
    assert len(plan["days"]) == 2
    placed_names = [a["name"] for d in plan["days"] for a in d["attractions"]]
    assert sorted(placed_names) == ["X", "Y", "Z"]
