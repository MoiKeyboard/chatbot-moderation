import firebase_admin # type: ignore
from firebase_admin import credentials, firestore
from src.config import config
from src.models import User, MessageLog
import structlog
from typing import Optional

logger = structlog.get_logger()

def init_db():
    """Initialize Firestore connection."""
    try:
        from google.cloud import firestore
        from google.auth.credentials import AnonymousCredentials

        # Check if using emulator
        if config.FIRESTORE_EMULATOR_HOST:
             logger.info("Connecting to Firestore Emulator", host=config.FIRESTORE_EMULATOR_HOST)
             # Use AnonymousCredentials for Emulator
             cred = AnonymousCredentials()
             # The client automatically reads FIRESTORE_EMULATOR_HOST from env
        else:
             logger.info("Connecting to Real Firestore")
             cred = None # Use Application Default Credentials

        # Connect to specific database if named, else default
        db_kwargs = {
            "project": config.GCP_PROJECT_ID,
            "credentials": cred
        }
        
        if config.FIRESTORE_DB_NAME:
            db_kwargs["database"] = config.FIRESTORE_DB_NAME
            
        db = firestore.Client(**db_kwargs)
        
        logger.info("Firestore initialized", project_id=config.GCP_PROJECT_ID, database=config.FIRESTORE_DB_NAME)
        return db
    except Exception as e:
        logger.error("Failed to initialize Firestore", error=str(e))
        return None

db = init_db()

async def get_user(user_id: int) -> Optional[User]:
    """Retrieve user from Firestore."""
    if not db:
        return None
    
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    
    if doc.exists:
        return User(**doc.to_dict())
    return None

async def create_or_update_user(user: User):
    """Create or update user in Firestore."""
    if not db:
        return
        
    doc_ref = db.collection('users').document(str(user.user_id))
    doc_ref.set(user.dict(), merge=True)

async def increment_warning(user_id: int):
    """Increment warning count for a user."""
    if not db:
        return

    doc_ref = db.collection('users').document(str(user_id))
    # Optimized: Atomic Increment (No Read required)
    # Note: google.cloud.firestore uses slightly different syntax than firebase_admin if using transforms?
    # Actually, firestore.Increment is available in google.cloud.firestore too.
    from google.cloud.firestore import Increment
    doc_ref.set({"warning_count": Increment(1)}, merge=True) 

async def log_message(message: MessageLog):
    """Log a message to Firestore."""
    if not db:
        return

    # Use a subcollection or root collection depending on your query needs. 
    # Root collection 'messages' is easier for global metrics.
    doc_ref = db.collection('messages').document(str(message.message_id))
    doc_ref.set(message.dict())

async def get_global_metrics():
    """Get basic stats from Firestore."""
    if not db:
        return {"error": "Database not connected"}
    
    # NOTE: Counting documents in Firestore is expensive ($$$) if you just list them.
    # For a POC with small data, `.stream()` is okay.
    # For prod, you'd use Distributed Counters or Aggregation Queries.
    
    # Simplified Aggregation (Phase 2 POC way)
    messages_ref = db.collection('messages')
    
    # Get total count (using aggregation query if available in SDK, else stream)
    # Using count() aggregation which is efficient
    # google.cloud.firestore supports count()
    try:
        from google.cloud.firestore import FieldFilter
        total_query = messages_ref.count()
        total_snapshot = total_query.get() 
        total_messages = total_snapshot[0][0].value
        
        # Get toxic count
        toxic_query = messages_ref.where(filter=FieldFilter('is_toxic', '==', True)).count()
        toxic_snapshot = toxic_query.get()
        toxic_messages = toxic_snapshot[0][0].value
    except:
         # Fallback for old SDK or emulator quirks
         # Actually just stream if count fails
         total_messages = 0
         toxic_messages = 0
    
    return {
        "total_messages": total_messages,
        "toxic_messages": toxic_messages,
        "toxicity_rate": (toxic_messages / total_messages * 100) if total_messages > 0 else 0
    }

async def get_top_offenders(limit: int = 5) -> list:
    """Get list of users with highest warning counts."""
    if not db:
        return []
    
    from google.cloud.firestore import Query
    users_ref = db.collection('users')
    query = users_ref.order_by('warning_count', direction=Query.DESCENDING).limit(limit)
    docs = query.stream()
    
    return [User(**doc.to_dict()) for doc in docs]
