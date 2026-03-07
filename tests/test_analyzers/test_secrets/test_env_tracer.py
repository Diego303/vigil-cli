"""Tests para env_tracer — tracing de valores de .env.example al codigo."""

from pathlib import Path

import pytest

from vigil.analyzers.secrets.env_tracer import (
    find_env_example_files,
    find_env_values_in_code,
    parse_env_example,
)


class TestFindEnvExampleFiles:
    """Tests para find_env_example_files."""

    def test_finds_env_example(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("KEY=value\n")
        files = find_env_example_files(str(tmp_path))
        assert len(files) == 1
        assert files[0].name == ".env.example"

    def test_finds_env_sample(self, tmp_path: Path) -> None:
        (tmp_path / ".env.sample").write_text("KEY=value\n")
        files = find_env_example_files(str(tmp_path))
        assert len(files) == 1

    def test_finds_multiple(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("KEY=value\n")
        (tmp_path / ".env.sample").write_text("KEY=value2\n")
        files = find_env_example_files(str(tmp_path))
        assert len(files) == 2

    def test_no_env_files(self, tmp_path: Path) -> None:
        files = find_env_example_files(str(tmp_path))
        assert files == []

    def test_from_file_path(self, tmp_path: Path) -> None:
        """find_env_example_files should work when given a file path."""
        (tmp_path / ".env.example").write_text("KEY=value\n")
        child = tmp_path / "app.py"
        child.touch()
        files = find_env_example_files(str(child))
        assert len(files) == 1


class TestParseEnvExample:
    """Tests para parse_env_example."""

    def test_basic_parsing(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("API_KEY=your-api-key-here\nSECRET=changeme\n")

        entries = parse_env_example(env)
        assert len(entries) == 2
        assert entries[0].key == "API_KEY"
        assert entries[0].value == "your-api-key-here"
        assert entries[1].key == "SECRET"
        assert entries[1].value == "changeme"

    def test_ignores_comments(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("# This is a comment\nKEY=value-here\n")

        entries = parse_env_example(env)
        assert len(entries) == 1
        assert entries[0].key == "KEY"

    def test_ignores_empty_lines(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("\n\nKEY=value-here\n\n")

        entries = parse_env_example(env)
        assert len(entries) == 1

    def test_ignores_empty_values(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("KEY=\nOTHER=value-here\n")

        entries = parse_env_example(env)
        assert len(entries) == 1
        assert entries[0].key == "OTHER"

    def test_quoted_values(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text('KEY="my-quoted-value"\n')

        entries = parse_env_example(env)
        assert len(entries) == 1
        assert entries[0].value == "my-quoted-value"

    def test_single_quoted_values(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("KEY='my-quoted-value'\n")

        entries = parse_env_example(env)
        assert len(entries) == 1
        assert entries[0].value == "my-quoted-value"

    def test_ignores_generic_values(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("DEBUG=true\nPORT=3000\nENV=development\n")

        entries = parse_env_example(env)
        assert len(entries) == 0

    def test_ignores_variable_references(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("KEY=${OTHER_KEY}\nDYN=$DYNAMIC\n")

        entries = parse_env_example(env)
        assert len(entries) == 0

    def test_line_numbers_correct(self, tmp_path: Path) -> None:
        env = tmp_path / ".env.example"
        env.write_text("# comment\nFIRST=value1\n\nSECOND=value2\n")

        entries = parse_env_example(env)
        assert entries[0].line == 2
        assert entries[1].line == 4

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        entries = parse_env_example(tmp_path / "nonexistent")
        assert entries == []


class TestFindEnvValuesInCode:
    """Tests para busqueda de valores de .env.example en codigo."""

    def test_finds_matching_value(self, tmp_path: Path) -> None:
        from vigil.analyzers.secrets.env_tracer import EnvExampleEntry

        entries = [
            EnvExampleEntry(
                key="API_KEY", value="your-api-key-here",
                file=".env.example", line=1,
            ),
        ]
        code = 'api_key = "your-api-key-here"\n'

        matches = find_env_values_in_code(code, entries)
        assert len(matches) == 1
        assert matches[0][0] == 1  # line number
        assert matches[0][1].key == "API_KEY"

    def test_no_match_different_value(self, tmp_path: Path) -> None:
        from vigil.analyzers.secrets.env_tracer import EnvExampleEntry

        entries = [
            EnvExampleEntry(
                key="API_KEY", value="your-api-key-here",
                file=".env.example", line=1,
            ),
        ]
        code = 'api_key = "real-production-key"\n'

        matches = find_env_values_in_code(code, entries)
        assert len(matches) == 0

    def test_ignores_comments_in_code(self, tmp_path: Path) -> None:
        from vigil.analyzers.secrets.env_tracer import EnvExampleEntry

        entries = [
            EnvExampleEntry(
                key="API_KEY", value="your-api-key-here",
                file=".env.example", line=1,
            ),
        ]
        code = '# api_key = "your-api-key-here"\n'

        matches = find_env_values_in_code(code, entries)
        assert len(matches) == 0

    def test_ignores_short_values(self, tmp_path: Path) -> None:
        from vigil.analyzers.secrets.env_tracer import EnvExampleEntry

        entries = [
            EnvExampleEntry(
                key="MODE", value="dev",
                file=".env.example", line=1,
            ),
        ]
        code = 'mode = "dev"\n'

        matches = find_env_values_in_code(code, entries)
        assert len(matches) == 0  # "dev" is < 5 chars

    def test_multiple_matches(self, tmp_path: Path) -> None:
        from vigil.analyzers.secrets.env_tracer import EnvExampleEntry

        entries = [
            EnvExampleEntry(key="KEY1", value="value-one-here", file=".env.example", line=1),
            EnvExampleEntry(key="KEY2", value="value-two-here", file=".env.example", line=2),
        ]
        code = 'k1 = "value-one-here"\nk2 = "value-two-here"\n'

        matches = find_env_values_in_code(code, entries)
        assert len(matches) == 2
