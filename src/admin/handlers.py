from src.database import get_global_metrics
from src.config import config

async def handle_metrics_command(user_id: int) -> str:
    """
    Handle /metrics command. 
    Only allow if user_id matches ADMIN_TELEGRAM_ID.
    """
    # Check Admin
    # Note: ADMIN_TELEGRAM_ID might be a string in config, ensure type safety
    if not config.ADMIN_TELEGRAM_ID:
        return "⚠️ Admin ID not configured."

    try:
        admin_id = int(config.ADMIN_TELEGRAM_ID)
    except ValueError:
        return "⚠️ Invalid Admin ID configuration."
    
    if user_id != admin_id:
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
    """
    Handle /warnings command.
    """
    # TODO: Implement listing top offenders or specific user lookup
    return "🚧 Warning listing not implemented yet."
