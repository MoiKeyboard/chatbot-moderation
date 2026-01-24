import os
from dataclasses import dataclass

@dataclass
class Config:
    """Configuration management via environment variables."""
    # App Settings
    PORT: int = int(os.getenv("PORT", 8080))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "") # e.g. https://xyz.ngrok.app
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ADMIN_TELEGRAM_ID: str = os.getenv("ADMIN_TELEGRAM_ID", "")
    
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
    FIRESTORE_DB_NAME: str = os.getenv("FIRESTORE_DB_NAME", "")
    FIRESTORE_EMULATOR_HOST: str = os.getenv("FIRESTORE_EMULATOR_HOST", "")
    
    # AI Configuration (Feature Toggle)
    # AI Configuration (Feature Toggle)
    # Options: "cloudrun" (LionGuard on Cloud Run), "remote" (Hugging Face API Backup), "local" (Disabled)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "cloudrun") 
    
    # Cloud Run / Remote Service Configuration
    AI_SERVICE_URL: str = os.getenv("AI_SERVICE_URL", "") # Full URL to /predict
    
    # Legacy / Optional
    VERTEX_PROJECT_ID: str = os.getenv("VERTEX_PROJECT_ID", GCP_PROJECT_ID)
    VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "europe-west4")
    VERTEX_ENDPOINT_ID: str = os.getenv("VERTEX_ENDPOINT_ID", "")
    
    # Backup: Hugging Face API (for "remote" provider)
    HUGGINGFACE_API_TOKEN: str = os.getenv("HUGGINGFACE_API_TOKEN", "")

    # Secret Token (Derived)
    @property
    def SECRET_TOKEN(self) -> str:
        """Derive a consistent secret token from the bot token."""
        import hashlib
        if not self.TELEGRAM_BOT_TOKEN:
            return "dev-token"
        return hashlib.sha256(self.TELEGRAM_BOT_TOKEN.encode()).hexdigest()

config = Config()
