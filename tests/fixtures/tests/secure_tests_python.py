"""Fixture: Well-written Python tests — should NOT produce findings."""
import pytest


def test_addition():
    assert add(2, 3) == 5


def test_subtraction():
    result = subtract(5, 3)
    assert result == 2
    assert isinstance(result, int)


def test_raises_value_error():
    with pytest.raises(ValueError, match="cannot be zero"):
        divide(1, 0)


@pytest.mark.skip(reason="Flaky on CI due to network timeout")
def test_external_service():
    pass


def test_api_response():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_user_creation():
    user = create_user("test@example.com", "Test User")
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.name == "Test User"
