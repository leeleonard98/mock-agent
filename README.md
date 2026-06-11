# Agentic Coding Test — Scaffold

Barebones FastAPI + Postgres + OpenAI scaffold for a 2-hour agentic coding interview.

## Quickstart

```bash
cp .env.example .env                # edit OPENAI_API_KEY if you want real LLM calls
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

make up                             # start postgres on :5432
make migrate                        # apply initial migration
make test                           # run pytest (auto-creates app_test DB)
make run                            # uvicorn on :8000
```

Then hit `http://localhost:8000/health` and `http://localhost:8000/docs` (Swagger UI).

## Layout

- `app/main.py` — FastAPI factory, mounts routers, `/health`
- `app/config.py` — env-driven settings
- `app/db.py` — engine, session, `get_db` dependency
- `app/models.py` — SQLAlchemy `Base` and example `Item`
- `app/llm.py` — OpenAI wrapper with mock-friendly seam
- `app/routers/` — per-feature routers go here
- `tests/conftest.py` — transactional db fixture, async client, mock LLM fixture
- `alembic/` — migrations

## Per-feature loop (during the real test)

1. Add router under `app/routers/<feature>.py`, mount it in `app/main.py`.
2. If schema change: edit `app/models.py` → `make revision m="add foo"` → `make migrate`.
3. Write `tests/test_<feature>.py` with **≥3 non-trivial tests** (happy path, validation/error, persistence/side-effect).
4. `make test` green.
5. `git add -A && git commit -m "feat: <feature>"` — one feature per commit.

## LLM in tests

`app.llm.complete` is the only entry point for OpenAI calls. The `mock_llm` fixture in
`tests/conftest.py` monkeypatches it so tests never hit the network. Real calls require
`OPENAI_API_KEY` in `.env`.

## Security notes

- `.env` is gitignored; only `.env.example` is committed.
- DB credentials come from env, never hardcoded.
- All DB access goes through SQLAlchemy parameter binding.
- Pydantic validates every request and response.
- CORS is off by default — enable per-feature with explicit origins.
