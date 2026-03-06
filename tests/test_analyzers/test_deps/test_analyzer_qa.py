"""QA tests adicionales para DependencyAnalyzer.

Cubre: false positives/negatives, integración analyzer-registry-similarity,
edge cases de DEP-002 boundary, DEP-007 con npm prefixed versions,
multi-ecosystem, metadata completa, y regression tests.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from vigil.analyzers.deps.analyzer import (
    DependencyAnalyzer,
    _deduplicate_deps,
    _extract_pinned_version,
    _extract_roots,
)
from vigil.analyzers.deps.parsers import DeclaredDependency
from vigil.analyzers.deps.registry_client import PackageInfo
from vigil.config.schema import ScanConfig
from vigil.core.finding import Category, Severity


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "deps"


# ──────────────────────────────────────────────────────────────────
# False Positives — Legitimate code should NOT generate findings
# ──────────────────────────────────────────────────────────────────


class TestFalsePositives:
    """Tests para verificar que código legítimo no genera false positives."""

    def test_clean_project_no_findings(self, tmp_path: Path) -> None:
        """Clean project fixture has no offline findings."""
        clean = FIXTURES_DIR / "clean_project"
        if not clean.exists():
            pytest.skip("Fixture not found")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True

        result = analyzer.analyze([str(clean)], config)

        # Popular packages should not be flagged
        dep003 = [f for f in result if f.rule_id == "DEP-003"]
        flagged_names = [f.metadata.get("package") for f in dep003]
        for name in ["flask", "requests", "click", "pydantic", "httpx"]:
            assert name not in flagged_names, f"False positive: {name} flagged as typosquatting"

    def test_pep503_normalized_names_no_typosquatting(self, tmp_path: Path) -> None:
        """PEP 503 normalized names are NOT flagged (e.g., python_dateutil)."""
        req = tmp_path / "requirements.txt"
        req.write_text("python_dateutil>=2.8\ntyping_extensions>=4.0\n")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True

        result = analyzer.analyze([str(tmp_path)], config)

        dep003 = [f for f in result if f.rule_id == "DEP-003"]
        assert len(dep003) == 0, f"False positive typosquatting: {[f.metadata for f in dep003]}"

    def test_popular_package_exact_name(self, tmp_path: Path) -> None:
        """Every popular PyPI package should NOT be flagged."""
        req = tmp_path / "requirements.txt"
        # Test a subset of popular packages
        req.write_text("requests\nnumpy\npandas\nflask\ndjango\nfastapi\n")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True

        result = analyzer.analyze([str(tmp_path)], config)

        dep003 = [f for f in result if f.rule_id == "DEP-003"]
        assert len(dep003) == 0

    def test_legitimate_with_registry_no_findings(self, tmp_path: Path) -> None:
        """Legitimate package with all good metadata generates no findings."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        mock_pkg = PackageInfo(
            name="flask",
            exists=True,
            ecosystem="pypi",
            created_at="2010-04-06T00:00:00+00:00",
            source_url="https://github.com/pallets/flask",
            latest_version="3.0.0",
            versions=["2.0.0", "3.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        # No findings at all
        assert len(result) == 0


# ──────────────────────────────────────────────────────────────────
# False Negatives — Problematic code SHOULD generate findings
# ──────────────────────────────────────────────────────────────────


class TestFalseNegatives:
    """Tests para verificar que código problemático SÍ genera findings."""

    def test_hallucinated_dep_always_critical(self, tmp_path: Path) -> None:
        """DEP-001 is always CRITICAL severity."""
        req = tmp_path / "requirements.txt"
        req.write_text("ai-generated-fake-lib==1.0.0\n")

        mock_pkg = PackageInfo(name="ai-generated-fake-lib", exists=False, ecosystem="pypi")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep001 = [f for f in result if f.rule_id == "DEP-001"]
        assert len(dep001) == 1
        assert dep001[0].severity == Severity.CRITICAL

    def test_hallucinated_no_further_checks(self, tmp_path: Path) -> None:
        """When DEP-001 fires (pkg doesn't exist), DEP-002/005/007 are NOT checked."""
        req = tmp_path / "requirements.txt"
        req.write_text("fake-pkg==99.0.0\n")

        mock_pkg = PackageInfo(name="fake-pkg", exists=False, ecosystem="pypi")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        # Only DEP-001, not DEP-007
        rule_ids = [f.rule_id for f in result]
        dep_registry = [r for r in rule_ids if r in ("DEP-001", "DEP-002", "DEP-005", "DEP-007")]
        assert dep_registry == ["DEP-001"]

    def test_multiple_findings_for_same_package(self, tmp_path: Path) -> None:
        """A package can trigger DEP-002 AND DEP-005 simultaneously."""
        req = tmp_path / "requirements.txt"
        req.write_text("suspicious-pkg==0.0.1\n")

        created = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        mock_pkg = PackageInfo(
            name="suspicious-pkg",
            exists=True,
            ecosystem="pypi",
            created_at=created,
            source_url=None,  # No source repo
            latest_version="0.0.1",
            versions=["0.0.1"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False
        config.deps.min_age_days = 30

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        rule_ids = {f.rule_id for f in result}
        assert "DEP-002" in rule_ids  # Suspiciously new
        assert "DEP-005" in rule_ids  # No source repo


# ──────────────────────────────────────────────────────────────────
# DEP-002 — Boundary conditions
# ──────────────────────────────────────────────────────────────────


class TestDEP002Boundary:
    """Boundary tests para DEP-002 (suspiciously new)."""

    def test_exactly_min_age_days_no_finding(self, tmp_path: Path) -> None:
        """Package created exactly min_age_days ago should NOT trigger DEP-002."""
        req = tmp_path / "requirements.txt"
        req.write_text("pkg==1.0.0\n")

        # Exactly 30 days ago
        created = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        mock_pkg = PackageInfo(
            name="pkg",
            exists=True,
            ecosystem="pypi",
            created_at=created,
            source_url="https://github.com/test/test",
            latest_version="1.0.0",
            versions=["1.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False
        config.deps.min_age_days = 30

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep002 = [f for f in result if f.rule_id == "DEP-002"]
        assert len(dep002) == 0

    def test_one_day_before_min_age_triggers(self, tmp_path: Path) -> None:
        """Package created min_age_days - 1 days ago SHOULD trigger DEP-002."""
        req = tmp_path / "requirements.txt"
        req.write_text("pkg==1.0.0\n")

        created = (datetime.now(timezone.utc) - timedelta(days=29)).isoformat()
        mock_pkg = PackageInfo(
            name="pkg",
            exists=True,
            ecosystem="pypi",
            created_at=created,
            source_url="https://github.com/test/test",
            latest_version="1.0.0",
            versions=["1.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False
        config.deps.min_age_days = 30

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep002 = [f for f in result if f.rule_id == "DEP-002"]
        assert len(dep002) == 1

    def test_no_created_at_skips_dep002(self, tmp_path: Path) -> None:
        """Package without created_at does NOT trigger DEP-002."""
        req = tmp_path / "requirements.txt"
        req.write_text("pkg==1.0.0\n")

        mock_pkg = PackageInfo(
            name="pkg",
            exists=True,
            ecosystem="pypi",
            created_at=None,
            source_url="https://github.com/test/test",
            latest_version="1.0.0",
            versions=["1.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep002 = [f for f in result if f.rule_id == "DEP-002"]
        assert len(dep002) == 0


# ──────────────────────────────────────────────────────────────────
# DEP-007 — Version checks
# ──────────────────────────────────────────────────────────────────


class TestDEP007VersionChecks:
    """Tests para DEP-007 (nonexistent version)."""

    def test_unpinned_version_not_checked(self, tmp_path: Path) -> None:
        """Unpinned versions (>=, ^, ~) don't trigger DEP-007."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask>=3.0.0\n")

        mock_pkg = PackageInfo(
            name="flask",
            exists=True,
            ecosystem="pypi",
            created_at="2010-04-06T00:00:00+00:00",
            source_url="https://github.com/pallets/flask",
            latest_version="3.0.0",
            versions=["3.0.0"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep007 = [f for f in result if f.rule_id == "DEP-007"]
        assert len(dep007) == 0

    def test_npm_prefixed_version_not_checked(self, tmp_path: Path) -> None:
        """npm versions with ^ or ~ prefix don't trigger DEP-007."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"express": "^4.99.99"}}')

        mock_pkg = PackageInfo(
            name="express",
            exists=True,
            ecosystem="npm",
            created_at="2010-12-29T00:00:00+00:00",
            source_url="https://github.com/expressjs/express",
            latest_version="4.18.2",
            versions=["4.18.2"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep007 = [f for f in result if f.rule_id == "DEP-007"]
        assert len(dep007) == 0  # ^4.99.99 is not a pinned version

    def test_dep007_suggestion_shows_latest(self, tmp_path: Path) -> None:
        """DEP-007 suggestion includes the latest version."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==99.0.0\n")

        mock_pkg = PackageInfo(
            name="flask",
            exists=True,
            ecosystem="pypi",
            created_at="2010-04-06T00:00:00+00:00",
            source_url="https://github.com/pallets/flask",
            latest_version="3.1.0",
            versions=["2.0.0", "3.0.0", "3.1.0"],
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep007 = [f for f in result if f.rule_id == "DEP-007"]
        assert len(dep007) == 1
        assert "3.1.0" in dep007[0].suggestion

    def test_dep007_no_versions_list(self, tmp_path: Path) -> None:
        """If versions list is None, DEP-007 is not checked."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==99.0.0\n")

        mock_pkg = PackageInfo(
            name="flask",
            exists=True,
            ecosystem="pypi",
            created_at="2010-04-06T00:00:00+00:00",
            source_url="https://github.com/pallets/flask",
            latest_version="3.0.0",
            versions=None,  # No versions info
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg

            result = analyzer.analyze([str(tmp_path)], config)

        dep007 = [f for f in result if f.rule_id == "DEP-007"]
        assert len(dep007) == 0


# ──────────────────────────────────────────────────────────────────
# _extract_pinned_version — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestExtractPinnedVersionEdgeCases:
    """Edge cases para _extract_pinned_version."""

    def test_pypi_spaces_around_version(self) -> None:
        assert _extract_pinned_version("==  1.0.0  ", "pypi") == "1.0.0"

    def test_pypi_pre_release(self) -> None:
        assert _extract_pinned_version("==1.0.0a1", "pypi") == "1.0.0a1"

    def test_pypi_post_release(self) -> None:
        assert _extract_pinned_version("==1.0.0.post1", "pypi") == "1.0.0.post1"

    def test_pypi_dev_release(self) -> None:
        assert _extract_pinned_version("==1.0.0.dev0", "pypi") == "1.0.0.dev0"

    def test_npm_semver_only(self) -> None:
        """npm only considers exact X.Y.Z as pinned."""
        assert _extract_pinned_version("1.2.3", "npm") == "1.2.3"
        assert _extract_pinned_version("^1.2.3", "npm") is None
        assert _extract_pinned_version("~1.2.3", "npm") is None
        assert _extract_pinned_version(">=1.2.3", "npm") is None
        assert _extract_pinned_version("1.2.3-beta.1", "npm") is None
        assert _extract_pinned_version("*", "npm") is None

    def test_unknown_ecosystem(self) -> None:
        assert _extract_pinned_version("==1.0.0", "cargo") is None

    def test_empty_string(self) -> None:
        assert _extract_pinned_version("", "pypi") is None
        assert _extract_pinned_version("", "npm") is None


# ──────────────────────────────────────────────────────────────────
# _extract_roots — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestExtractRootsEdgeCases:
    """Edge cases para _extract_roots."""

    def test_mixed_files_and_dirs(self, tmp_path: Path) -> None:
        """Mix of files and directories."""
        f = tmp_path / "src" / "app.py"
        f.parent.mkdir(parents=True)
        f.touch()

        roots = _extract_roots([str(f), str(tmp_path)])

        # tmp_path subsumes tmp_path/src, so only tmp_path should remain
        assert len(roots) == 1

    def test_nonexistent_path(self) -> None:
        """Nonexistent paths are included as-is."""
        roots = _extract_roots(["/nonexistent/path"])

        # Nonexistent path is still added (not a file or dir, falls to else)
        assert len(roots) == 1

    def test_duplicate_paths(self, tmp_path: Path) -> None:
        """Duplicate paths are deduplicated."""
        roots = _extract_roots([str(tmp_path), str(tmp_path)])

        assert len(roots) == 1

    def test_nested_subdirs_collapsed(self, tmp_path: Path) -> None:
        """Nested subdirectories are collapsed to the parent."""
        sub1 = tmp_path / "a" / "b"
        sub2 = tmp_path / "a" / "c"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)

        roots = _extract_roots([str(sub1), str(sub2), str(tmp_path)])

        # All are under tmp_path
        assert len(roots) == 1


# ──────────────────────────────────────────────────────────────────
# _deduplicate_deps — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestDeduplicateDepsEdgeCases:
    """Edge cases para _deduplicate_deps."""

    def test_empty_list(self) -> None:
        assert _deduplicate_deps([]) == []

    def test_single_dep(self) -> None:
        deps = [
            DeclaredDependency(
                name="flask", version_spec="==3.0.0",
                source_file="req.txt", line_number=1, ecosystem="pypi",
            )
        ]
        result = _deduplicate_deps(deps)
        assert len(result) == 1

    def test_case_insensitive_dedup(self) -> None:
        """Flask and flask are deduplicated."""
        deps = [
            DeclaredDependency(
                name="Flask", version_spec="==3.0.0",
                source_file="req.txt", line_number=1, ecosystem="pypi",
            ),
            DeclaredDependency(
                name="flask", version_spec=">=3.0",
                source_file="pyproject.toml", line_number=5, ecosystem="pypi",
            ),
        ]
        result = _deduplicate_deps(deps)
        assert len(result) == 1
        assert result[0].name == "Flask"  # First occurrence kept

    def test_same_name_different_ecosystems_kept(self) -> None:
        """Same name in different ecosystems are NOT deduplicated."""
        deps = [
            DeclaredDependency(
                name="redis", version_spec=">=4.0",
                source_file="req.txt", line_number=1, ecosystem="pypi",
            ),
            DeclaredDependency(
                name="redis", version_spec="^4.0.0",
                source_file="package.json", line_number=5, ecosystem="npm",
            ),
        ]
        result = _deduplicate_deps(deps)
        assert len(result) == 2


# ──────────────────────────────────────────────────────────────────
# Registry exception handling
# ──────────────────────────────────────────────────────────────────


class TestRegistryExceptionHandling:
    """Tests para manejo de excepciones en registry checks."""

    def test_registry_exception_logged_not_raised(self, tmp_path: Path) -> None:
        """Exception in registry check is logged, scan continues."""
        req = tmp_path / "requirements.txt"
        req.write_text("pkg-a==1.0\npkg-b==1.0\n")

        call_count = 0

        def check_side_effect(name, ecosystem):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated network error")
            return PackageInfo(
                name=name, exists=True, ecosystem=ecosystem,
                created_at="2020-01-01T00:00:00+00:00",
                source_url="https://example.com",
                latest_version="1.0", versions=["1.0"],
            )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.side_effect = check_side_effect

            result = analyzer.analyze([str(tmp_path)], config)

        # Should not crash, second package still checked
        assert call_count == 2

    def test_verify_registry_false_skips_online(self, tmp_path: Path) -> None:
        """verify_registry=False skips online checks even if not offline."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = False
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            result = analyzer.analyze([str(tmp_path)], config)

        # RegistryClient should not be used
        MockClient.assert_not_called()


# ──────────────────────────────────────────────────────────────────
# Finding metadata completeness
# ──────────────────────────────────────────────────────────────────


class TestFindingMetadataCompleteness:
    """Tests para verificar que todos los findings tienen metadata completa."""

    def test_dep001_has_all_required_fields(self, tmp_path: Path) -> None:
        """DEP-001 finding has all required fields per CLAUDE.md spec."""
        req = tmp_path / "requirements.txt"
        req.write_text("hallucinated-pkg==1.0.0\n")

        mock_pkg = PackageInfo(name="hallucinated-pkg", exists=False, ecosystem="pypi")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg
            result = analyzer.analyze([str(tmp_path)], config)

        finding = [f for f in result if f.rule_id == "DEP-001"][0]

        # Spec requirements from CLAUDE.md
        assert finding.rule_id == "DEP-001"
        assert finding.category == Category.DEPENDENCY
        assert finding.severity == Severity.CRITICAL
        assert "hallucinated-pkg" in finding.message
        assert "does not exist" in finding.message
        assert finding.location.file == str(req)
        assert finding.location.line == 1
        assert finding.suggestion is not None
        assert len(finding.suggestion) > 0
        assert finding.metadata["package"] == "hallucinated-pkg"
        assert finding.metadata["ecosystem"] == "pypi"

    def test_dep003_has_similarity_info(self, tmp_path: Path) -> None:
        """DEP-003 finding includes similarity score and similar package name."""
        req = tmp_path / "requirements.txt"
        req.write_text("reqeusts==2.31.0\n")

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.offline_mode = True
        config.deps.similarity_threshold = 0.75

        result = analyzer.analyze([str(tmp_path)], config)

        dep003 = [f for f in result if f.rule_id == "DEP-003"]
        assert len(dep003) >= 1
        finding = dep003[0]

        assert "similarity" in finding.metadata
        assert "similar_to" in finding.metadata
        assert isinstance(finding.metadata["similarity"], float)
        assert 0.0 <= finding.metadata["similarity"] <= 1.0
        assert finding.location.snippet is not None

    def test_dep007_suggestion_includes_recent_versions(self, tmp_path: Path) -> None:
        """DEP-007 suggestion lists recent available versions."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==99.0.0\n")

        versions = [f"3.0.{i}" for i in range(10)]
        mock_pkg = PackageInfo(
            name="flask", exists=True, ecosystem="pypi",
            created_at="2010-04-06T00:00:00+00:00",
            source_url="https://github.com/pallets/flask",
            latest_version="3.0.9", versions=versions,
        )

        analyzer = DependencyAnalyzer()
        config = ScanConfig()
        config.deps.verify_registry = True
        config.deps.offline_mode = False

        with patch("vigil.analyzers.deps.analyzer.RegistryClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.check.return_value = mock_pkg
            result = analyzer.analyze([str(tmp_path)], config)

        dep007 = [f for f in result if f.rule_id == "DEP-007"]
        assert len(dep007) == 1
        # Should show at most 5 recent versions
        assert "3.0.9" in dep007[0].suggestion
        # Should mention latest
        assert dep007[0].metadata["latest_version"] == "3.0.9"
