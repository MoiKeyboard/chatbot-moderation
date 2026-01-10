function Show-Usage {
    Write-Host "Usage: .\manage.ps1 [command]"
    Write-Host "Commands:"
    Write-Host "  up            Start local development (docker-compose up --build)"
    Write-Host "  down          Stop everything (docker-compose down)"
    Write-Host "  test          Run tests in container"
    Write-Host "  lint          Run linting (ruff, mypy)"
    Write-Host "  format        Format code (ruff format)"
    Write-Host "  shell         Open shell in app container"
    Write-Host "  build         Build production container"
}

if ($args.Count -eq 0) {
    Show-Usage
    exit 1
}

$Command = $args[0]

switch ($Command) {
    "up" {
        docker-compose -f docker/docker-compose.yml -p chatbot-moderation up --build
    }
    "down" {
        docker-compose -f docker/docker-compose.yml -p chatbot-moderation down
    }
    "test" {
        docker-compose -f docker/docker-compose.yml -p chatbot-moderation run --rm app pytest tests/
    }
    "lint" {
        docker-compose -f docker/docker-compose.yml -p chatbot-moderation run --rm app ruff check src/ tests/
        docker-compose -f docker/docker-compose.yml -p chatbot-moderation run --rm app mypy -p src
    }
    "format" {
        docker-compose -f docker/docker-compose.yml -p chatbot-moderation run --rm app ruff format src/ tests/
    }
    "shell" {
        docker-compose -f docker/docker-compose.yml -p chatbot-moderation run --rm app /bin/bash
    }
    "build" {
        docker build -t chatbot-moderation -f docker/Dockerfile.prod .
    }
    Default {
        Write-Error "Unknown command: $Command"
        Show-Usage
        exit 1
    }
}
