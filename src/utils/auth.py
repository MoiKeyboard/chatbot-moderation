from typing import Optional
import structlog
import google.auth
from google.auth.transport.requests import Request as AuthRequest
from google.oauth2 import id_token
from src.config import config

logger = structlog.get_logger()

def get_oidc_token(audience: str) -> Optional[str]:
    """
    Get OIDC Token for secure service-to-service calls on Google Cloud.
    
    This function attempts to fetch an ID token for the target service (audience).
    It is designed to be robust for both Production (Cloud Run) and Local Development.
    
    Behavior:
    1. Feature Flag: Returns None if ENABLE_AI_AUTH is False.
    2. Localhost Bypass: If the target is localhost, returns None (no auth needed).
    3. Production: Uses Application Default Credentials (ADC) or Service Account to sign a token.
    4. Failure: Logs a warning and returns None (fails open for non-strict setups).
    
    Args:
        audience (str): The full URL of the service being called (e.g., https://my-service-run.app).
        
    Returns:
        Optional[str]: The ID token string, or None if not available/needed.
    """
    if not audience or not config.ENABLE_AI_AUTH:
        return None

    # 1. Localhost Bypass
    # If calling a local container, we assume it's inside our private network/docker-compose
    # and doesn't need an OIDC token (or can't validate one).
    if "localhost" in audience or "127.0.0.1" in audience or "host.docker.internal" in audience:
        return None

    # 2. Production / ADC
    try:
        # A. Try to generate an OIDC Identity Token (Standard for Service-to-Service)
        # This works on Cloud Run (Service Account) but fails locally with User Credentials.
        auth_req = AuthRequest()
        token = id_token.fetch_id_token(auth_req, audience)
        return token
    except Exception as e:
        # B. Fallback: Try to generate an OAuth2 Access Token (For Local Dev)
        # User Credentials (ADC) can't sign ID tokens, but they can provide Access Tokens.
        # Cloud Run accepts Access Tokens if the user has `run.invoker` role.
        logger.warning("Failed to get ID Token, trying Access Token fallback", error=str(e))
        try:
            creds, _ = google.auth.default()
            creds.refresh(auth_req)
            return creds.token
        except Exception as e2:
            # 3. Fail Open (Safety Net)
            # We assume that if we can't get a token, the user might be testing locally without auth,
            # or the target service is public. We warn but allow the request to proceed.
            # This prevents the bot from crushing if auth is misconfigured but the service is actually reachable.
            logger.warning("Auth Warning: Could not generate OIDC or Access token", target=audience, error=str(e2))
            return None

def verify_webhook_token(received_token: Optional[str], expected_token: str) -> bool:
    """
    Verify the Secret Token from an incoming Webhook request.
    
    Args:
        received_token (str): The token header received in the request.
        expected_token (str): The configured secret token.
        
    Returns:
        bool: True if valid, False otherwise.
    """
    if not input or not expected_token:
        return False
        
    # Constant-time comparison could be used here for strict security, 
    # but regular comparison is sufficient for this threat model (guessing a long string).
    if received_token != expected_token:
        logger.warning("Unauthorized webhook access attempt", token_received=received_token)
        return False
        
    return True
