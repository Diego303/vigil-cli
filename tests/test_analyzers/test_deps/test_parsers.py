"""Tests para parsers de dependencias."""

from pathlib import Path

import pytest

from vigil.analyzers.deps.parsers import (
    DeclaredDependency,
    find_and_parse_all,
    parse_package_json,
    parse_pyproject_toml,
    parse_requirements_txt,
)


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "deps"


class TestParseRequirementsTxt:
    """Tests para parse_requirements_txt."""

    def test_basic_requirements(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\nrequests>=2.31.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2
        assert deps[0].name == "flask"
        assert deps[0].version_spec == "==3.0.0"
        assert deps[0].ecosystem == "pypi"
        assert deps[0].line_number == 1
        assert deps[0].is_dev is False

        assert deps[1].name == "requests"
        assert deps[1].version_spec == ">=2.31.0"

    def test_comments_and_blanks(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("# A comment\n\nflask==3.0.0\n# Another comment\nrequests\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2
        assert deps[0].name == "flask"
        assert deps[1].name == "requests"
        assert deps[1].version_spec is None

    def test_flags_skipped(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("-r requirements-base.txt\n--index-url https://pypi.org\nflask\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].name == "flask"

    def test_extras(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("pydantic[email]>=2.0\nuvicorn[standard]==0.29.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2
        assert deps[0].name == "pydantic"
        assert deps[0].version_spec == ">=2.0"
        assert deps[1].name == "uvicorn"

    def test_dev_requirements(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements-dev.txt"
        req.write_text("pytest>=8.0\nruff>=0.4\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2
        assert all(d.is_dev for d in deps)

    def test_tilde_version(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("PyJWT~=2.8.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 1
        assert deps[0].name == "PyJWT"
        assert deps[0].version_spec == "~=2.8.0"

    def test_empty_file(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("")

        deps = parse_requirements_txt(req)

        assert deps == []

    def test_only_comments(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("# Only comments\n# Nothing here\n")

        deps = parse_requirements_txt(req)

        assert deps == []

    def test_no_version_spec(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("flask\nrequests\nclick\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 3
        assert all(d.version_spec is None for d in deps)

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        req = tmp_path / "nonexistent.txt"

        deps = parse_requirements_txt(req)

        assert deps == []

    def test_complex_version_specifiers(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("django>=4.0,<5.0\nnumpy!=1.21.0\n")

        deps = parse_requirements_txt(req)

        assert len(deps) == 2
        assert deps[0].name == "django"
        assert deps[0].version_spec == ">=4.0,<5.0"

    def test_fixture_valid_project(self) -> None:
        req = FIXTURES_DIR / "valid_project" / "requirements.txt"
        if not req.exists():
            pytest.skip("Fixture not found")

        deps = parse_requirements_txt(req)

        names = [d.name for d in deps]
        assert "flask" in names
        assert "requests" in names
        assert "PyJWT" in names
        assert "click" in names
        assert "pydantic" in names

    def test_source_file_is_absolute_path(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        deps = parse_requirements_txt(req)

        assert deps[0].source_file == str(req)


class TestParsePyprojectToml:
    """Tests para parse_pyproject_toml."""

    def test_basic_dependencies(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\n'
            'dependencies = [\n    "flask>=3.0",\n    "requests>=2.31",\n]\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 2
        assert deps[0].name == "flask"
        assert deps[0].version_spec == ">=3.0"
        assert deps[0].ecosystem == "pypi"
        assert deps[0].is_dev is False

    def test_optional_dependencies(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\n'
            "dependencies = []\n"
            "[project.optional-dependencies]\n"
            'dev = [\n    "pytest>=8.0",\n    "ruff>=0.4",\n]\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 2
        assert all(d.is_dev for d in deps)

    def test_no_project_section(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("[build-system]\nrequires = ['setuptools']\n")

        deps = parse_pyproject_toml(toml)

        assert deps == []

    def test_empty_dependencies(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text('[project]\nname = "test"\ndependencies = []\n')

        deps = parse_pyproject_toml(toml)

        assert deps == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        toml = tmp_path / "nonexistent.toml"

        deps = parse_pyproject_toml(toml)

        assert deps == []

    def test_invalid_toml(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("this is not valid toml [[[")

        deps = parse_pyproject_toml(toml)

        assert deps == []

    def test_fixture_valid_project(self) -> None:
        toml = FIXTURES_DIR / "valid_project" / "pyproject.toml"
        if not toml.exists():
            pytest.skip("Fixture not found")

        deps = parse_pyproject_toml(toml)

        names = [d.name for d in deps]
        assert "click" in names
        assert "pydantic" in names
        assert "httpx" in names

    def test_version_with_extras(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\n'
            'dependencies = [\n    "pydantic[email]>=2.0",\n]\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 1
        assert deps[0].name == "pydantic"
        assert deps[0].version_spec == ">=2.0"

    def test_multiple_optional_groups(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\ndependencies = []\n'
            "[project.optional-dependencies]\n"
            'dev = ["pytest>=8.0"]\n'
            'docs = ["sphinx>=7.0"]\n'
        )

        deps = parse_pyproject_toml(toml)

        assert len(deps) == 2
        dev_deps = [d for d in deps if d.is_dev]
        non_dev = [d for d in deps if not d.is_dev]
        assert len(dev_deps) == 1
        assert dev_deps[0].name == "pytest"
        # "docs" group is not in dev groups, so not marked as dev
        assert len(non_dev) == 1
        assert non_dev[0].name == "sphinx"


class TestParsePackageJson:
    """Tests para parse_package_json."""

    def test_basic_dependencies(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"express": "^4.18.0", "lodash": "^4.17.21"}}')

        deps = parse_package_json(pkg)

        assert len(deps) == 2
        assert deps[0].name == "express"
        assert deps[0].version_spec == "^4.18.0"
        assert deps[0].ecosystem == "npm"
        assert deps[0].is_dev is False

    def test_dev_dependencies(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text('{"devDependencies": {"jest": "^29.0.0", "typescript": "^5.0.0"}}')

        deps = parse_package_json(pkg)

        assert len(deps) == 2
        assert all(d.is_dev for d in deps)

    def test_both_dep_types(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            '{"dependencies": {"express": "^4.18.0"}, '
            '"devDependencies": {"jest": "^29.0.0"}}'
        )

        deps = parse_package_json(pkg)

        assert len(deps) == 2
        prod = [d for d in deps if not d.is_dev]
        dev = [d for d in deps if d.is_dev]
        assert len(prod) == 1
        assert len(dev) == 1

    def test_empty_deps(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text('{"name": "test", "version": "1.0.0"}')

        deps = parse_package_json(pkg)

        assert deps == []

    def test_invalid_json(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text("not json at all {{{")

        deps = parse_package_json(pkg)

        assert deps == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        pkg = tmp_path / "nonexistent.json"

        deps = parse_package_json(pkg)

        assert deps == []

    def test_scoped_packages(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"@types/node": "^20.0.0", "@nestjs/core": "^10.0.0"}}')

        deps = parse_package_json(pkg)

        assert len(deps) == 2
        assert deps[0].name == "@types/node"
        assert deps[1].name == "@nestjs/core"

    def test_line_numbers(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(
            '{\n  "dependencies": {\n    "express": "^4.18.0",\n    "lodash": "^4.17.21"\n  }\n}'
        )

        deps = parse_package_json(pkg)

        assert deps[0].line_number == 3
        assert deps[1].line_number == 4

    def test_fixture_npm_project(self) -> None:
        pkg = FIXTURES_DIR / "npm_project" / "package.json"
        if not pkg.exists():
            pytest.skip("Fixture not found")

        deps = parse_package_json(pkg)

        names = [d.name for d in deps]
        assert "express" in names
        assert "lodash" in names
        assert "nonexistent-ai-pkg" in names
        assert "jest" in names
        assert "typescript" in names


class TestFindAndParseAll:
    """Tests para find_and_parse_all."""

    def test_finds_requirements_txt(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.txt"
        req.write_text("flask==3.0.0\n")

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1
        assert deps[0].name == "flask"

    def test_finds_pyproject_toml(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\nname = "test"\ndependencies = ["flask>=3.0"]\n'
        )

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1
        assert deps[0].name == "flask"

    def test_finds_package_json(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"express": "^4.18.0"}}')

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1
        assert deps[0].name == "express"

    def test_finds_all_types(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.18.0"}}')

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 2
        ecosystems = {d.ecosystem for d in deps}
        assert ecosystems == {"pypi", "npm"}

    def test_skips_venv(self, tmp_path: Path) -> None:
        venv_dir = tmp_path / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "requirements.txt").write_text("internal-pkg==1.0\n")
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1
        assert deps[0].name == "flask"

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        nm = tmp_path / "node_modules" / "some-pkg"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text('{"dependencies": {"internal": "1.0.0"}}')
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.18.0"}}')

        deps = find_and_parse_all(str(tmp_path))

        assert len(deps) == 1
        assert deps[0].name == "express"

    def test_nonexistent_root(self) -> None:
        deps = find_and_parse_all("/nonexistent/path")

        assert deps == []

    def test_empty_directory(self, tmp_path: Path) -> None:
        deps = find_and_parse_all(str(tmp_path))

        assert deps == []

    def test_nested_requirements(self, tmp_path: Path) -> None:
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "requirements.txt").write_text("requests>=2.31.0\n")
        (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")

        deps = find_and_parse_all(str(tmp_path))

        names = [d.name for d in deps]
        assert "flask" in names
        assert "requests" in names
