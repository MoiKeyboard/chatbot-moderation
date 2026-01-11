.PHONY: up down test lint build shell expose

DC = docker-compose -f docker/docker-compose.yml -p chatbot-moderation

up:
	$(DC) up --build

down:
	$(DC) down

test:
	$(DC) run --rm app pytest tests/

lint:
	$(DC) run --rm app ruff check src/ tests/
	$(DC) run --rm app mypy -p src

format:
	$(DC) run --rm app ruff format src/ tests/

shell:
	$(DC) run --rm app /bin/bash

build:
	docker build -t chatbot-moderation -f docker/Dockerfile.prod .

expose:
	ngrok http --domain=brandee-avirulent-nonretroactively.ngrok-free.dev 8080
