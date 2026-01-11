
import pytest
from fastapi.testclient import TestClient
from src.main import app

@pytest.fixture
def client():
    # FastAPI TestClient is synchronous wrapper around async app
    with TestClient(app) as client:
        yield client

def test_health_check(client):
    """Test the /health endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert "telegram_bot" in data

def test_root_endpoint(client):
    """Test the root endpoint."""
    response = client.get('/')
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "chatbot-moderation"
