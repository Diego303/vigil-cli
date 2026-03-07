"""Fixture: Python tests with various quality issues."""
import pytest
from unittest.mock import MagicMock


# TEST-001: Test without assertions
def test_login():
    response = client.post("/login")
    # No assertions at all


# TEST-001: Another test without assertions
def test_user_creation():
    user = create_user("alice")
    print(user)


# TEST-002: Trivial assertion — assert x is not None
def test_user_exists():
    user = get_user(1)
    assert user is not None


# TEST-002: Trivial assertion — assertTrue(True)
def test_always_passes():
    result = compute_something()
    assert True


# TEST-003: Catches all exceptions
def test_complex():
    try:
        result = complex_operation()
    except Exception:
        pass


# TEST-003: Bare except catch-all
def test_another_complex():
    try:
        result = another_operation()
    except:
        pass


# TEST-004: Skip without reason
@pytest.mark.skip
def test_broken_feature():
    assert 1 + 1 == 2


# TEST-004: Skip with empty parens
@pytest.mark.skip()
def test_another_broken():
    assert True


# TEST-005: API test without status code check
def test_api_endpoint():
    response = client.get("/api/users")
    data = response.json()
    assert len(data) > 0


# TEST-006: Mock mirrors implementation
def test_calculate_price():
    mock_calc = MagicMock()
    mock_calc.return_value = 42
    result = mock_calc()
    assert result == 42


# LEGITIMATE: Test with proper assertions — should NOT trigger
def test_addition():
    result = add(2, 3)
    assert result == 5
    assert isinstance(result, int)


# LEGITIMATE: Test with pytest.raises — should NOT trigger TEST-001
def test_raises_value_error():
    with pytest.raises(ValueError):
        divide(1, 0)


# LEGITIMATE: Skip with reason — should NOT trigger TEST-004
@pytest.mark.skip(reason="Requires external service")
def test_external_api():
    pass


# LEGITIMATE: API test with status code — should NOT trigger TEST-005
def test_api_with_status():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
