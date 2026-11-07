PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup backend-install frontend-install dev frontend-dev test e2e seed lint build up down migrate migrate-down backup restore prune-backups load-test

setup: backend-install frontend-install

backend-install:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements-dev.txt

frontend-install:
	cd frontend && npm install

dev:
	cd backend && ../$(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && npm run dev

test:
	cd backend && ../$(PYTHON) -m pytest

e2e:
	cd frontend && npm run test:e2e

seed:
	cd backend && ../$(PYTHON) -m scripts.seed

lint:
	cd backend && ../.venv/bin/python -m compileall -q app tests scripts

build:
	cd frontend && npm run build

up:
	docker compose up --build

down:
	docker compose down

migrate:
	cd backend && ../$(PYTHON) -m alembic upgrade head

migrate-down:
	cd backend && ../$(PYTHON) -m alembic downgrade -1

backup:
	cd backend && ../$(PYTHON) -m scripts.backup backup --output "$(abspath $(BACKUP_DIR))"

restore:
	@test -n "$(BACKUP)" || (echo "BACKUP=<yedek-dizini> gerekli"; exit 1)
	cd backend && ../$(PYTHON) -m scripts.backup restore --input "$(abspath $(BACKUP))" --force

prune-backups:
	cd backend && ../$(PYTHON) -m scripts.backup prune --directory "$(abspath $(BACKUP_DIR))" --keep $(BACKUP_KEEP) $(PRUNE_ARGS)

load-test:
	cd backend && ../$(PYTHON) -m scripts.load_test $(LOAD_TEST_ARGS)
