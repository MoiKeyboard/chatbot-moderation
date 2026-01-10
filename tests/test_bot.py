
import pytest
from unittest.mock import MagicMock, AsyncMock
from src.telegram_bot.bot import start

@pytest.mark.asyncio
async def test_start_command():
    """Test the /start command handler."""
    update = MagicMock()
    context = MagicMock()
    
    # Mock user
    user = MagicMock()
    user.id = 12345
    user.username = "testuser"
    user.mention_html.return_value = "<a href='tg://user?id=12345'>testuser</a>"
    update.effective_user = user
    
    # Mock message reply
    update.message.reply_html = AsyncMock()
    
    await start(update, context)
    
    # Assert reply was called
    update.message.reply_html.assert_called_once()
    args, _ = update.message.reply_html.call_args
    assert "Hi <a href='tg://user?id=12345'>testuser</a>" in args[0]
