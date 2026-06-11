from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db


class HealthResponse(BaseModel):
    status: str
    db: str


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Coding Test Scaffold", version="0.1.0")

    @app.get("/health", response_model=HealthResponse)
    def health(db: Session = Depends(get_db)) -> HealthResponse:
        try:
            db.execute(text("SELECT 1"))
            db_status = "ok"
        except SQLAlchemyError:
            db_status = "down"
        return HealthResponse(status="ok", db=db_status)

    # Per-feature routers mount here, e.g.:
    # from app.routers import items
    # app.include_router(items.router)

    return app


app = create_app()
