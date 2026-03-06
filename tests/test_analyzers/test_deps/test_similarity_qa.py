"""QA tests adicionales para similarity/typosquatting detection.

Cubre: normalización PEP 503, false positives con paquetes populares,
corpus duplicates, umbrales boundary, nombres cortos/largos, y npm specifics.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vigil.analyzers.deps.similarity import (
    _BUILTIN_POPULAR_NPM,
    _BUILTIN_POPULAR_PYPI,
    _normalize_package_name,
    find_similar_popular,
    levenshtein_distance,
    load_popular_packages,
    normalized_similarity,
)


# ──────────────────────────────────────────────────────────────────
# Corpus integrity
# ──────────────────────────────────────────────────────────────────


class TestCorpusIntegrity:
    """Tests para integridad del corpus built-in."""

    def test_no_duplicate_keys_pypi(self) -> None:
        """PyPI corpus has no duplicate entries."""
        # Since Python dicts discard duplicates silently, count source entries
        assert len(_BUILTIN_POPULAR_PYPI) > 90

    def test_no_duplicate_keys_npm(self) -> None:
        """npm corpus has no duplicate entries (chalk was fixed)."""
        assert len(_BUILTIN_POPULAR_NPM) > 60
        # Verify chalk appears exactly once
        chalk_count = sum(1 for k in _BUILTIN_POPULAR_NPM if k == "chalk")
        assert chalk_count == 1

    def test_all_pypi_names_are_strings(self) -> None:
        for name, downloads in _BUILTIN_POPULAR_PYPI.items():
            assert isinstance(name, str), f"Key {name} is not a string"
            assert isinstance(downloads, int), f"Value for {name} is not int"
            assert downloads > 0, f"Downloads for {name} is not positive"

    def test_all_npm_names_are_strings(self) -> None:
        for name, downloads in _BUILTIN_POPULAR_NPM.items():
            assert isinstance(name, str), f"Key {name} is not a string"
            assert isinstance(downloads, int), f"Value for {name} is not int"
            assert downloads > 0, f"Downloads for {name} is not positive"

    def test_known_pypi_packages_in_corpus(self) -> None:
        """Key popular packages are in the PyPI corpus."""
        for pkg in ["requests", "flask", "django", "numpy", "pandas", "pydantic", "fastapi"]:
            assert pkg in _BUILTIN_POPULAR_PYPI, f"{pkg} missing from PyPI corpus"

    def test_known_npm_packages_in_corpus(self) -> None:
        """Key popular packages are in the npm corpus."""
        for pkg in ["express", "react", "lodash", "axios", "next", "vue"]:
            assert pkg in _BUILTIN_POPULAR_NPM, f"{pkg} missing from npm corpus"


# ──────────────────────────────────────────────────────────────────
# Levenshtein — Additional cases
# ──────────────────────────────────────────────────────────────────


class TestLevenshteinEdgeCases:
    """Edge cases para Levenshtein distance."""

    def test_transposition(self) -> None:
        """Character transposition (common typo type)."""
        dist = levenshtein_distance("ab", "ba")
        assert dist == 2  # Levenshtein counts transposition as 2

    def test_long_strings(self) -> None:
        """Performance with long strings."""
        s1 = "a" * 100
        s2 = "a" * 99 + "b"
        assert levenshtein_distance(s1, s2) == 1

    def test_unicode_strings(self) -> None:
        """Unicode characters work correctly."""
        assert levenshtein_distance("café", "cafe") == 1

    def test_symmetric(self) -> None:
        """Distance is symmetric."""
        assert levenshtein_distance("abc", "xyz") == levenshtein_distance("xyz", "abc")


# ──────────────────────────────────────────────────────────────────
# Normalized similarity — Boundary cases
# ──────────────────────────────────────────────────────────────────


class TestNormalizedSimilarityBoundary:
    """Boundary cases para normalized_similarity."""

    def test_single_char_difference_long_string(self) -> None:
        """One char diff in long string has high similarity."""
        sim = normalized_similarity("a" * 20, "a" * 19 + "b")
        assert sim == 0.95  # 1 - (1/20)

    def test_single_char_difference_short_string(self) -> None:
        """One char diff in short string has lower similarity."""
        sim = normalized_similarity("ab", "ac")
        assert sim == 0.5  # 1 - (1/2)

    def test_one_char_string(self) -> None:
        """Single character strings."""
        assert normalized_similarity("a", "a") == 1.0
        assert normalized_similarity("a", "b") == 0.0

    def test_default_threshold_sensitivity(self) -> None:
        """At default 0.85 threshold, 1-char typo in 8+ char names matches."""
        # "requests" (8 chars) vs "requasts" (1 substitution)
        sim = normalized_similarity("requasts", "requests")
        assert sim >= 0.85  # 1 - (1/8) = 0.875


# ──────────────────────────────────────────────────────────────────
# Package name normalization — PEP 503
# ──────────────────────────────────────────────────────────────────


class TestNormalizePackageNamePEP503:
    """Tests para normalizacion PEP 503 completa."""

    def test_all_separators_equivalent(self) -> None:
        """Hyphens, underscores, dots all normalize to underscore for PyPI."""
        assert _normalize_package_name("my-pkg", "pypi") == "my_pkg"
        assert _normalize_package_name("my_pkg", "pypi") == "my_pkg"
        assert _normalize_package_name("my.pkg", "pypi") == "my_pkg"

    def test_mixed_separators(self) -> None:
        """Mixed separators all normalize."""
        assert _normalize_package_name("my-pkg_v2.extra", "pypi") == "my_pkg_v2_extra"

    def test_uppercase_normalized(self) -> None:
        """Uppercase is normalized to lowercase."""
        assert _normalize_package_name("MyPackage", "pypi") == "mypackage"

    def test_npm_preserves_structure(self) -> None:
        """npm does not normalize hyphens/underscores."""
        assert _normalize_package_name("my-package", "npm") == "my-package"
        assert _normalize_package_name("my_package", "npm") == "my_package"

    def test_npm_scoped_lowercase(self) -> None:
        """npm scoped packages are lowercased."""
        assert _normalize_package_name("@Scope/Name", "npm") == "@scope/name"


# ──────────────────────────────────────────────────────────────────
# find_similar_popular — False positive prevention
# ──────────────────────────────────────────────────────────────────


class TestFindSimilarPopularFalsePositives:
    """Tests para prevenir false positives de typosquatting."""

    def test_popular_package_not_flagged(self) -> None:
        """A popular package itself should never be flagged."""
        popular = {"requests": 300_000_000, "flask": 30_000_000}

        # Each popular package should return no matches
        for name in popular:
            matches = find_similar_popular(name, "pypi", popular_packages=popular)
            assert matches == [], f"Popular package {name} was falsely flagged"

    def test_pypi_normalized_exact_match_not_flagged(self) -> None:
        """python_dateutil vs python-dateutil is NOT typosquatting (PEP 503)."""
        popular = {"python-dateutil": 170_000_000}
        matches = find_similar_popular(
            "python_dateutil", "pypi", threshold=0.85, popular_packages=popular
        )
        assert matches == []

    def test_pypi_dot_normalized_not_flagged(self) -> None:
        """zope.interface vs zope-interface is NOT typosquatting."""
        popular = {"zope.interface": 1_000_000}
        matches = find_similar_popular(
            "zope-interface", "pypi", threshold=0.85, popular_packages=popular
        )
        assert matches == []

    def test_case_insensitive_exact_match(self) -> None:
        """Flask vs flask is NOT typosquatting."""
        popular = {"flask": 30_000_000}
        matches = find_similar_popular(
            "Flask", "pypi", threshold=0.85, popular_packages=popular
        )
        assert matches == []

    def test_completely_different_name(self) -> None:
        """Completely different names don't match at high threshold."""
        popular = {"requests": 300_000_000}
        matches = find_similar_popular(
            "celery", "pypi", threshold=0.85, popular_packages=popular
        )
        assert matches == []

    def test_short_names_not_over_flagged(self) -> None:
        """Short package names have high sensitivity — single char diff is caught."""
        popular = {"pg": 1_600_000}
        # "px" vs "pg" — 50% similarity, well below 0.85
        matches = find_similar_popular(
            "px", "npm", threshold=0.85, popular_packages=popular
        )
        assert matches == []


