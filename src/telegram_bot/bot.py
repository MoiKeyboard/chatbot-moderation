from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from src.config import config
from src.moderation.service import process_message
from src.admin.handlers import handle_metrics_command
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

async def metrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /metrics command."""
    if not update.effective_user or not update.message:
        return
    response = await handle_metrics_command(update.effective_user.id)
    await update.message.reply_text(response, parse_mode='Markdown')

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    if not update.message or not update.message.text:
        return
        
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    reply = await process_message(
        user_id=user.id,
        chat_id=chat.id,
        message_id=update.message.message_id,
        text=update.message.text,
        username=user.username,
        first_name=user.first_name
    )
    
    if reply:
        await update.message.reply_text(reply)

def create_application() -> Optional[Application]:
    """Create and configure the Telegram Application."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("No TELEGRAM_BOT_TOKEN found. Bot will not start.")
        return None

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("metrics", metrics_command))
    
    # Handle text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    return application
