# Agentic Coding Test — Barebones Scaffold

**Date:** 2026-06-11
**Purpose:** Pre-built starting point for a 2-hour agentic coding interview. Optimised for the test's scoring rules: per-feature commits, ≥3 non-trivial tests per feature, no obvious security flaws, "agentic / GenAI first" hint.

## Goals

1. Boot a working FastAPI + Postgres app in one command.
2. Make the per-feature loop (write code → write 3 tests → commit) as short as possible.
3. Have an LLM client wired up so "GenAI" features are a one-line call away.
4. Pass a basic security review on first inspection.

## Non-goals

- A frontend. Add only if a specific feature requires it during the real 2 hours.
- Auth. Add when a feature demands it.
- CI, deployment, observability beyond a `/health` endpoint.

## Stack

- **Python 3.11+**, FastAPI, SQLAlchemy 2.x, Alembic, pydantic-settings
- **Postgres 16** via Docker Compose on `:5432`
- **OpenAI Python SDK** for LLM calls (key from env; absence does not break boot)
- **pytest + httpx.AsyncClient** for tests; transactional rollback per test
- **uv** or plain `pip` + `requirements.txt` (pick whichever the candidate is fastest with — default to `requirements.txt` for portability)

## Repo layout

```
mock/
├── docker-compose.yml           # postgres + (optional) app service
├── Dockerfile                   # app image (optional, compose can mount source)
├── .env.example                 # committed; documents required vars
├── .gitignore                   # ignores .env, __pycache__, .venv, etc.
├── Makefile                     # up / down / test / migrate / revision / fmt
├── pyproject.toml               # deps + tool config (ruff, pytest)
├── README.md                    # quickstart + per-feature workflow
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/                # initial migration committed
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, /health
│   ├── config.py                # pydantic-settings (DATABASE_URL, OPENAI_API_KEY)
│   ├── db.py                    # engine, SessionLocal, get_db dependency
│   ├── models.py                # SQLAlchemy Base + one example model
│   ├── llm.py                   # OpenAI client wrapper (lazy init)
│   └── routers/
│       └── __init__.py          # empty; per-feature routers go here
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # client + db fixtures, transactional rollback
│   └── test_health.py           # 3 tests demonstrating the pattern
└── docs/
    └── superpowers/specs/       # this file lives here
```

## Components

### `app/config.py`
`Settings` BaseSettings reads `DATABASE_URL`, `OPENAI_API_KEY`, `APP_ENV`. `.env` file optional. Cached via `lru_cache`.

### `app/db.py`
- `engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)`
- `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`
- `get_db()` dependency yields a session, closes after request.

### `app/models.py`
- `Base = declarative_base()`
- One example `Item(id, name, created_at)` model so the initial Alembic migration has something to migrate. Easy to delete or keep.

### `app/main.py`
- `create_app()` factory returning `FastAPI` instance.
- Mounts routers from `app.routers`.
- `/health` returns `{"status": "ok", "db": "ok" | "down"}` after a `SELECT 1`.

### `app/llm.py`
- `get_openai_client()` lazily constructs `openai.OpenAI()` using the env key.
- Raises a clear error if called without a key set, but importing the module never fails.
- Single `complete(prompt: str, model: str = "gpt-4o-mini") -> str` helper to keep feature code one-liner-ish.

### `tests/conftest.py`
- Session-scoped engine pointed at a separate test DB (`DATABASE_URL` overridden via env in tests, or appended `_test`).
- Per-test fixture opens a connection, begins a transaction, binds a session, yields, rolls back. Standard SQLAlchemy "transactional tests" pattern.
- `client` fixture: `httpx.AsyncClient(app=app, base_url="http://test")`.

### `tests/test_health.py` (the pattern)
1. `/health` returns 200 with `status=ok` when DB up.
2. `/health` includes `db` field equal to `"ok"`.
3. `/health` content-type is `application/json` and body is valid JSON shape (uses pydantic schema).

## Data flow

Request → FastAPI route → `Depends(get_db)` session → SQLAlchemy model ops → pydantic response model → JSON. LLM features additionally call `app.llm.complete()` and persist the result through the same session.

## Security baseline

- `.env` gitignored; `.env.example` has placeholders only, no real secrets.
- Postgres credentials come from env, not hardcoded in compose.
- DB role used by app is the default compose-created user (acceptable for a local test); do NOT use `postgres` superuser in app code paths.
- All DB access via SQLAlchemy parameter binding — no f-string SQL anywhere.
- Pydantic models on every request and response (no raw dicts back to the client).
- CORS not enabled in scaffold; add per-feature with explicit origins.
- OpenAI key never logged; LLM wrapper does not echo prompts/responses to stdout.

## Per-feature workflow (during the real 2 hours)

1. `git checkout main` (already on it)
2. Create `app/routers/<feature>.py` with the endpoint(s).
3. If schema change: edit `app/models.py`, then `make revision m="add foo"`, then `make migrate`.
4. Write `tests/test_<feature>.py` with ≥3 non-trivial tests:
   - Happy path with realistic data
   - Validation / error path (4xx)
   - Persistence or side-effect verification (DB row exists, LLM called, etc.)
5. `make test` — green.
6. `git add -A && git commit -m "feat: <feature>"` — one feature per commit (scoring rule).

## Open questions / deferred decisions

- **Frontend:** deferred. If the real test rewards UI, add Vite + minimal React or even server-rendered Jinja templates as the first feature.
- **Auth:** deferred. JWT via `python-jose` if needed.
- **Background jobs / agent loops:** deferred. If the real test asks for an "agent that does X over Y," wire a simple `while not done` loop calling `llm.complete` — the scaffold doesn't need Celery/Redis day 1.
