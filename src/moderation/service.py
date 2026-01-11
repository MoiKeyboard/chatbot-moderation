from typing import Optional, List, Tuple
from datetime import datetime
import structlog

from src.models import MessageLog, User
from src.database import log_message, increment_warning, get_user, create_or_update_user

logger = structlog.get_logger()

# Basic "dumb" list for Phase 2
TOXIC_KEYWORDS = {"badword", "stupid", "idiot", "hate", "scam"} 

async def analyze_toxicity(text: str) -> Tuple[bool, float, List[str]]:
    """
    Basic keyword-based toxicity check.
    Returns: (is_toxic, score, found_keywords)
    """
    text_lower = text.lower()
    found = [word for word in TOXIC_KEYWORDS if word in text_lower]
    
    if found:
        return True, 1.0, found
    return False, 0.0, []

async def process_message(
    user_id: int, 
    chat_id: int, 
    message_id: int, 
    text: str, 
    username: Optional[str] = None, 
    first_name: str = "Unknown"
) -> Optional[str]:
    """
    Process an incoming message.
    Returns a reply string if the message should be replied to (e.g. warning), 
    or None if no action needed.
    """
    
    # 1. Analyze
    is_toxic, score, reasons = await analyze_toxicity(text)
    
    # 2. Log Message
    msg_log = MessageLog(
        message_id=message_id,
        chat_id=chat_id,
        user_id=user_id,
        text=text,
        is_toxic=is_toxic,
        toxicity_score=score,
        timestamp=datetime.now()
    )
    # Fire and forget logging to avoid slowing down response too much, 
    # but for simple async logic await is fine.
    await log_message(msg_log)
    
    # 3. Handle Toxicity
    if is_toxic:
        logger.info("Toxic message detected", user_id=user_id, reasons=reasons)
        
        # Ensure user exists
        user = await get_user(user_id)
        if not user:
            user = User(user_id=user_id, username=username, first_name=first_name)
            await create_or_update_user(user)
        
        # Increment warning
        await increment_warning(user_id)
        
        # Get latest count (approximate for now)
        current_warnings = user.warning_count + 1
        
        # Return warning message
        return f"⚠️ Warning: Your message contains inappropriate content. (Violation #{current_warnings})"
        
    return None
