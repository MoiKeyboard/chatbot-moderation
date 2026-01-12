from typing import Optional, List, Tuple
from datetime import datetime, timedelta, timezone
import structlog
import httpx
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential
from telegram import Bot, ChatPermissions
from telegram.error import BadRequest

from src.config import config
from src.models import MessageLog, User
from src.database import log_message, increment_warning, get_user, create_or_update_user

logger = structlog.get_logger()

# Basic "dumb" list for Fallback
TOXIC_KEYWORDS = {"badword", "stupid", "idiot", "hate", "scam"} 

# AI Model Configuration
# Primary: Custom Singlish Model
# Fallback: Zero-Shot Standard Model
# MODEL_PRIMARY = "govtech/lionguard-2" # TODO: Enable when we have a dedicated endpoint
MODEL_FALLBACK = "facebook/bart-large-mnli"

# Use Fallback for POC stability (LionGuard-2 returns 404 on free tier)
ACTIVE_MODEL = MODEL_FALLBACK
API_URL = f"https://router.huggingface.co/hf-inference/models/{ACTIVE_MODEL}"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def call_huggingface_api(text: str) -> dict:
    """Call Hugging Face Inference API with retry logic."""
    if not config.HUGGINGFACE_API_TOKEN:
        return {"error": "No token"}

    headers = {"Authorization": f"Bearer {config.HUGGINGFACE_API_TOKEN}"}
    
    # Payload for Zero-Shot Classification (BART)
    # We must define the candidates
    payload = {
        "inputs": text,
        "parameters": {"candidate_labels": ["toxic", "safe", "insult", "threat"]}
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(API_URL, headers=headers, json=payload, timeout=5.0)
        
        # If the specific model is loading, it sends 503. Retry handled by tenacity.
        if response.status_code == 503:
            raise Exception("Model loading")
            
        if response.status_code != 200:
            logger.error("HF Inference Error", status=response.status_code, body=response.text)
            return {"error": "API failed"}
            
        return response.json()

async def analyze_toxicity(text: str) -> Tuple[bool, float, List[str]]:
    """
    Hybrid check: AI > Keyword Fallback.
    Returns: (is_toxic, score, found_keywords)
    """
    
    # 1. AI Check (Phase 3)
    if config.HUGGINGFACE_API_TOKEN:
        try:
            result = await call_huggingface_api(text)
            logger.info("AI Raw Result", model=MODEL_FALLBACK, result=result) # DEBUG Log
            
            if "error" not in result:
                # Debug log confirmed format is List[Dict] or Dict with 'labels'
                # Log: [{"label": "insult", "score": 0.81}, ...]
                
                # Case A: List of Dicts (seen in logs)
                if isinstance(result, list):
                    # Sort by score desc just in case
                    # result = [{'label': 'insult', 'score': 0.8}, ...]
                    top_item = max(result, key=lambda x: x.get("score", 0))
                    top_label = top_item.get("label")
                    top_score = top_item.get("score")
                    
                    if top_label in ["toxic", "insult", "threat"] and top_score > 0.6:
                         return True, top_score, [top_label]

                # Case B: Standard Zero-Shot Dict (safety fallback)
                elif isinstance(result, dict) and "labels" in result:
                    top_label = result["labels"][0]
                    top_score = result["scores"][0]
                    
                    if top_label in ["toxic", "insult", "threat"] and top_score > 0.6:
                         return True, top_score, [top_label]

        except Exception as e:
            logger.error("AI Analysis Failed", error=str(e))
            # Fall through to keyword check
    
    # 2. Keyword Fallback (Phase 2)
    text_lower = text.lower()
    found = [word for word in TOXIC_KEYWORDS if word in text_lower]
    
    if found:
        return True, 1.0, found
        
    return False, 0.0, []

async def restrict_user(bot: Bot, chat_id: int, user_id: int, duration_minutes: int):
    """Mute a user for a specific duration. Handles Supergroup vs Basic Group differences."""
    try:
        # Debug Override: 0 means Kick (Disabled)
        # if duration_minutes == 0:
        #     await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        #     logger.info("User BANNED (Kick)", user_id=user_id, chat_id=chat_id)
        #     return

        until_date = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        # 1. Try Supergroup Permissions (Granular)
        try:
            permissions = ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
            await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=permissions, until_date=until_date)
            logger.info("User muted (Supergroup)", user_id=user_id, chat_id=chat_id)
            return
        except BadRequest as e:
            if "supergroup" not in str(e).lower():
                raise e # Re-raise if it's not the supergroup error
            logger.warning("Supergroup restriction failed, trying Basic Group fallback", error=str(e))

        # 2. Fallback: Basic Group Permissions (Simple)
        permissions_basic = ChatPermissions(can_send_messages=False)
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=permissions_basic, until_date=until_date)
        logger.info("User muted (Basic Group)", user_id=user_id, chat_id=chat_id)

    except Exception as e:
        logger.error("Failed to mute user", error=str(e))

async def process_message(
    bot: Bot, # Added dependency
    user_id: int, 
    chat_id: int, 
    message_id: int, 
    text: str, 
    username: Optional[str] = None, 
    first_name: str = "Unknown"
) -> Optional[str]:
    """
    Process an incoming message.
    Returns a reply string if the message should be replied to.
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
    # Fire and forget logging (Non-Blocking Optimization)
    asyncio.create_task(log_message(msg_log))
    
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
        
        actions = []
        
        # Action: Mute on 3rd Warning
        if current_warnings == 3:
            await restrict_user(bot, chat_id, user_id, 10)
            actions.append("MUTED (10m)")
            
        # Action: Kick on 5th Warning (Placeholder)
        # if current_warnings >= 5:
        #     await bot.ban_chat_member(chat_id, user_id)
        #     actions.append("BANNED")
        
        action_text = f"Actions: {', '.join(actions)}" if actions else ""
        
        # Return warning message
        return f"⚠️ Warning: Your message contains inappropriate content. (Violation #{current_warnings}) {action_text}"
        
    return None
