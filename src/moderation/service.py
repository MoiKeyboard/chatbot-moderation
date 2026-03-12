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
from src.utils.auth import get_oidc_token

logger = structlog.get_logger()

# Basic "dumb" list for Fallback
TOXIC_KEYWORDS = {"badword", "stupid", "idiot", "hate", "scam"} 

# Fallback / Remote Model
MODEL_REMOTE = "facebook/bart-large-mnli"

# External AI Endpoint Configuration
# The endpoint should be a deployed LionGuard-2 model in any Vertex AI Model Garden or Cloud Run
ACTIVE_MODEL = "LionGuard-2 (Cloud Run)" if config.AI_PROVIDER in ["cloudrun", "vertex"] else f"{MODEL_REMOTE} (Remote)"

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
        
        # Security: Get OIDC Token (if needed)
        token = get_oidc_token(config.AI_SERVICE_URL)
        headers = {}
        if token:
             headers["Authorization"] = f"Bearer {token}"
             logger.info("Attached OIDC Token for Security")
        else:
             logger.debug("No OIDC Token attached (Public or Localhost)")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(config.AI_SERVICE_URL, json=payload, headers=headers, timeout=60.0)
            
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
            elif isinstance(raw_result, dict):
                 # Handle flat format (old version or single prediction)
                 results.append({"label": raw_result.get("label"), "score": raw_result.get("score")})
            
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
        try:
            # 1. Format (Crucial Step: Add Prompt)
            # Source: https://huggingface.co/govtech/lionguard-2-lite/blob/main/inference.py
            formatted_text = f"task: classification | query: {text}"
            
            # 2. Embed
            embeddings = self.embedder.encode([formatted_text]) 
            
            # 3. Classify
            # The custom model has a .predict() method that takes embeddings
            # and returns a dictionary of scores per category.
            # We use that if available, otherwise fall back to raw call.
            
            if hasattr(self.classifier, "predict"):
                 # Expected Output: {"category1": [score], "category2": [score]}
                 results_dict = self.classifier.predict(embeddings)
                 
                 parsed_results = []
                 # results_dict is likely {"sexual": [0.1], "hate": [0.9]...}
                 for category, scores in results_dict.items():
                     score = float(scores[0]) # Get score for the single input
                     parsed_results.append({"label": category, "score": score})
                     
                 return parsed_results
            
            # Fallback for standard AutoModel usage (if .predict isn't dynamically loaded)
            import torch
            with torch.no_grad():
                inputs = torch.tensor(embeddings)
                outputs = self.classifier(inputs)
                
                if hasattr(outputs, "logits"):
                    logits = outputs.logits
                else:
                    logits = outputs
                    
                probs = torch.softmax(logits, dim=1).numpy()[0]
                
            # Map Logic (Fallback)
            id2label = self.classifier.config.id2label
            if not id2label or str(id2label.get(0, "")).upper() == "LABEL_0":
                 id2label = {0: "safe", 1: "toxic"}
            
            return [{"label": id2label.get(i, f"label_{i}"), "score": float(p)} for i, p in enumerate(probs)]

        except Exception as e:
            logger.error("LionGuard Prediction Failed", error=str(e))
            return []

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
        "parameters": {"candidate_labels": [
            "toxic", "insult", "violence", "hate speech", 
            "sexual", "discriminatory", 
            "harassment", "self-harm",
            "neutral", "safe"
        ]}
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
    logger.info("Analyzing toxicity...", text_snippet=text[:50] if text else "")
    
    # 1. AI Check (Phase 3)
    # Feature Toggle: Choose Provider
    
    try:
        labels_and_scores = []
        



        if config.AI_PROVIDER == "cloudrun" or config.AI_PROVIDER == "vertex": # Keep vertex for backward compat if needed
             # --- CLOUD RUN (Production) ---
             raw_results = await call_cloud_run(text)
             for item in raw_results:
                 labels_and_scores.append((item["label"], item["score"]))

        elif config.AI_PROVIDER == "local":
             # --- LOCAL INFERENCE (Legacy/Disabled) ---
             logger.warning("Local AI provider is deprecated/disabled in this version.")
             # Fallback to zero
             
        elif config.AI_PROVIDER == "remote":
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
            # --- SCORING POLICY ---
            # Define how to score based on the active provider
            
            # Policy 1: LionGuard (Cloud Run)
            # Uses a specific 'binary' flag for the overall score.
            if config.AI_PROVIDER in ["cloudrun", "vertex"]:
                primary_label = "binary"
                threshold = 0.95 # High confidence required
                
                # Tags: Descriptive labels only
                tag_labels = {
                    "binary", 
                    "hateful_l1", "hateful_l2", "insults", "sexual_l1", "sexual_l2", 
                    "physical_violence", "self_harm_l1", "self_harm_l2",
                    "all_other_misconduct_l1", "all_other_misconduct_l2"
                }

            # Policy 2: Hugging Face API (BART / Fallback)
            # Uses MAX score of any bad label (since BART treats them independently)
            else:
                primary_label = "max_score" # Placeholder name
                threshold = 0.5 # Lower threshold for Zero-Shot
                
                # Tags: All bad labels
                tag_labels = {
                    "toxic", "insult", "violence", "hate speech", "sexual", 
                    "discriminatory", "harassment", "self-harm"
                }

            current_score = 0.0
            found_tags = []
            
            # --- CALCULATE SCORE ---
            if config.AI_PROVIDER in ["cloudrun", "vertex"]:
                 # LionGuard: Trust specific label
                 for label, score in labels_and_scores:
                    if label == primary_label:
                        current_score = score
            else:
                 # Remote: Trust MAX of any bad label
                 current_score = max([score for label, score in labels_and_scores if label in tag_labels], default=0.0)

            # --- POPULATE TAGS ---
            for label, score in labels_and_scores:
                # Add Tags (For Explanation)
                if label in tag_labels:
                    # NOISE FILTER: Only log specific categories if > 0.3
                    if score > 0.3:
                         found_tags.append(f"{label} ({score:.2f})")
            
            # Fallback for LionGuard mismatches (SafeGuard)
            if current_score == 0.0 and found_tags:
                # If we have strong tags but missed the primary label, take the max tag score
                 max_tag_score = max([float(t.split('(')[1].strip(')')) for t in found_tags], default=0.0)
                 if max_tag_score > threshold:
                     current_score = max_tag_score
                     found_tags.append(f"inferred_from_tags ({current_score:.2f})")

            # If no detailed tags found but it is toxic, add a generic tag
            if current_score > threshold and not found_tags:
                 found_tags.append(f"toxic_confidence ({current_score:.2f})")
            
            provider_tag = config.AI_PROVIDER.capitalize()
            logger.info(f"AI Analysis ({provider_tag})", total_score=current_score, breakdown=found_tags, original_text=text)

            # Final Decision
            if current_score >= threshold:
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
    logger.info("Processing message", user_id=user_id, text=text)
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
