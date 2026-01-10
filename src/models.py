from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class User(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: str
    is_admin: bool = False
    warning_count: int = 0
    created_at: datetime = datetime.now()

class MessageLog(BaseModel):
    message_id: int
    chat_id: int
    user_id: int
    text: str
    is_toxic: bool = False
    toxicity_score: float = 0.0
    timestamp: datetime = datetime.now()
