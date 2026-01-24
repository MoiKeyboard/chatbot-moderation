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

# Fallback / Remote Model
MODEL_REMOTE = "facebook/bart-large-mnli"

# Vertex AI Configuration
# The endpoint should be a deployed LionGuard-2 model in Vertex AI Model Garden
ACTIVE_MODEL = "Google Vertex AI (LionGuard-2)" if config.AI_PROVIDER == "vertex" else f"{MODEL_REMOTE} (Remote)"

async def call_cloud_run(text: str) -> List[dict]:
    """
    Call Cloud Run (or any HTTP Model Service).
    """
    if not config.AI_SERVICE_URL:
        logger.warning("Skipping Cloud Run: No AI_SERVICE_URL set")
        return []

    try:
        logger.info("Calling Cloud Run", url=config.AI_SERVICE_URL)
        
        # Standard format for our container: {"instances": [{"text": "message"}]}
        payload = {"instances": [{"text": text}]}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(config.AI_SERVICE_URL, json=payload, timeout=10.0)
            
            if response.status_code != 200:
                logger.error("Cloud Run Failed", status=response.status_code, body=response.text)
                return []
                
            prediction = response.json()
            
        # Parse Response
        # Expected: {"predictions": [[{"label": "toxic", "score": 0.9}]]}
        logger.info("Cloud Run Response", predictions=prediction.get("predictions"))
        
        results = []
        preds = prediction.get("predictions", [])
        if preds:
            # Flatten/Normalize
            raw_result = preds[0]
            if isinstance(raw_result, list):
                    for item in raw_result:
                        results.append({"label": item.get("label"), "score": item.get("score")})
            
        return results

    except Exception as e:
        logger.error("Cloud Run Call Failed", error=str(e))
        return []

class LionGuardClassifier:
    """
    Custom wrapper for LionGuard-2-Lite.
    Architecture: Text -> Embedding(Gemma) -> Vectors -> Classifier(LionGuard) -> Scores
    """
    def __init__(self):
        logger.info("Loading Local AI Chain...")
        
        # 0. Authenticate (for Gated Models)
        if config.HUGGINGFACE_API_TOKEN:
            import huggingface_hub
            try:
                huggingface_hub.login(token=config.HUGGINGFACE_API_TOKEN)
                logger.info("Authenticated with Hugging Face")
            except Exception as e:
                logger.warning("Failed to authenticate with HF", error=str(e))

        # 1. Load Embedding Model (SBERT)
        logger.info("Loading Embedder", model=MODEL_EMBEDDING)
        from sentence_transformers import SentenceTransformer
        self.embedder = SentenceTransformer(MODEL_EMBEDDING, device="cpu")
        
        # 2. Load Classifier (Transformers)
        logger.info("Loading Classifier", model=MODEL_CLASSIFIER)
        from transformers import AutoModel
        import torch
        
        self.classifier = AutoModel.from_pretrained(
            MODEL_CLASSIFIER, 
            trust_remote_code=True
        ).to("cpu")
        self.classifier.eval()
        
        # Labels mapping (from model config or known LionGuard labels)
        # LionGuard-2-Lite usually outputs specific indices. 
        # We assume standard LionGuard labels for now:
        self.labels = ["unsafe", "safe"] # Basic binary or specific categories?
        # NOTE: LionGuard-2-Lite typically outputs multi-class logits.
        # We will inspect the output dynamically.
        
        logger.info("LionGuard Chain Loaded")

    def predict(self, text: str) -> List[dict]:
        """
        Returns list of dicts: [{"label": "hate", "score": 0.9}, ...]
        """
        import torch
        import numpy as np
        
        # 1. Embed
        # LionGuard expects embeddings. SBERT returns numpy array.
        embeddings = self.embedder.encode([text]) # Shape: (1, 768)
        
        # 2. Classify
        with torch.no_grad():
            inputs = torch.tensor(embeddings)
            outputs = self.classifier(inputs)
            # Logits shape: (1, NumLabels)
            if hasattr(outputs, "logits"):
                logits = outputs.logits
            elif isinstance(outputs, (list, tuple)):
                logits = outputs[0]
            else:
                logits = outputs
                
            probs = torch.softmax(logits, dim=1).numpy()[0] # [0.1, 0.9, ...]
            
        # 3. Map to Labels
        # If model config has id2label, use it.
        id2label = self.classifier.config.id2label
        
        # Fix: Handle generic labels (LABEL_0, LABEL_1) or missing labels
        # We assume binary classification for LionGuard: 0=Safe, 1=Unsafe (Toxic)
        if not id2label or str(id2label.get(0, "")).upper() == "LABEL_0":
             # lionguard-2-lite binary assumption
             id2label = {0: "safe", 1: "toxic"}
        
        logger.info("Model Labels", id2label=id2label, raw_probs=probs.tolist())

        results = []
        
        for idx, score in enumerate(probs):
            label = id2label.get(idx, f"label_{idx}")
            results.append({"label": label, "score": float(score)})
            
        return results

