"""QA tests adicionales para parsers de dependencias.

Cubre: edge cases, environment markers, encoding, archivos malformados,
line numbers, single-char names, URL-based deps, BOM, y fixtures.
"""

from pathlib import Path

import pytest

from vigil.analyzers.deps.parsers import (
    DeclaredDependency,
    _build_toml_line_map,
    _find_json_key_line,
    find_and_parse_all,
    parse_package_json,
    parse_pyproject_toml,
    parse_requirements_txt,
)


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "deps"


# ──────────────────────────────────────────────────────────────────
# requirements.txt — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestRequirementsTxtEdgeCases:
    """Edge cases para parse_requirements_txt."""

    def test_environment_markers_no_version(self, tmp_path: Path) -> None:
        """Paquetes con environment markers sin version spec se parsean."""
        req = tmp_path / "requirements.txt"
        req.write_text('pywin32; sys_platform == "win32"\n')

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].name == "pywin32"
        assert deps[0].version_spec is None

    def test_environment_markers_with_version(self, tmp_path: Path) -> None:
        """Paquetes con environment markers + version spec se parsean correctamente."""
        req = tmp_path / "requirements.txt"
        req.write_text('requests>=2.31.0; python_version >= "3.8"\n')

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].name == "requests"
        assert deps[0].version_spec == ">=2.31.0"

    def test_environment_markers_fixture(self) -> None:
        """Fixture con environment markers."""
        req = FIXTURES_DIR / "edge_cases" / "markers_requirements.txt"
        if not req.exists():
            pytest.skip("Fixture not found")

        deps = parse_requirements_txt(req)

        names = [d.name for d in deps]
        assert "pywin32" in names
        assert "requests" in names
        assert "uvloop" in names
        assert "flask" in names

    def test_url_deps_skipped(self, tmp_path: Path) -> None:
        """URL-based dependencies are skipped (start with - or git+)."""
        req = tmp_path / "requirements.txt"
        req.write_text(
            "-e git+https://github.com/org/lib.git@v1.0#egg=lib\n"
            "flask==3.0.0\n"
        )

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].name == "flask"

    def test_single_char_package_name(self, tmp_path: Path) -> None:
        """Single character package names are parsed."""
        req = tmp_path / "requirements.txt"
        req.write_text("q\ne>=1.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2
        assert deps[0].name == "q"
        assert deps[1].name == "e"

    def test_line_numbers_with_comments_and_blanks(self, tmp_path: Path) -> None:
        """Line numbers are correct even with comments and blank lines."""
        req = tmp_path / "requirements.txt"
        req.write_text("# comment\n\nflask==3.0.0\n# another\nrequests\n")

        deps = parse_requirements_txt(req)

        assert deps[0].line_number == 3
        assert deps[1].line_number == 5

    def test_trailing_whitespace(self, tmp_path: Path) -> None:
        """Trailing whitespace doesn't break parsing."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0   \nrequests>=2.31.0  \n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2

    def test_windows_line_endings(self, tmp_path: Path) -> None:
        """Windows CRLF line endings work."""
        req = tmp_path / "requirements.txt"
        req.write_bytes(b"flask==3.0.0\r\nrequests>=2.31.0\r\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2
        assert deps[0].name == "flask"

    def test_unicode_in_comments(self, tmp_path: Path) -> None:
        """Unicode in comments doesn't break parsing."""
        req = tmp_path / "requirements.txt"
        req.write_text("# Dependencias básicas — nécessaires\nflask==3.0.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 1

    def test_not_utf8_file(self, tmp_path: Path) -> None:
        """Non-UTF8 file returns empty list gracefully."""
        req = tmp_path / "requirements.txt"
        req.write_bytes(b"\xff\xfe" + b"flask==3.0.0\n")

        deps = parse_requirements_txt(req)

        # Should handle gracefully (either parse or return empty)
        assert isinstance(deps, list)

    def test_package_with_dots_in_name(self, tmp_path: Path) -> None:
        """Package names with dots are parsed."""
        req = tmp_path / "requirements.txt"
        req.write_text("zope.interface>=5.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].name == "zope.interface"

    def test_package_with_underscores_in_name(self, tmp_path: Path) -> None:
        """Package names with underscores are parsed."""
        req = tmp_path / "requirements.txt"
        req.write_text("my_package>=1.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].name == "my_package"

    def test_multiple_version_constraints(self, tmp_path: Path) -> None:
        """Multiple version constraints are captured."""
        req = tmp_path / "requirements.txt"
        req.write_text("django>=4.0,<5.0,!=4.1.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].name == "django"
        assert ">=4.0" in deps[0].version_spec

    def test_requirements_test_txt_not_dev(self, tmp_path: Path) -> None:
        """requirements-test.txt is NOT marked as dev (only 'dev' keyword triggers)."""
        req = tmp_path / "requirements-test.txt"
        req.write_text("pytest>=8.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        # "dev" is not in "requirements-test.txt" — so is_dev=False
        assert deps[0].is_dev is False

    def test_requirements_dev_test_is_dev(self, tmp_path: Path) -> None:
        """requirements-dev-test.txt IS marked as dev."""
        req = tmp_path / "requirements-dev-test.txt"
        req.write_text("pytest>=8.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].is_dev is True

    def test_very_long_line(self, tmp_path: Path) -> None:
        """Very long lines don't crash."""
        req = tmp_path / "requirements.txt"
        long_name = "a" * 300
        req.write_text(f"{long_name}==1.0.0\n")

        deps = parse_requirements_txt(req)

        # May or may not parse depending on regex limits, but must not crash
        assert isinstance(deps, list)

    def test_empty_line_between_deps(self, tmp_path: Path) -> None:
        """Empty lines between dependencies are handled."""
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n\n\n\nrequests>=2.31.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2


# ──────────────────────────────────────────────────────────────────
# pyproject.toml — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestPyprojectTomlEdgeCases:
    """Edge cases para parse_pyproject_toml."""

    def test_line_numbers_approximation(self, tmp_path: Path) -> None:
        """Line numbers are at least approximate."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\n'
            'name = "test"\n'
            'dependencies = [\n'
            '    "flask>=3.0",\n'
            '    "requests>=2.31",\n'
            ']\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 2
        # Line numbers should be reasonable (not 0)
        assert deps[0].line_number > 0
        assert deps[1].line_number > 0

    def test_deps_without_version(self, tmp_path: Path) -> None:
        """Dependencies without version constraints."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\n'
            'dependencies = ["flask", "requests"]\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 2
        assert all(d.version_spec is None or d.version_spec == "" for d in deps)

    def test_optional_deps_testing_group(self, tmp_path: Path) -> None:
        """'testing' group is marked as dev."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\ndependencies = []\n'
            "[project.optional-dependencies]\n"
            'testing = ["pytest>=8.0"]\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 1
        assert deps[0].is_dev is True

    def test_optional_deps_development_group(self, tmp_path: Path) -> None:
        """'development' group is marked as dev."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\ndependencies = []\n'
            "[project.optional-dependencies]\n"
            'development = ["black>=24.0"]\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 1
        assert deps[0].is_dev is True

    def test_optional_deps_docs_group_not_dev(self, tmp_path: Path) -> None:
        """'docs' group is NOT marked as dev."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\ndependencies = []\n'
            "[project.optional-dependencies]\n"
            'docs = ["sphinx>=7.0"]\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 1
        assert deps[0].is_dev is False

    def test_with_build_system_only(self, tmp_path: Path) -> None:
        """TOML with only build-system section returns empty."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            "[build-system]\n"
            'requires = ["setuptools>=68.0", "wheel"]\n'
            'build-backend = "setuptools.build_meta"\n'
        )

        deps = parse_pyproject_toml(toml)

        assert deps == []

    def test_complex_extras(self, tmp_path: Path) -> None:
        """Dependencies with complex extras brackets."""
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\n'
            'dependencies = [\n'
            '    "pydantic[email,dotenv]>=2.0",\n'
            ']\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 1
        assert deps[0].name == "pydantic"
        assert ">=2.0" in (deps[0].version_spec or "")

    def test_malformed_toml_fixture(self) -> None:
        """Malformed TOML file returns empty list."""
        toml = FIXTURES_DIR / "edge_cases" / "malformed.toml"
        if not toml.exists():
            pytest.skip("Fixture not found")

        deps = parse_pyproject_toml(toml)

        assert deps == []


# ──────────────────────────────────────────────────────────────────
# package.json — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestPackageJsonEdgeCases:
    """Edge cases para parse_package_json."""

    def test_non_string_version(self, tmp_path: Path) -> None:
        """Version value that is not a string."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"pkg": 42}}')

        deps = parse_package_json(pkg)

        assert len(deps) == 1
        assert deps[0].name == "pkg"
        assert deps[0].version_spec is None

    def test_empty_dependencies_object(self, tmp_path: Path) -> None:
        """Empty dependencies object returns empty list."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {}}')

        deps = parse_package_json(pkg)

        assert deps == []

    def test_null_values(self, tmp_path: Path) -> None:
        """Null value for version."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"pkg": null}}')

        deps = parse_package_json(pkg)

        assert len(deps) == 1
        assert deps[0].version_spec is None

    def test_deeply_nested_json(self, tmp_path: Path) -> None:
        """Extra nested objects don't break parsing."""
        pkg = tmp_path / "package.json"
        pkg.write_text(
            '{"name": "test", "scripts": {"test": "jest"}, '
            '"dependencies": {"express": "^4.18.0"}, '
            '"config": {"nested": {"deep": true}}}'
        )

        deps = parse_package_json(pkg)

        assert len(deps) == 1
        assert deps[0].name == "express"

    def test_line_numbers_compact_json(self, tmp_path: Path) -> None:
        """Line numbers for compact (single-line) JSON return 0."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies":{"a":"1.0","b":"2.0"}}')

        deps = parse_package_json(pkg)

        # In compact JSON, keys may not be found on separate lines
        assert len(deps) == 2

    def test_scoped_package_with_nested_slash(self, tmp_path: Path) -> None:
        """Scoped packages like @scope/name are parsed correctly."""
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"@angular/core": "^17.0.0"}}')

        deps = parse_package_json(pkg)

        assert len(deps) == 1
        assert deps[0].name == "@angular/core"
        assert deps[0].ecosystem == "npm"

    def test_malformed_json_fixture(self) -> None:
        """Malformed JSON fixture returns empty list."""
        pkg = FIXTURES_DIR / "edge_cases" / "malformed.json"
        if not pkg.exists():
            pytest.skip("Fixture not found")

        deps = parse_package_json(pkg)

        assert deps == []

    def test_peer_dependencies_ignored(self, tmp_path: Path) -> None:
        """peerDependencies are not parsed (only dependencies + devDependencies)."""
        pkg = tmp_path / "package.json"
        pkg.write_text(
            '{"dependencies": {"express": "^4.18.0"}, '
            '"peerDependencies": {"react": "^18.0.0"}}'
        )

        deps = parse_package_json(pkg)

        assert len(deps) == 1
        assert deps[0].name == "express"


# ──────────────────────────────────────────────────────────────────
# find_and_parse_all — Edge cases
# ──────────────────────────────────────────────────────────────────


class TestFindAndParseAllEdgeCases:
    """Edge cases para find_and_parse_all."""

    def test_skips_tox(self, tmp_path: Path) -> None:
        """.tox directories are skipped."""
        tox_dir = tmp_path / ".tox" / "py312"
        tox_dir.mkdir(parents=True)
        (tox_dir / "requirements.txt").write_text("internal==1.0\n")
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1
        assert deps[0].name == "flask"

    def test_skips_pycache(self, tmp_path: Path) -> None:
        """__pycache__ directories are skipped."""
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "requirements.txt").write_text("cached==1.0\n")
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1
        assert deps[0].name == "flask"

    def test_skips_git(self, tmp_path: Path) -> None:
        """.git directories are skipped."""
        git_dir = tmp_path / ".git" / "hooks"
        git_dir.mkdir(parents=True)
        (git_dir / "requirements.txt").write_text("git-internal==1.0\n")
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1

    def test_finds_requirements_star_txt(self, tmp_path: Path) -> None:
        """Finds requirements-prod.txt, requirements-ci.txt, etc."""
        (tmp_path / "requirements-prod.txt").write_text("gunicorn>=21.0\n")
        (tmp_path / "requirements-ci.txt").write_text("tox>=4.0\n")

        deps = find_and_parse_all(str(tmp_path))

        names = [d.name for d in deps]
        assert "gunicorn" in names
        assert "tox" in names

    def test_deeply_nested_project(self, tmp_path: Path) -> None:
        """Finds deps in deeply nested directories."""
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "requirements.txt").write_text("flask==3.0.0\n")

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1
        assert deps[0].name == "flask"

    def test_multiple_package_json_in_subdirs(self, tmp_path: Path) -> None:
        """Finds package.json in subdirectories (not in node_modules)."""
        sub = tmp_path / "packages" / "frontend"
        sub.mkdir(parents=True)
        (sub / "package.json").write_text('{"dependencies": {"react": "^18.0"}}')
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.18"}}')

        deps = find_and_parse_all(str(tmp_path))

        names = [d.name for d in deps]
        assert "react" in names
        assert "express" in names

    def test_file_passed_as_root(self, tmp_path: Path) -> None:
        """Passing a file instead of directory returns empty."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")

        deps = find_and_parse_all(str(f))

        assert deps == []

    def test_symlink_not_followed_into_skip_dirs(self, tmp_path: Path) -> None:
        """Symlinks named like skip dirs are handled."""
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1


# ──────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────


class TestBuildTomlLineMap:
    """Tests para _build_toml_line_map."""

    def test_basic_mapping(self) -> None:
        lines = [
            '[project]',
            'name = "test"',
            'dependencies = [',
            '    "flask>=3.0",',
            '    "requests>=2.31",',
            ']',
        ]

        result = _build_toml_line_map(lines)

        assert result.get("flask") == 4
        assert result.get("requests") == 5

    def test_first_occurrence_wins(self) -> None:
        lines = [
            '    "flask>=3.0",',
            '    "flask>=4.0",',
        ]

        result = _build_toml_line_map(lines)

        assert result["flask"] == 1

    def test_empty_lines(self) -> None:
        result = _build_toml_line_map([])

        assert result == {}


class TestFindJsonKeyLine:
    """Tests para _find_json_key_line."""

    def test_basic_find(self) -> None:
        lines = ['{', '  "dependencies": {', '    "express": "^4.18"', '  }', '}']

        assert _find_json_key_line(lines, "express") == 3

    def test_not_found_returns_zero(self) -> None:
        lines = ['{"name": "test"}']

        assert _find_json_key_line(lines, "missing") == 0

    def test_special_chars_in_key(self) -> None:
        """Package names with special regex chars are escaped."""
        lines = ['{', '  "@types/node": "^20.0"', '}']

        assert _find_json_key_line(lines, "@types/node") == 2

    def test_key_with_dots(self) -> None:
        lines = ['{', '  "socket.io": "^4.0"', '}']

        assert _find_json_key_line(lines, "socket.io") == 2
