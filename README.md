# Chatbot Moderation POC

A Dockerized Telegram/WhatsApp group moderation bot that uses simple keyword detection (Phase 2) and AI (Phase 3) to moderate conversations. Built with Python, FastAPI, and Google Firestore.

## 🚀 Quick Start

### Prerequisites
*   [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
*   [ngrok](https://ngrok.com/download) installed and in your PATH.
*   PowerShell (Windows) or Make (Linux/Mac).

### Setup

1.  **Clone the repository**.
2.  **Telegram Configuration (Critical)**:
    *   Open [@BotFather](https://t.me/BotFather) on Telegram.
    *   Send `/mybots` -> Select Bot -> **Bot Settings** -> **Group Privacy**.
    *   Click **Turn OFF**. (Required for the bot to see user messages).
    *   **Promote to Admin**: The bot MUST be an Administrator with "Ban Users" permission.
    *   **Convert to Supergroup**: "Mute" functionality only works in Supergroups.
        *   *Tip*: Change "Chat History" to **Visible** in Group Settings to auto-upgrade to a Supergroup.

3.  **Environment Setup**:
    Copy the example environment file:
    ```powershell
    cp .env.example .env
    ```
    *Add your `TELEGRAM_BOT_TOKEN` and `public_url` to `.env`.*

3.  **Start Tunnel (Required for Webhooks)**:
    ```powershell
    .\manage.ps1 expose
    ```
    *Copy the HTTPS URL generated (e.g. `https://xyz.ngrok.app`) and update `PUBLIC_URL` in `.env` (or use a static domain).*

4.  **Start the Application**:
    ```powershell
    .\manage.ps1 up
    ```
    This will:
    *   Build the development Docker container (Uvicorn + FastAPI).
    *   Start the Firestore Emulator.
    *   **Auto-register** the Telegram Webhook and Menu Commands.

5.  **Verify**:
    Open Telegram and chat with your bot. It should respond to `/start` and filter toxic keywords.

## 🛠 Development Commands

We use `manage.ps1` (Windows) as a task runner.

| Command               | Description                                          |
| :-------------------- | :--------------------------------------------------- |
| `.\manage.ps1 up`     | Start the app (Hot Reload) and DB emulator.          |
| `.\manage.ps1 down`   | Stop and remove all containers.                      |
| `.\manage.ps1 expose` | Start ngrok tunnel to expose port 8080.              |
| `.\manage.ps1 test`   | Run the test suite inside the container.             |
| `.\manage.ps1 lint`   | Run code formatting (Ruff) and type checking (Mypy). |
| `.\manage.ps1 shell`  | Open a bash shell inside the running app container.  |

## 📂 Project Structure

*   `src/`: Application source code.
    *   `src/main.py`: Entry point (FastAPI server).
    *   `src/database.py`: Firestore connection logic.
    *   `src/telegram_bot/`: Telegram bot handlers.
*   `tests/`: Pytest test suite.
*   `docker/`: Docker configuration files.

## 🏗 Architecture

*   **Core**: Python 3.14 (FastAPI).
*   **Database**: Google Firestore (NoSQL).
*   **Hosting**: Designed for Google Cloud Run (Serverless).
*   **CI/CD**: GitHub Actions (Test, Lint, Publish to GHCR).

## ⚠️ Troubleshooting

*   **Firestore Error**: If you see `Failed to initialize a certificate credential`, ensure your `src/database.py` has the valid dummy key fix (already applied in this version).
*   **Linting Errors**: Run `.\manage.ps1 lint` to check for issues. Mypy is configured to check `src/` in package mode.
