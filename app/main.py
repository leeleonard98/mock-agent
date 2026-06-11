from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import chat


class HealthResponse(BaseModel):
    status: str
    db: str


_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Smart Travel Planner Agent", version="0.1.0")

    # Templates / static (created lazily so tests don't need them on disk to import)
    if _TEMPLATES_DIR.exists():
        app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/health", response_model=HealthResponse)
    def health(db: Session = Depends(get_db)) -> HealthResponse:
        try:
            db.execute(text("SELECT 1"))
            db_status = "ok"
        except SQLAlchemyError:
            db_status = "down"
        return HealthResponse(status="ok", db=db_status)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        templates: Jinja2Templates = request.app.state.templates
        return templates.TemplateResponse(request, "index.html", {})

    app.include_router(chat.router)

    return app


app = create_app()
