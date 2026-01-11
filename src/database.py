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
        # Check if already initialized
        if not firebase_admin._apps:
            # Check if using emulator
            if config.FIRESTORE_EMULATOR_HOST:
                 # When using emulator, we don't need real credentials, but SDK needs an object.
                 # Using AnonymousCredentials is the standard way.
                 # Create a dummy credential with a valid formatted key (needed for google-auth parsing)
                 dummy_key = (
                     "-----BEGIN PRIVATE KEY-----\n"
                     "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDWANUSI5QrNnyI\n"
                     "D4TsQZiAbnCEnepf7E3ethj753LpOrY9IVLrfvO5UNSPHcQU/AGOeUbRNxjl91XA\n"
                     "T0ZlLM4eO3suSffKKtSJSkyXY2FInzaYZrS8biPxnO9uwGZAmi/5lYGOyJousiMC\n"
                     "vTMDUJOU8GXOzjzH/YOaGb1uOy8WTG0JyFKn9aDP1m13pK2Pp0KR+b+GVhrpe2En\n"
                     "lCK7PNAgVpwavdf4R4a7UmDoosED+CcqUQq0GpiHPm50FGDUC1+EVGivk1QvpclX\n"
                     "+RA6saZNCZph/tNDVgUek7elY8zDlF6FrSjfR/k14eF/pHReFjmDG6w1Pf1/vebZ\n"
                     "qMMp2eWjAgMBAAECggEABEL/dSr+Q78WV3S9kVI6hbIkMgNUfPID+e1owvZVTTxA\n"
                     "6w9ZkUROEbSGvBPv4wWqZu+7ZOXsu4KFH9EUVjVrC/fkFVyX+U+s/qtnVLwtv+eC\n"
                     "c2tRhZJzpr8Y7IL2gcKzWme/MxyDoYbDcidmKzf9+Ypn8NAqRuUz3BPJk6SoOf5k\n"
                     "1f5MtZVPq8VRb7odD5kC2KxwQGqMk3NktReOu4G1RTJMlxK/mRfWhsTeBYF+nXJ1\n"
                     "V6H84VOc+oMg/sydRu2fpMR+g/J3C3WYLiYPS8bVMDbKY6eXXAEYm2AeJS9Ot64T\n"
                     "pSq8L7VpT3DlHdQVXUGAA5OXXO2mA7ni8M3qCguSaQKBgQDsLeQAmKaZKh2jylKt\n"
                     "EHRzDcScsDmDbjMVZmVUimJQWXCSbPMKFsfO0yYuOz1/UxWuEFEmK9aOj/rynajs\n"
                     "gVGNALHerYeGkL6Eft5F5n++Ku967fzpTHophJxGgdEiFd0aHP4+22Ptl69kuvVt\n"
                     "qejNqGDal72Qdbl0ilaIr/69WQKBgQDn9oJTrhROvsemYmiy7eDzt3pQAyFHC7my\n"
                     "L30twBVMog4qGfkTghDB+UNmGmCflEUGJ0S2BmHz6DHpqwQoH8/CKC7X6igsAxXy\n"
                     "4lUrh8Ctu1nqvcvxE7hqsu1Sdh/PxuCm5hkw8a0jXfzWlbe+v38olnVA0vziqlfg\n"
                     "PPx50mtvWwKBgEdY3aXod3uRo36VYkBx1hvjrt9+xQEVS01Nr5LIc0a+nik9zHXh\n"
                     "x96NHt2ce8l4+fWpbDpRx/EtQawFQMChmFc2PIV+epCGLWetQ8xuA20ZX1sNhfec\n"
                     "aNMeAm+yS9E2NaLr20p10Ew4JH4TlIzaZT+rfAbNDDEVvz6bg+Sq9hORAoGAZPG5\n"
                     "tYDEBaCwcY/R0EwE4Qqvh7JVAP3xScGw0AAPRNIhJ+E1q2+mq0M2OXCxK8DyaMMd\n"
                     "+7i7V9FsJyvtGyj82Jl0CTI1WTHek1w7hD4Hc5NchfMilT7nukczT/dn0JvTl836\n"
                     "mHoTxphYN2ngFHpxc9BGJneq5VkL9OGVXc5cQpECgYEAyi9mcNcVPvaMGq2cKYK8\n"
                     "rLaaOZ4Skf9G7+ng6SMvByP0k/IUxUIK0vsibgcA6YwsfJBoU8N2pngtROvjXdhE\n"
                     "7d5dNk9zkPST6k4+1qMtGVcFWLLu/NeIZwwGrzBId8lh+cRD3kHC7K35W8KzUzJj\n"
                     "SjmZvK88J3mviKDU38c7Ipg=\n"
                     "-----END PRIVATE KEY-----"
                 )
                 cred = credentials.Certificate({
                     "type": "service_account",
                     "project_id": config.GCP_PROJECT_ID or "test-project",
                     "private_key_id": "dummy",
                     "private_key": dummy_key,
                     "client_email": "dummy@dummy.com",
                     "client_id": "dummy",
                     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                     "token_uri": "https://oauth2.googleapis.com/token",
                     "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                     "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/dummy"
                 })
            else:
                cred = credentials.ApplicationDefault()
                
            firebase_admin.initialize_app(cred, {
                'projectId': config.GCP_PROJECT_ID or "test-project",
            })
        
        db = firestore.client()
        logger.info("Firestore initialized", project_id=config.GCP_PROJECT_ID)
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
    # In a real app, use a transaction here. simpler for POC.
    doc = doc_ref.get()
    if doc.exists:
        current_data = doc.to_dict()
        new_count = current_data.get('warning_count', 0) + 1
        doc_ref.update({'warning_count': new_count})
    else:
        # Create user if not exists (simplified)
        pass 

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
    total_query = messages_ref.count()
    total_snapshot = total_query.get() 
    total_messages = total_snapshot[0][0].value
    
    # Get toxic count
    toxic_query = messages_ref.where(filter=firestore.FieldFilter('is_toxic', '==', True)).count()
    toxic_snapshot = toxic_query.get()
    toxic_messages = toxic_snapshot[0][0].value
    
    return {
        "total_messages": total_messages,
        "toxic_messages": toxic_messages,
        "toxicity_rate": (toxic_messages / total_messages * 100) if total_messages > 0 else 0
    }
