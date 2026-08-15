.PHONY: up down dev worker beat test lint migrate shell reset logs

up:            ## levanta postgres + redis
	docker compose up -d
	@echo "esperando a postgres..."
	@until docker compose exec -T postgres pg_isready -U licit -d licitaciones >/dev/null 2>&1; do sleep 1; done
	@echo "listo"

down:
	docker compose down

logs:
	docker compose logs -f

dev:
	uv run python manage.py runserver

worker:
	uv run celery -A config worker -l info

beat:
	uv run celery -A config beat -l info

test:
	uv run pytest

lint:
	uv run ruff check --fix .
	uv run ruff format .

migrate:
	uv run python manage.py makemigrations
	@echo "--- REVISA LA MIGRACIÓN ANTES DE CONTINUAR ---"
	@read -p "aplicar? [y/N] " ok && [ "$$ok" = "y" ]
	uv run python manage.py migrate

shell:
	uv run python manage.py shell_plus

reset:          ## borra la base y reconstruye desde cero
	docker compose down -v
	$(MAKE) up
	uv run python manage.py migrate
	uv run python manage.py createsuperuser
