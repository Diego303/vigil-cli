"""Clean tests — should produce zero findings."""
import pytest


def test_login_returns_token():
    response = client.post("/login", json={"username": "test", "password": "pass"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert isinstance(data["access_token"], str)


def test_delete_requires_auth():
    response = client.delete("/users/1")
    assert response.status_code == 401


def test_user_creation():
    user = create_user("test", "test@example.com")
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.username == "test"


@pytest.mark.skip(reason="Payment gateway not configured in CI")
def test_payment_integration():
    result = process_payment(100)
    assert result.status == "success"
