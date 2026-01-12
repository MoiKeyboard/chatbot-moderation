
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.moderation.service import analyze_toxicity, process_message
from src.models import User

@pytest.mark.asyncio
async def test_analyze_toxicity_keyword():
    """Test fallback keyword detection."""
    # Ensure Token is None so we hit the keyword fallback path!
    with patch("src.config.config.HUGGINGFACE_API_TOKEN", None):
        is_toxic, score, reasons = await analyze_toxicity("you are stupid")
        assert is_toxic is True
        assert score == 1.0
        assert "stupid" in reasons

@pytest.mark.asyncio
async def test_analyze_toxicity_ai_safe():
    """Test AI detection (mocked) for safe message."""
    with patch("src.moderation.service.call_huggingface_api", new_callable=AsyncMock) as mock_api:
        # Mocking Zero-Shot response for "hello"
        mock_api.return_value = {
            "labels": ["safe", "toxic"],
            "scores": [0.99, 0.01]
        }
        # We need to set token to enable AI path
        with patch("src.config.config.HUGGINGFACE_API_TOKEN", "fake_token"):
            is_toxic, score, reasons = await analyze_toxicity("hello friend")
            
            assert is_toxic is False
            mock_api.assert_called_once()

@pytest.mark.asyncio
async def test_process_message_logic():
    """Test the full flow: analyze -> log -> warn -> mute."""
    bot = MagicMock()
    bot.restrict_chat_member = AsyncMock()
    
    # Mock Logs/User DB
    with patch("src.moderation.service.log_message", new_callable=AsyncMock), \
         patch("src.moderation.service.get_user", new_callable=AsyncMock) as mock_get_user, \
         patch("src.moderation.service.create_or_update_user", new_callable=AsyncMock), \
         patch("src.moderation.service.increment_warning", new_callable=AsyncMock):

        # Scenario: User has 2 warnings already (this is the 3rd strike)
        mock_user = User(user_id=123, username="badguy", first_name="TestBad", warning_count=2)
        mock_get_user.return_value = mock_user
        
        # Act: Send a toxic message
        reply = await process_message(
            bot=bot,
            user_id=123,
            chat_id=999,
            message_id=1,
            text="you are stupid", # Triggers keyword check
            username="badguy"
        )
        
        # Assertions
        assert "Warning" in reply
        assert "MUTED" in reply
        
        # Verify Mute was called
        bot.restrict_chat_member.assert_called_once()
        # Check if called with correct args
        call_kwargs = bot.restrict_chat_member.call_args.kwargs
        assert call_kwargs['user_id'] == 123
        assert call_kwargs['chat_id'] == 999


