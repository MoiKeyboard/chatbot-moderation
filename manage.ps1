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
    Write-Host "  expose        Start ngrok tunnel on port 8080"
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
    "expose" {
        Write-Host "Starting ngrok on port 8080 with static domain..."
        if (Get-Command "ngrok" -ErrorAction SilentlyContinue) {
            ngrok http --domain=brandee-avirulent-nonretroactively.ngrok-free.dev 8080
        } else {
            Write-Error "ngrok not found in PATH."
        }
    }
    Default {
        Write-Error "Unknown command: $Command"
        Show-Usage
        exit 1
    }
}
