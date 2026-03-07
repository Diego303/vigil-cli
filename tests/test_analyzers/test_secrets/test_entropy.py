"""Tests para el modulo de entropy."""

import pytest

from vigil.analyzers.secrets.entropy import (
    is_high_entropy_secret,
    is_low_entropy_secret,
    shannon_entropy,
)


class TestShannonEntropy:
    """Tests para calculo de entropy de Shannon."""

    def test_empty_string(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_single_char(self) -> None:
        assert shannon_entropy("a") == 0.0

    def test_repeated_char(self) -> None:
        assert shannon_entropy("aaaaaaa") == 0.0

    def test_two_chars_equal(self) -> None:
        # "ab" -> entropy = 1.0 (log2(2) = 1)
        assert abs(shannon_entropy("ab") - 1.0) < 0.01

    def test_low_entropy_password(self) -> None:
        # Simple passwords have low entropy
        entropy = shannon_entropy("password123")
        assert entropy < 3.5

    def test_high_entropy_random(self) -> None:
        # Random-looking strings have high entropy
        entropy = shannon_entropy("a3f8b2c1d9e0x7y4z6w")
        assert entropy > 3.5

    def test_placeholder_low_entropy(self) -> None:
        assert shannon_entropy("changeme") < 3.5
        assert shannon_entropy("supersecret") < 3.5
        assert shannon_entropy("TODO") < 2.5

    def test_api_key_high_entropy(self) -> None:
        # Realistic API key
        entropy = shannon_entropy("sk_live_a3f8b2c1d9e0x7y4z6wq")
        assert entropy > 3.5

    def test_all_unique_chars(self) -> None:
        # All unique chars = maximum entropy for that length
        text = "abcdefghij"
        entropy = shannon_entropy(text)
        # log2(10) ≈ 3.32
        assert abs(entropy - 3.32) < 0.01


class TestIsHighEntropySecret:
    """Tests para is_high_entropy_secret."""

    def test_short_string_rejected(self) -> None:
        # Too short regardless of entropy
        assert is_high_entropy_secret("abc") is False

    def test_random_string_accepted(self) -> None:
        assert is_high_entropy_secret("a3f8b2c1d9e0x7y4z") is True

    def test_simple_password_rejected(self) -> None:
        assert is_high_entropy_secret("password", min_entropy=4.0) is False

    def test_custom_threshold(self) -> None:
        # With a very low threshold, even simple strings pass
        assert is_high_entropy_secret("abcdefgh", min_entropy=1.0) is True


class TestIsLowEntropySecret:
    """Tests para is_low_entropy_secret."""

    def test_placeholder_is_low_entropy(self) -> None:
        assert is_low_entropy_secret("changeme") is True

    def test_random_is_not_low_entropy(self) -> None:
        assert is_low_entropy_secret("a3f8b2c1d9e0x7y4z") is False

    def test_short_string_rejected(self) -> None:
        assert is_low_entropy_secret("ab") is False

    def test_custom_threshold(self) -> None:
        assert is_low_entropy_secret("test1234", max_entropy=4.0) is True
