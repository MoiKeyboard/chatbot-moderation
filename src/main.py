import structlog
from flask import Flask, jsonify

from src.config import config
from src.database import db
from src.telegram_bot import create_application

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger()

app = Flask(__name__)

# Initialize Telegram App (Global)
bot_app = create_application()

@app.route("/health")
def health():
    """Health check endpoint for Cloud Run."""
    db_status = "connected" if db is not None else "failed"
    bot_status = "configured" if bot_app else "disabled"
    return jsonify({
        "status": "ok", 
        "version": "0.1.0", 
        "database": db_status,
        "telegram_bot": bot_status
    })

@app.route("/")
def index():
    """Root endpoint."""
    return jsonify({"service": "chatbot-moderation", "status": "running"})

@app.route("/telegram", methods=["POST"])
async def telegram_webhook():
    """Handle incoming Telegram updates via Webhook."""
    if not bot_app:
        return jsonify({"error": "Bot not configured"}), 503
    
    # Process update
    # In a real async flask app (Quart) this is easier. 
    # For now we just acknowledge. PTB usually handles this better.
    # This is a placeholder for the Webhook logic.
    return jsonify({"status": "received"})

if __name__ == "__main__":
    logger.info("Starting application...", port=config.PORT, debug=config.DEBUG)
    
    # In local dev (if not using docker-compose with hot reload which uses watchmedo)
    # The docker-compose command is: watchmedo ... python src/main.py
    
    # If you want to run Polling locally, you'd typically do it here if TELEGRAM_BOT_TOKEN is present.
    # But since we are behind Flask, handling polling + flask synchronously is hard.
    # For this POC, we will just run Flask. User can run bot via separate command or we rely on webhooks later.
    
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
