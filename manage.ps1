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
    Write-Host "  build-ai    Build heavy AI service container (for Vertex AI)"
    Write-Host "  push-ai     Tag and Push AI service container to GCR"
    Write-Host "  expose        Start ngrok tunnel on port 8080"
    Write-Host "  auth          Login to Google Cloud (ADC) for local dev"
    Write-Host "  deps          Install dependencies (gcloud) via Winget"
}

if ($args.Count -eq 0) {
    Show-Usage
    exit 1
}

$Command = $args[0]

function Initialize-ADC-Path {
    # 1. Try to load GCP_SDK_CREDENTIALS_PATH from .env if not already set
    if (-not $env:GCP_SDK_CREDENTIALS_PATH -and (Test-Path .env)) {
        Get-Content .env | Where-Object { $_ -match "^GCP_SDK_CREDENTIALS_PATH=" } | ForEach-Object {
            $env:GCP_SDK_CREDENTIALS_PATH = $_.Split('=', 2)[1].Trim()
        }
    }

    # 2. If still not set, try dynamic detection (Default for Windows)
    if (-not $env:GCP_SDK_CREDENTIALS_PATH) {
        $PotentialPath = "$env:APPDATA\gcloud\application_default_credentials.json"
        if (Test-Path $PotentialPath) {
            $env:GCP_SDK_CREDENTIALS_PATH = $PotentialPath
        } else {
            # Fallback to User Profile (sometimes used in other configs)
            $env:GCP_SDK_CREDENTIALS_PATH = "$env:USERPROFILE\.config\gcloud\application_default_credentials.json"
        }
    }
    
    return (Test-Path $env:GCP_SDK_CREDENTIALS_PATH)
}

# Run detection globally
$ADC_Ready = Initialize-ADC-Path


switch ($Command) {
    "up" {
        if ($ADC_Ready) {
             Write-Host "Using ADC credentials from: $env:GCP_SDK_CREDENTIALS_PATH" -ForegroundColor Green
        } else {
             Write-Host "Warning: ADC credentials ($env:GCP_SDK_CREDENTIALS_PATH) not found. OIDC Auth will fail." -ForegroundColor Yellow
        }
        
        # Explicitly pass .env file for variable substitution in YAML
        docker-compose --env-file .env -f docker/docker-compose.yml -p chatbot-moderation up --build
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
        # Load env vars if needed, or assume user has them set.
        # PowerShell doesn't auto-load .env files easily into the session for this command.
        # We assume the user has set the variable OR we read it.
        # Simple hack: Read from .env if present
        if (Test-Path .env) {
            Get-Content .env | Where-Object { $_ -match "^HUGGINGFACE_API_TOKEN=" } | ForEach-Object {
                 $env:HUGGINGFACE_API_TOKEN = $_.Split('=', 2)[1]
            }
        }
        docker build -t chatbot-moderation -f docker/Dockerfile --target prod --build-arg HF_TOKEN=$env:HUGGINGFACE_API_TOKEN .
    }
    "expose" {
        Write-Host "Starting ngrok on port 8080 with static domain..."
        if (Get-Command "ngrok" -ErrorAction SilentlyContinue) {
            ngrok http --domain=brandee-avirulent-nonretroactively.ngrok-free.dev 8080
        } else {
            Write-Error "ngrok not found in PATH."
        }
    }
    "build-ai" {
        Write-Host "Building LionGuard AI Service (this will take a while)..." -ForegroundColor Cyan
        docker build -f docker/Dockerfile.ai -t lionguard-v2 .
    }
    "push-ai" {
        # Try to get Project ID from .env
        $ProjectID = $env:GCP_PROJECT_ID
        if (-not $ProjectID -and (Test-Path .env)) {
            $ProjectID = (Get-Content .env | Where-Object { $_ -match "^GCP_PROJECT_ID=" } | ForEach-Object { $_.Split('=', 2)[1].Trim() })
        }

        if (-not $ProjectID) {
            Write-Error "GCP_PROJECT_ID not set in .env or environment."
            exit 1
        }

        # User is in Europe (europe-west4), so we must use eu.gcr.io
        $ImageTag = "eu.gcr.io/$ProjectID/lionguard-service:v1"
        Write-Host "Tagging image as $ImageTag..." -ForegroundColor Cyan
        docker tag lionguard-v2 $ImageTag
        
        Write-Host "Pushing to GCR..." -ForegroundColor Cyan
        docker push $ImageTag
    }
    "auth" {
        $AuthList = gcloud auth list --format="value(account)" 2>&1
        if ($AuthList) {
            Write-Host "Already logged in as:" -ForegroundColor Green
            Write-Host $AuthList
        } else {
             Write-Host "Logging into Google Cloud..." -ForegroundColor Cyan
             gcloud auth login --update-adc
        }
        Write-Host "Listing Projects:" -ForegroundColor Cyan
        gcloud projects list

        # Auto-select project if not set
        $CurrentProject = gcloud config get-value project 2>&1
        if (-not $CurrentProject -or $CurrentProject -match "unset") {
             Write-Host "Project not set. Selecting first available project..." -ForegroundColor Yellow
             $FirstProject = gcloud projects list --format="value(projectId)" | Select-Object -First 1
             if ($FirstProject) {
                 Write-Host "Setting project to: $FirstProject" -ForegroundColor Green
                 gcloud config set project $FirstProject
                 gcloud auth application-default set-quota-project $FirstProject
             } else {
                 Write-Error "No projects found! Please create a GCP project first."
             }
        }
    }
    "deps" {
        Write-Host "Installing Google Cloud SDK via Winget..." -ForegroundColor Cyan
        winget install Google.CloudSDK --accept-source-agreements --accept-package-agreements
        Write-Host "Installation complete. You may need to restart your terminal." -ForegroundColor Green
    }
    Default {
        Write-Error "Unknown command: $Command"
        Show-Usage
        exit 1
    }
}
