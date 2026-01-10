.PHONY: up down test lint build shell

up:
	docker-compose up --build

down:
	docker-compose down

test:
	docker-compose run --rm app pytest tests/

lint:
	docker-compose run --rm app ruff check src/ tests/
	docker-compose run --rm app mypy src/

format:
	docker-compose run --rm app ruff format src/ tests/

shell:
	docker-compose run --rm app /bin/bash

build:
	docker build -t chatbot-moderation -f docker/Dockerfile.prod .
