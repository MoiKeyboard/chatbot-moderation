# Chatbot Moderation POC

A Dockerized Telegram/WhatsApp group moderation bot that uses simple keyword detection (Phase 1/2) and AI (Phase 3) to moderate conversations. Built with Python, Flask, and Google Firestore.

## 🚀 Quick Start

### Prerequisites
*   [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
*   PowerShell (Windows) or Make (Linux/Mac).

### Setup

1.  **Clone the repository** (if you haven't already).
2.  **Environment Setup**:
    Copy the example environment file:
    ```powershell
    cp .env.example .env
    ```
    *Note: For local development with the emulator, you don't need real API keys yet.*

3.  **Start the Application**:
    ```powershell
    .\manage.ps1 up
    ```
    This will:
    *   Build the development Docker container.
    *   Start the Python Flask application (Port 8080).
    *   Start the Firestore Emulator (Port 8081).
    *   Enable hot-reloading (edits to `src/` apply immediately).

4.  **Verify**:
    Visit `http://localhost:8080/health`. You should see `{"status": "ok", "database": "connected"}`.

## 🛠 Development Commands

We use `manage.ps1` (Windows) as a task runner.

| Command              | Description                                                 |
| :------------------- | :---------------------------------------------------------- |
| `.\manage.ps1 up`    | Start the app and database emulator in the background.      |
| `.\manage.ps1 down`  | Stop and remove all containers.                             |
| `.\manage.ps1 test`  | Run the test suite inside the container.                    |
| `.\manage.ps1 lint`  | Run code formatting (Ruff) and type checking (Mypy).        |
| `.\manage.ps1 shell` | Open a bash shell inside the running app container.         |
| `.\manage.ps1 build` | Build the production Docker image (verifies deployability). |

## 📂 Project Structure

*   `src/`: Application source code.
    *   `src/main.py`: Entry point (Flask server).
    *   `src/database.py`: Firestore connection logic.
    *   `src/telegram_bot/`: Telegram bot handlers.
*   `tests/`: Pytest test suite.
*   `docker/`: Docker configuration files.
    *   `Dockerfile.dev`: Dev environment (heavy, includes tools).
    *   `Dockerfile.prod`: Prod environment (light, secure).

## 🏗 Architecture

*   **Core**: Python 3.14 (Flask).
*   **Database**: Google Firestore (NoSQL).
*   **Hosting**: Designed for Google Cloud Run (Serverless).
*   **CI/CD**: GitHub Actions (Test, Lint, Publish to GHCR).

## ⚠️ Troubleshooting

*   **Firestore Error**: If you see `Failed to initialize a certificate credential`, ensure your `src/database.py` has the valid dummy key fix (already applied in this version).
*   **Linting Errors**: Run `.\manage.ps1 lint` to check for issues. Mypy is configured to check `src/` in package mode.
