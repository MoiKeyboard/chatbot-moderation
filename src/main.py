import logging
import structlog
from flask import Flask, jsonify
from src.config import config

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

@app.route("/health")
def health():
    """Health check endpoint for Cloud Run."""
    return jsonify({"status": "ok", "version": "0.1.0"})

@app.route("/")
def index():
    """Root endpoint."""
    return jsonify({"service": "chatbot-moderation", "status": "running"})

if __name__ == "__main__":
    logger.info("Starting application locally", port=config.PORT, debug=config.DEBUG)
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
