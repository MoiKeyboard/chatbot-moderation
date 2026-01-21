from typing import Optional
from telegram import Update, ChatMember, ChatMemberUpdated
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, ChatMemberHandler, filters
from src.config import config
from src.moderation.service import process_message
from src.admin.handlers import handle_metrics_command, handle_warnings_command, check_admin
from src.moderation.service import ACTIVE_MODEL, restrict_user
from src.database import add_chat, remove_chat
from src.models import Chat
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

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Tracks addition/removal of the bot from groups.
    SECURITY: Only allow ADMIN_TELEGRAM_ID to add the bot.
    """
    result = extract_status_change(update.my_chat_member)
    if result is None:
        return

    was_member, is_member = result
    
    # CASE 1: Bot Added to Group
    if not was_member and is_member:
        user = update.my_chat_member.from_user
        chat = update.effective_chat
        
        logger.info("Bot added to chat", chat_id=chat.id, title=chat.title, by_user_id=user.id)
        
        # SECURITY CHECK
        # If the user adding us is NOT the Admin, leave immediately.
        if str(user.id) != config.ADMIN_TELEGRAM_ID:
            logger.warning("Unauthorized addition blocked", chat_id=chat.id, by_user_id=user.id)
            await context.bot.send_message(chat.id, "⛔ Authorization Failed. Adding this bot is restricted to the Administrator.")
            await context.bot.leave_chat(chat.id)
            return
            
        await context.bot.send_message(chat.id, "🛡 Moderation Bot Active. Hello Admin!")
        
        # PERSISTENCE: Save new chat to DB
        new_chat = Chat(
            chat_id=chat.id,
            title=chat.title or "Unknown",
            type=chat.type,
            added_by=user.id
        )
        await add_chat(new_chat)
        
    # CASE 2: Bot Removed from Group
    elif was_member and not is_member:
        chat = update.effective_chat
        logger.info("Bot removed from chat", chat_id=chat.id, title=chat.title)
        
        # PERSISTENCE: Mark chat as inactive
        await remove_chat(chat.id)

def extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[tuple[bool, bool]]:
    """Helper to detect if bot was added or removed."""
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = old_status in [
        ChatMember.MEMBER,
        ChatMember.ADMINISTRATOR,
    ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    
    is_member = new_status in [
        ChatMember.MEMBER,
        ChatMember.ADMINISTRATOR,
    ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)

    return was_member, is_member

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    if not update.message or not update.message.text:
        return
        
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    # SECURITY: Ignore DMs from non-admins to prevent unauthorized AI usage costs
    if chat.type == "private" and str(user.id) != config.ADMIN_TELEGRAM_ID:
        logger.warning("Ignored private message from non-admin", user_id=user.id)
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
    
    # Handle Chat Membership (Security)
    application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))

    return application
