import structlog
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from telegram import Update, BotCommand

from src.config import config
from src.database import db
from src.telegram_bot.bot import create_application

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

# Global Bot Instance
bot_app = create_application()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan events for the FastAPI application.
    Handles Bot startup, webhook registration, and shutdown.
    """
    logger.info("Starting application lifespan...")
    # Debug: Log Configuration (Masked)
    logger.info("Configuration Loaded", 
        port=config.PORT, 
        debug=config.DEBUG, 
        log_level=config.LOG_LEVEL,
        ai_provider=config.AI_PROVIDER,
        ai_service_url=config.AI_SERVICE_URL,
        public_url=config.PUBLIC_URL,
        has_bot_token=bool(config.TELEGRAM_BOT_TOKEN),
    )

    if config.TELEGRAM_BOT_TOKEN and bot_app:
        # 1. Initialize Bot
        await bot_app.initialize()
        await bot_app.start()
        logger.info("Telegram Bot started")

        # 2. Configure Webhook (if PUBLIC_URL set)
        if config.PUBLIC_URL:
            webhook_url = f"{config.PUBLIC_URL}/telegram"
            logger.info("Configuring Telegram Webhook", url=webhook_url)
            await bot_app.bot.set_webhook(
                url=webhook_url, 
                secret_token=config.SECRET_TOKEN
            )
            
            # Configure Menu
            commands = [
                BotCommand("start", "Start the bot"),
                BotCommand("help", "Get help"),
                BotCommand("metrics", "View stats (Admin)"),
                BotCommand("warnings", "View offenders (Admin)"),
                BotCommand("restrict", "Mute user (min) (Admin)"),
            ]
            await bot_app.bot.set_my_commands(commands)
            logger.info("Bot commands menu configured")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    if bot_app:
        await bot_app.stop()
        await bot_app.shutdown()
    logger.info("Shutdown complete")

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    """Health check endpoint."""
    db_status = "connected" if db is not None else "failed"
    bot_status = "configured" if bot_app else "disabled"
    return {
        "status": "ok", 
        "version": "0.4.0-fastapi", 
        "database": db_status,
        "telegram_bot": bot_status
    }

@app.get("/")
async def index():
    """Root endpoint."""
    return {"service": "chatbot-moderation", "status": "running"}

@app.post("/telegram")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates via Webhook."""
    # SECURITY: Verify Secret Token
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != config.SECRET_TOKEN:
        logger.warning("Unauthorized webhook access attempt", token_received=secret_token)
        return JSONResponse(
            content={"error": "Unauthorized"}, 
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    if not bot_app:
        return JSONResponse(
            content={"error": "Bot not configured"}, 
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    data = await request.json()
    
    # Process update
    # In FastAPI/Uvicorn, we are on the main event loop, so this is safe.
    # No need for new contexts per request.
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    
    return {"status": "ok"}
    
if __name__ == "__main__":
    import uvicorn
    # Local dev entry point (python src/main.py)
    # Note: docker-compose uses its own command, this is just for manual run
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
