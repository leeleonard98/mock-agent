"""HTTP route to invoke a registered tool directly (T3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ValidationError

from app.tools import registry

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolInvokeRequest(BaseModel):
    args: dict[str, Any]


class ToolInvokeResponse(BaseModel):
    name: str
    result: Any


@router.get("", response_model=list[dict[str, Any]])
def list_tools() -> list[dict[str, Any]]:
    """Return the OpenAI tool-call schemas for all registered tools.

    Useful for the planner UI ("here's what I can do") and for tests.
    """
    return registry.openai_schemas()


@router.post("/{name}/invoke", response_model=ToolInvokeResponse)
def invoke_tool(name: str, payload: ToolInvokeRequest) -> ToolInvokeResponse:
    if name not in registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown tool: {name}"
        )
    try:
        result = registry.invoke(name, payload.args)
    except ValidationError as e:
        # Pydantic raised on the tool's args model — surface as 422 with details.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors()
        ) from e
    return ToolInvokeResponse(name=name, result=result)
