from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from src.config import config
from src.moderation.service import process_message
from src.admin.handlers import handle_metrics_command, handle_warnings_command, check_admin
from src.moderation.service import ACTIVE_MODEL, restrict_user
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
        
    help_text = (
        "🛡 **Group Moderation Bot**\n\n"
        "I protect this group from toxic content using AI.\n"
        f"🧠 **AI Model:** `{ACTIVE_MODEL}`\n"
        "🚨 **Rules:**\n"
        "- No insults or toxicity\n"
        "- 3 Strikes = 10m Mute\n"
        "\nCommands:\n"
        "/metrics - View stats (Admin)\n"
        "/warnings - Top offenders (Admin)\n"
        "/restrict <id> [min] - Mute user (Admin)"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def metrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /metrics command."""
    logger.info("Metrics command received", chat_type=update.effective_chat.type if update.effective_chat else "unknown")
    if not update.effective_user or not update.message:
        return
    response = await handle_metrics_command(update.effective_user.id)
    await update.message.reply_text(response, parse_mode='Markdown')

async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /warnings command."""
    if not update.effective_user or not update.message:
        return
    response = await handle_warnings_command(update.effective_user.id)
    await update.message.reply_text(response, parse_mode='Markdown')

async def restrict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /restrict <user_id> [minutes] OR Reply with /restrict [minutes]."""
    if not update.effective_user or not update.message or not update.effective_chat:
        return
        
    # Check Admin
    if not check_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    # Parse Args
    args = context.args
    target_id = None
    duration = 10 # Default
    
    # CASE A: Reply to a message
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
        # args[0] might be duration
        if args and args[0].isdigit():
            duration = int(args[0])
            
    # CASE B: Explicit ID
    elif args and args[0].isdigit():
        target_id = int(args[0])
        if len(args) > 1 and args[1].isdigit():
            duration = int(args[1])
            
    if not target_id:
        await update.message.reply_text("Usage: Reply to a user with /restrict [min] OR type /restrict <id> [min]")
        return
        
    try:
        await restrict_user(context.bot, update.effective_chat.id, target_id, duration)
        await update.message.reply_text(f"🔇 User {target_id} restricted for {duration} minutes.")
        
    except ValueError:
        await update.message.reply_text("⚠️ Invalid duration.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    if not update.message or not update.message.text:
        return
        
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    reply = await process_message(
        bot=context.bot,
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
    application.add_handler(CommandHandler("warnings", warnings_command))
    application.add_handler(CommandHandler("restrict", restrict_command))
    
    # Handle text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    return application
