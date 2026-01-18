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
    
    # GCP
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
    FIRESTORE_DB_NAME: str = os.getenv("FIRESTORE_DB_NAME", "")
    FIRESTORE_EMULATOR_HOST: str = os.getenv("FIRESTORE_EMULATOR_HOST", "")
    
    # AI / Phases 3
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
