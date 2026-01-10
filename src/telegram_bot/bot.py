from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from src.config import config
import structlog

logger = structlog.get_logger()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    if not user or not update.message:
        return
        
    logger.info("User started bot", user_id=user.id, username=user.username)
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! I am your group moderation bot.",
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    if not update.message:
        return
    await update.message.reply_text("Help!")

def create_application() -> Optional[Application]:
    """Create and configure the Telegram Application."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("No TELEGRAM_BOT_TOKEN found. Bot will not start.")
        return None

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    return application