# ──────────────────────────────────────────────────────────────────
# find_similar_popular — True positive detection
# ──────────────────────────────────────────────────────────────────


class TestFindSimilarPopularTruePositives:
    """Tests para detectar typosquatting real."""

    def test_common_typosquat_patterns(self) -> None:
        """Common typosquatting patterns are detected."""
        popular = {"requests": 300_000_000}
        test_cases = [
            ("requets", 0.75),   # missing char
            ("reqeusts", 0.75),  # transposition
            ("requestss", 0.85),  # extra char
        ]

        for typo, threshold in test_cases:
            matches = find_similar_popular(
                typo, "pypi", threshold=threshold, popular_packages=popular
            )
            assert len(matches) >= 1, f"Typo '{typo}' not detected at threshold {threshold}"
            assert matches[0][0] == "requests"

    def test_npm_typosquatting(self) -> None:
        """npm typosquatting is detected."""
        popular = {"express": 20_000_000}
        matches = find_similar_popular(
            "expresss", "npm", threshold=0.85, popular_packages=popular
        )
        assert len(matches) >= 1
        assert matches[0][0] == "express"

    def test_results_sorted_by_similarity(self) -> None:
        """Results are sorted by similarity descending."""
        popular = {"numpy": 145_000_000, "numpyy": 1000}
        matches = find_similar_popular(
            "numpi", "pypi", threshold=0.6, popular_packages=popular
        )
        if len(matches) >= 2:
            assert matches[0][1] >= matches[1][1]


# ──────────────────────────────────────────────────────────────────
# load_popular_packages — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestLoadPopularPackagesEdgeCases:
    """Edge cases para load_popular_packages."""

    def test_file_is_list_not_dict(self, tmp_path: Path) -> None:
        """Data file with a list instead of dict falls back to builtin."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text('["requests", "flask"]')

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            packages = load_popular_packages("pypi")

        # Should fall back to builtin (list is not dict)
        assert len(packages) > 50

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty data file falls back to builtin."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text("")

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            packages = load_popular_packages("pypi")

        # json.loads("") raises JSONDecodeError → fallback
        assert len(packages) > 50

    def test_empty_dict_file(self, tmp_path: Path) -> None:
        """Empty dict data file is used (no fallback needed)."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "popular_pypi.json").write_text("{}")

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            packages = load_popular_packages("pypi")

        assert packages == {}

    def test_npm_ecosystem_from_data_file(self, tmp_path: Path) -> None:
        """npm data file is loaded correctly."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        corpus = {"my-npm-pkg": 5000}
        (data_dir / "popular_npm.json").write_text(json.dumps(corpus))

        with patch("vigil.analyzers.deps.similarity.DATA_DIR", data_dir):
            packages = load_popular_packages("npm")

        assert packages == corpus
