from src.database import get_global_metrics, get_top_offenders
from src.config import config

def check_admin(user_id: int) -> bool:
    """Check if user is admin."""
    if not config.ADMIN_TELEGRAM_ID:
        return False
    try:
        return user_id == int(config.ADMIN_TELEGRAM_ID)
    except ValueError:
        return False

async def handle_metrics_command(user_id: int) -> str:
    """Handle /metrics command."""
    if not check_admin(user_id):
        return "⛔ Access Denied: You are not an administrator."

    metrics = await get_global_metrics()
    if "error" in metrics:
        return f"⚠️ Error fetching metrics: {metrics['error']}"
        
    return (
        f"📊 **Bot Metrics**\n\n"
        f"**Total Messages:** {metrics['total_messages']}\n"
        f"**Toxic Messages:** {metrics['toxic_messages']}\n"
        f"**Toxicity Rate:** {metrics['toxicity_rate']:.1f}%"
    )

async def handle_warnings_command(user_id: int) -> str:
    """Handle /warnings command."""
    if not check_admin(user_id):
        return "⛔ Access Denied."

    offenders = await get_top_offenders()
    if not offenders:
        return "✅ No active warnings found."
        
    lines = ["🚨 **Top Offenders**\n"]
    for i, user in enumerate(offenders, 1):
        name = user.username or user.first_name or f"User {user.user_id}"
        lines.append(f"{i}. {name} (ID: `{user.user_id}`): {user.warning_count} warnings")
        
    return "\n".join(lines)
