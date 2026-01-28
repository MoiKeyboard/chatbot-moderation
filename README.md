# Chatbot Moderation POC

A Dockerized Telegram/WhatsApp group moderation bot that uses simple keyword detection and advanced AI to moderate conversations. Built with Python, FastAPI, and Google Firestore.

**AI Models**: Uses `govtech/lionguard-2-lite` hosted on Cloud Run for primary moderation, with `facebook/bart-large-mnli` (via Hugging Face API) as a zero-shot fallback.

## 🚀 Quick Start

### Prerequisites
*   [Docker Desktop](https://www.docker.com/products/docker-desktop/) or [Docker Engine](https://docs.docker.com/engine/install/) installed and running.
*   [ngrok](https://ngrok.com/download) installed and in your PATH.
*   PowerShell (Windows) or Make (Linux/Mac).
*   [HuggingFace Account](https://huggingface.co/join) for the inference provider.

#### Production requisites 
*   [Google Cloud Account](https://cloud.google.com/) for the production deployment.
*   Access to gated models: [gemma](https://huggingface.co/google/gemma-300m) 

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

4.  **Start Tunnel (Required for Webhooks)**:
    ```powershell
    .\manage.ps1 expose
    ```
    *Copy the HTTPS URL generated (e.g. `https://xyz.ngrok.app`) and update `PUBLIC_URL` in `.env` (or use a static domain).*

5.  **Start the Application**:
    ```powershell
    .\manage.ps1 up
    ```
    This will:
    *   Build the development Docker container (Uvicorn + FastAPI).
    *   Start the Firestore Emulator.
    *   **Auto-register** the Telegram Webhook and Menu Commands.

6.  **Verify**:
    Open Telegram and chat with your bot. It should respond to `/start` and filter toxic keywords.

## 🧠 AI Configuration

The bot supports two AI modes via the `AI_PROVIDER` environment variable:

1.  **`cloudrun` (Primary)**:
    *   Uses a self-hosted `govtech/lionguard-2-lite` container running on Cloud Run.
    *   Requires `AI_SERVICE_URL` to point to the deployed service.
    *   High accuracy, specific taxonomy (Hate, Insult, Sexual, etc.).

2.  **`remote` (Fallback)**:
    *   Uses the Hugging Face Inference API (`facebook/bart-large-mnli`).
    *   Requires `HUGGINGFACE_API_TOKEN`.
    *   Zero-shot classification (Toxic, Insult, Violence).

## 🛠 Development Commands

We use `manage.ps1` (Windows) as a task runner.

| Command                 | Description                                          |
| :---------------------- | :--------------------------------------------------- |
| `.\manage.ps1 up`       | Start the app (Hot Reload) and DB emulator.          |
| `.\manage.ps1 down`     | Stop and remove all containers.                      |
| `.\manage.ps1 expose`   | Start ngrok tunnel to expose port 8080.              |
| `.\manage.ps1 test`     | Run the test suite inside the container.             |
| `.\manage.ps1 lint`     | Run code formatting (Ruff) and type checking (Mypy). |
| `.\manage.ps1 shell`    | Open a bash shell inside the running app container.  |
| `.\manage.ps1 build-ai` | Build the heavy AI service container locally.        |
| `.\manage.ps1 push-ai`  | Tag and Push the AI service container to GCR.        |

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
