"""calculate_budget — pure-function trip budget breakdown (T3).

Returns a dict with accommodation, transport, activities, and total. Math is
deliberately simple and explainable: nights = days - 1, never negative.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.tools.registry import registry


class CalculateBudgetArgs(BaseModel):
    days: int = Field(ge=1, le=60, description="Total trip duration in days")
    accommodation_per_night: float = Field(ge=0, description="Cost per hotel night")
    transport_total: float = Field(ge=0, description="Total inter-city transport cost")
    activities_per_day: float = Field(ge=0, description="Average activities cost per day")


def calculate_budget(
    days: int,
    accommodation_per_night: float,
    transport_total: float,
    activities_per_day: float,
) -> dict[str, float]:
    nights = max(0, days - 1)
    accommodation = nights * accommodation_per_night
    activities = days * activities_per_day
    total = accommodation + transport_total + activities
    return {
        "accommodation": round(accommodation, 2),
        "transport": round(transport_total, 2),
        "activities": round(activities, 2),
        "total": round(total, 2),
    }


registry.register(
    name="calculate_budget",
    description=(
        "Estimate a trip budget. Inputs: days, accommodation_per_night, "
        "transport_total, activities_per_day. Returns breakdown + total."
    ),
    func=calculate_budget,
    args_model=CalculateBudgetArgs,
)
