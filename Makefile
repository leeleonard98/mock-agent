.PHONY: help up down logs psql migrate revision test run fmt clean

help:
	@echo "make up         - start postgres"
	@echo "make down       - stop postgres"
	@echo "make logs       - tail db logs"
	@echo "make psql       - open psql shell"
	@echo "make migrate    - apply alembic migrations to dev DB"
	@echo "make revision m=\"msg\" - create new alembic revision (autogenerate)"
	@echo "make test       - run pytest (creates app_test DB if missing)"
	@echo "make run        - run uvicorn dev server on :8000"
	@echo "make fmt        - run ruff format"

up:
	docker compose up -d
	@echo "waiting for postgres..."
	@until docker compose exec -T db pg_isready -U $${POSTGRES_USER:-app} >/dev/null 2>&1; do sleep 1; done
	@echo "postgres ready on :5432"

down:
	docker compose down

logs:
	docker compose logs -f db

psql:
	docker compose exec db psql -U $${POSTGRES_USER:-app} -d $${POSTGRES_DB:-app}

migrate:
	alembic upgrade head

revision:
	@if [ -z "$(m)" ]; then echo 'usage: make revision m="message"'; exit 1; fi
	alembic revision --autogenerate -m "$(m)"

test:
	@docker compose exec -T db psql -U $${POSTGRES_USER:-app} -d $${POSTGRES_DB:-app} \
		-tc "SELECT 1 FROM pg_database WHERE datname = 'app_test'" | grep -q 1 || \
		docker compose exec -T db psql -U $${POSTGRES_USER:-app} -d $${POSTGRES_DB:-app} \
		-c "CREATE DATABASE app_test"
	pytest -v

run:
	uvicorn app.main:app --reload --port 8000

fmt:
	ruff format .
	ruff check --fix .

clean:
	docker compose down -v
