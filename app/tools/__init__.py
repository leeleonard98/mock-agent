"""Tool calling system (T3).

Tools are plain Python functions wrapped in pydantic-validated arg models.
The registry exposes them by name, validates args, and emits OpenAI
function-calling schemas so an agent can pick them.

Adding a new tool: write a function + ArgsModel, then call register().
"""

from __future__ import annotations

from app.tools.registry import registry

# Import each tool module so its register() side-effect runs on app startup.
# Keep these imports here, not at the call site, to avoid forgetting one.
from app.tools import budget as _budget  # noqa: F401
from app.tools import itinerary as _itinerary  # noqa: F401
from app.tools import search as _search  # noqa: F401

__all__ = ["registry"]
