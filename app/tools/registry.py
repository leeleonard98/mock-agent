"""Tool registry — name → (callable, pydantic args model).

Validation is centralised here: every dispatch goes through pydantic, so a
malformed call surfaces as a clean ValidationError (caller turns it into 422).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


@dataclass(frozen=True)
class _ToolEntry:
    name: str
    description: str
    func: Callable[..., Any]
    args_model: type[BaseModel]


class _Registry:
    def __init__(self) -> None:
        self._tools: dict[str, _ToolEntry] = {}

    def register(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        args_model: type[BaseModel],
    ) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = _ToolEntry(name, description, func, args_model)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def invoke(self, name: str, args: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(name)
        entry = self._tools[name]
        validated = entry.args_model(**args)
        return entry.func(**validated.model_dump())

    def openai_schemas(self) -> list[dict[str, Any]]:
        """Emit OpenAI Chat Completions tool-call schemas.

        Forwards `$defs` so nested-model `$ref`s resolve. Without this the
        OpenAI tool-call validator rejects the schema (e.g. for
        ``generate_itinerary``'s ``attractions: list[_Attraction]``).
        """
        out: list[dict[str, Any]] = []
        for entry in self._tools.values():
            schema = entry.args_model.model_json_schema()
            parameters: dict[str, Any] = {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
            if "$defs" in schema:
                parameters["$defs"] = schema["$defs"]
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": entry.name,
                        "description": entry.description,
                        "parameters": parameters,
                    },
                }
            )
        return out


registry = _Registry()