def get_classifier():
    """Load the local model on first use."""
    global _LIONGUARD
    if _LIONGUARD is None:
        try:
            _LIONGUARD = LionGuardClassifier()
        except Exception as e:
            logger.error("Failed to load Local AI", error=str(e))
            raise e
    return _LIONGUARD

API_URL = f"https://router.huggingface.co/hf-inference/models/{MODEL_REMOTE}"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def call_huggingface_api(text: str) -> dict:
    """Call Hugging Face Inference API with retry logic."""
    if not config.HUGGINGFACE_API_TOKEN:
        logger.warning("Skipping AI check: No HUGGINGFACE_API_TOKEN set")
        return {"error": "No token"}

    headers = {"Authorization": f"Bearer {config.HUGGINGFACE_API_TOKEN}"}
    
    # Payload for Zero-Shot Classification (BART)
    # We must define the candidates
    # 'threat' causes false positives on dates (e.g. "Feb 7th"). Switched to 'violence'.
    payload = {
        "inputs": text,
        "parameters": {"candidate_labels": ["toxic", "insult", "violence", "hate speech", "neutral", "safe"]}
    }
    
    logger.info("Calling HF API (Remote)", model=MODEL_REMOTE)

    async with httpx.AsyncClient() as client:
        response = await client.post(API_URL, headers=headers, json=payload, timeout=5.0)
        
        # If the specific model is loading, it sends 503. Retry handled by tenacity.
        if response.status_code == 503:
            logger.info("HF Model loading (503), retrying...")
            raise Exception("Model loading")
            
        if response.status_code != 200:
            logger.error("HF Inference Error", status=response.status_code, body=response.text)
            return {"error": "API failed"}
            
        data = response.json()
        logger.info("HF Response Received", data=data) 
        return data

async def analyze_toxicity(text: str) -> Tuple[bool, float, List[str]]:
    """
    Hybrid check: AI (Local/Remote) > Keyword Fallback.
    Returns: (is_toxic, score, found_keywords)
    """
    
    # 1. AI Check (Phase 3)
    # Feature Toggle: Choose Provider
    
    try:
        labels_and_scores = []
        
# Cloud Run / HTTP Configuration
ACTIVE_MODEL = "LionGuard-2 (Cloud Run)" if config.AI_PROVIDER == "cloudrun" else f"{MODEL_REMOTE} (Remote)"

# ... (omitted code) ...

        if config.AI_PROVIDER == "cloudrun" or config.AI_PROVIDER == "vertex": # Keep vertex for backward compat if needed
             # --- CLOUD RUN (Production) ---
             raw_results = await call_cloud_run(text)
             for item in raw_results:
                 labels_and_scores.append((item["label"], item["score"]))

        elif config.AI_PROVIDER == "local":
             # --- LOCAL INFERENCE (Legacy/Disabled) ---
             logger.warning("Local AI provider is deprecated/disabled in this version.")
             # Fallback to zero
             
        else:
             # --- REMOTE INFERENCE (HuggingFace API Backup) ---
             if config.HUGGINGFACE_API_TOKEN:
                 result = await call_huggingface_api(text)
                 
                 # Normalize API response to [(label, score), ...]
                 # Handle List format (e.g. [{"label": "toxic", "score": 0.9}, ...])
                 if isinstance(result, list):
                    work_list = result[0] if (result and isinstance(result[0], list)) else result
                    for item in work_list:
                        if isinstance(item, dict) and "label" in item and "score" in item:
                            labels_and_scores.append((item["label"], item["score"]))
                            
                 # Handle Dict format
                 elif isinstance(result, dict) and "labels" in result and "scores" in result:
                    labels_and_scores = zip(result["labels"], result["scores"])

        # 2. Score Calculation (Unified Logic)
        if labels_and_scores:
            # LionGuard Labels: "hate", "harassment", "violence", "sexual", "self-harm", "toxic", "insult"
            # BART Labels: "toxic", "insult", "violence", "hate speech"
            bad_labels = {"toxic", "insult", "violence", "hate speech", "hate", "harassment", "sexual", "self-harm"}
            
            current_score = 0.0
            found_tags = []
            
            for label, score in labels_and_scores:
                if label in bad_labels:
                    # NOISE FILTER: Only count scores > 0.05
                    if score > 0.05:
                        current_score += score
                        found_tags.append(f"{label} ({score:.2f})")
            
            provider_tag = config.AI_PROVIDER.capitalize()
            logger.info(f"AI Analysis ({provider_tag})", total_score=current_score, breakdown=found_tags, original_text=text[:50])

            # Threshold: 0.7 (Conservative)
            # LionGuard is sharper, but 0.7 works well for cumulative scores.
            if current_score >= 0.7:
                 return True, current_score, found_tags

    except Exception as e:
        logger.error("AI Analysis Failed", error=str(e))
        # Fall through to keyword check
    
    # 2. Keyword Fallback (Phase 2)
    text_lower = text.lower()
    found = [word for word in TOXIC_KEYWORDS if word in text_lower]
    
    if found:
        return True, 1.0, found
        
    return False, 0.0, []
    
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
