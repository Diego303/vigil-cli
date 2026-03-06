"""Tests para deteccion de typosquatting por similitud."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vigil.analyzers.deps.similarity import (
    _normalize_package_name,
    find_similar_popular,
    levenshtein_distance,
    load_popular_packages,
    normalized_similarity,
)


class TestLevenshteinDistance:
    """Tests para calculo de distancia de Levenshtein."""

    def test_identical_strings(self) -> None:
        assert levenshtein_distance("hello", "hello") == 0

    def test_empty_strings(self) -> None:
        assert levenshtein_distance("", "") == 0

    def test_one_empty(self) -> None:
        assert levenshtein_distance("hello", "") == 5
        assert levenshtein_distance("", "hello") == 5

    def test_single_insertion(self) -> None:
        assert levenshtein_distance("cat", "cats") == 1

    def test_single_deletion(self) -> None:
        assert levenshtein_distance("cats", "cat") == 1

    def test_single_substitution(self) -> None:
        assert levenshtein_distance("cat", "bat") == 1

    def test_typical_typo(self) -> None:
        # "reqeusts" vs "requests" (transposition = 2 operations)
        assert levenshtein_distance("reqeusts", "requests") == 2

    def test_completely_different(self) -> None:
        assert levenshtein_distance("abc", "xyz") == 3

    def test_case_sensitive(self) -> None:
        assert levenshtein_distance("Hello", "hello") == 1


class TestNormalizedSimilarity:
    """Tests para similaridad normalizada."""

    def test_identical(self) -> None:
        assert normalized_similarity("flask", "flask") == 1.0

    def test_identical_case_insensitive(self) -> None:
        assert normalized_similarity("Flask", "flask") == 1.0

    def test_completely_different(self) -> None:
        sim = normalized_similarity("abcdefgh", "xyz")
        assert sim < 0.3

    def test_similar_typo(self) -> None:
        # "reqeusts" vs "requests" — should be high similarity
        sim = normalized_similarity("reqeusts", "requests")
        assert sim > 0.7

    def test_empty_strings(self) -> None:
        assert normalized_similarity("", "") == 1.0

    def test_symmetry(self) -> None:
        sim1 = normalized_similarity("flask", "flaask")
        sim2 = normalized_similarity("flaask", "flask")
        assert sim1 == sim2


class TestNormalizePackageName:
    """Tests para normalizacion de nombres de paquetes."""

    def test_pypi_hyphen_underscore(self) -> None:
        assert _normalize_package_name("my-package", "pypi") == "my_package"
        assert _normalize_package_name("my_package", "pypi") == "my_package"

    def test_pypi_dot(self) -> None:
        assert _normalize_package_name("my.package", "pypi") == "my_package"

    def test_pypi_case(self) -> None:
        assert _normalize_package_name("Flask", "pypi") == "flask"

    def test_npm_lowercase(self) -> None:
        assert _normalize_package_name("Express", "npm") == "express"

    def test_npm_preserves_hyphens(self) -> None:
        # npm doesn't normalize hyphens/underscores
        assert _normalize_package_name("my-package", "npm") == "my-package"


class TestLoadPopularPackages:
    """Tests para carga de corpus de paquetes populares."""

    def test_loads_builtin_pypi_fallback(self) -> None:
        """Si no hay data file, usa el corpus built-in."""
        packages = load_popular_packages("pypi")
        assert len(packages) > 50
        assert "requests" in packages
        assert "flask" in packages
        assert "django" in packages

    def test_loads_builtin_npm_fallback(self) -> None:
        packages = load_popular_packages("npm")
        assert len(packages) > 30
        assert "express" in packages
        assert "lodash" in packages
        assert "react" in packages

    def test_loads_from_file(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        corpus = {"custom-pkg": 1000, "another-pkg": 500}
        (data_dir / "popular_pypi.json").write_text(json.dumps(corpus))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            packages = load_popular_packages("pypi")

        assert packages == corpus

    def test_unknown_ecosystem_returns_empty(self) -> None:
        packages = load_popular_packages("cargo")
        assert packages == {}

    def test_corrupt_file_falls_back(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text("not json {{{")

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            packages = load_popular_packages("pypi")

        # Should fall back to builtin
        assert len(packages) > 50


class TestFindSimilarPopular:
    """Tests para deteccion de typosquatting."""

    def test_exact_match_not_reported(self) -> None:
        """Un paquete que es exactamente popular no es typosquatting."""
        popular = {"requests": 300_000_000}
        matches = find_similar_popular("requests", "pypi", popular_packages=popular)
        assert matches == []

    def test_typo_detected(self) -> None:
        """Un typo de un paquete popular se detecta."""
        popular = {"requests": 300_000_000}
        matches = find_similar_popular(
            "reqeusts", "pypi", threshold=0.7, popular_packages=popular
        )
        assert len(matches) == 1
        assert matches[0][0] == "requests"
        assert matches[0][1] > 0.7

    def test_threshold_filters(self) -> None:
        """Paquetes debajo del threshold no se reportan."""
        popular = {"requests": 300_000_000}
        matches = find_similar_popular(
            "xyz", "pypi", threshold=0.85, popular_packages=popular
        )
        assert matches == []

    def test_multiple_matches_sorted(self) -> None:
        """Multiples matches se ordenan por similaridad descendente."""
        popular = {"requests": 300_000_000, "request": 1_000_000}
        matches = find_similar_popular(
            "reqeust", "pypi", threshold=0.7, popular_packages=popular
        )
        if len(matches) > 1:
            assert matches[0][1] >= matches[1][1]

    def test_pypi_normalization(self) -> None:
        """PyPI normaliza - y _ como equivalentes."""
        popular = {"python-dateutil": 170_000_000}
        # "python_dateutil" normalizes to same as "python-dateutil" — not typosquatting
        matches = find_similar_popular(
            "python_dateutil", "pypi", threshold=0.85, popular_packages=popular
        )
        assert matches == []

    def test_empty_corpus(self) -> None:
        matches = find_similar_popular("flask", "pypi", popular_packages={})
        assert matches == []

    def test_with_builtin_corpus(self) -> None:
        """Test usando el corpus built-in real."""
        matches = find_similar_popular("reqeusts", "pypi", threshold=0.75)
        match_names = [m[0] for m in matches]
        assert "requests" in match_names

    def test_case_insensitive(self) -> None:
        popular = {"Flask": 30_000_000}
        matches = find_similar_popular(
            "flaask", "pypi", threshold=0.7, popular_packages=popular
        )
        assert len(matches) == 1
        assert matches[0][0] == "Flask"

    def test_short_names_high_threshold(self) -> None:
        """Nombres cortos con un caracter diferente pueden tener alta similaridad."""
        popular = {"pg": 1_600_000}
        # "py" vs "pg" — 50% similarity, should not match at 0.85 threshold
        matches = find_similar_popular(
            "py", "npm", threshold=0.85, popular_packages=popular
        )
        assert matches == []
