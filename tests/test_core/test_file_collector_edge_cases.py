"""Edge case tests para file_collector — robustez y falsos positivos."""

import os

import pytest

from vigil.core.file_collector import (
    DEPENDENCY_FILES,
    LANGUAGE_EXTENSIONS,
    _should_include_file,
    collect_files,
)


class TestExcludePatternEdgeCases:
    """Verifica que los patrones de exclusion funcionan correctamente."""

    def test_exclude_node_modules_nested(self, tmp_path):
        """node_modules en cualquier nivel debe excluirse."""
        deep = tmp_path / "project" / "node_modules" / "express" / "lib"
        deep.mkdir(parents=True)
        (deep / "index.js").write_text("module.exports = {};")
        files = collect_files([str(tmp_path)], exclude=["node_modules/"])
        assert not any("node_modules" in f for f in files), (
            f"node_modules files should be excluded, got: {files}"
        )

    def test_exclude_venv_nested(self, tmp_path):
        """.venv en cualquier nivel debe excluirse."""
        venv = tmp_path / ".venv" / "lib" / "python3.12"
        venv.mkdir(parents=True)
        (venv / "site.py").write_text("# venv")
        files = collect_files([str(tmp_path)], exclude=[".venv/"])
        assert not any(".venv" in f for f in files)

    def test_exclude_pattern_does_not_overmatch_prefix(self, tmp_path):
        """exclude 'build/' should NOT exclude 'rebuild/' (path-component match)."""
        rebuild_dir = tmp_path / "rebuild"
        rebuild_dir.mkdir()
        (rebuild_dir / "app.py").write_text("x = 1")
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "app.py").write_text("x = 1")

        files = collect_files(
            [str(tmp_path)], exclude=["build/"], languages=["python"]
        )
        # rebuild/ should NOT be excluded
        assert any("rebuild" in f for f in files), (
            "rebuild/ should not be excluded by 'build/' pattern"
        )
        # build/ SHOULD be excluded — check by path component
        build_app = str((build_dir / "app.py").resolve())
        assert build_app not in files, (
            f"build/app.py should be excluded, got files: {files}"
        )

    def test_exclude_git_directory(self, tmp_path):
        git_dir = tmp_path / ".git" / "objects"
        git_dir.mkdir(parents=True)
        (git_dir / "pack.py").write_text("# git object")
        files = collect_files([str(tmp_path)], exclude=[".git/"])
        assert not any(".git" in f for f in files)

    def test_exclude_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "module.cpython-312.pyc").write_text("")
        files = collect_files([str(tmp_path)], exclude=["__pycache__/"])
        assert not any("__pycache__" in f for f in files)


class TestFileExtensionEdgeCases:
    def test_jsx_included_as_javascript(self, tmp_path):
        (tmp_path / "Component.jsx").write_text("export default () => <div/>;")
        files = collect_files([str(tmp_path)], languages=["javascript"])
        assert any("Component.jsx" in f for f in files)

    def test_tsx_included_as_javascript(self, tmp_path):
        (tmp_path / "Component.tsx").write_text("const App: FC = () => <div/>;")
        files = collect_files([str(tmp_path)], languages=["javascript"])
        assert any("Component.tsx" in f for f in files)

    def test_mjs_included_as_javascript(self, tmp_path):
        (tmp_path / "module.mjs").write_text("export const x = 1;")
        files = collect_files([str(tmp_path)], languages=["javascript"])
        assert any("module.mjs" in f for f in files)

    def test_cjs_included_as_javascript(self, tmp_path):
        (tmp_path / "module.cjs").write_text("module.exports = {};")
        files = collect_files([str(tmp_path)], languages=["javascript"])
        assert any("module.cjs" in f for f in files)

    def test_non_code_files_excluded(self, tmp_path):
        """Archivos que no son codigo no deben incluirse."""
        for name in ["readme.md", "image.png", "data.csv", "config.ini"]:
            (tmp_path / name).write_text("content")
        files = collect_files(
            [str(tmp_path)], languages=["python", "javascript"]
        )
        for f in files:
            assert not f.endswith((".md", ".png", ".csv", ".ini")), (
                f"Non-code file included: {f}"
            )

    def test_unknown_language_collects_nothing(self, tmp_path):
        """Un lenguaje desconocido no tiene extensiones y no recolecta nada."""
        (tmp_path / "app.py").write_text("x = 1")
        files = collect_files([str(tmp_path)], languages=["rust"])
        # Solo archivos de dependencias deben incluirse
        code_files = [f for f in files if f.endswith(".py")]
        assert code_files == []


class TestDependencyFilesAlwaysIncluded:
    """Archivos de dependencias deben incluirse sin importar el filtro de lenguaje."""

    @pytest.mark.parametrize("dep_file", sorted(DEPENDENCY_FILES))
    def test_dependency_file_included(self, tmp_path, dep_file):
        (tmp_path / dep_file).write_text("# dep file content")
        files = collect_files([str(tmp_path)], languages=["python"])
        assert any(dep_file in f for f in files), (
            f"Dependency file '{dep_file}' should always be included"
        )

    def test_dependency_files_in_subdirectory(self, tmp_path):
        sub = tmp_path / "backend"
        sub.mkdir()
        (sub / "requirements.txt").write_text("flask==3.0")
        files = collect_files([str(tmp_path)], languages=["python"])
        assert any("requirements.txt" in f for f in files)


class TestEmptyAndEdgeCaseInputs:
    def test_empty_paths_list(self):
        files = collect_files([], languages=["python"])
        assert files == []

    def test_file_with_no_extension(self, tmp_path):
        (tmp_path / "Makefile").write_text("all: build")
        files = collect_files([str(tmp_path)], languages=["python"])
        # No extension = not matched by language filter, not a dep file
        assert not any("Makefile" in f for f in files)

    def test_hidden_files_included_if_matching(self, tmp_path):
        """Archivos ocultos (.file) con extension valida se incluyen."""
        (tmp_path / ".hidden.py").write_text("# hidden python file")
        files = collect_files([str(tmp_path)], languages=["python"])
        assert any(".hidden.py" in f for f in files)

    def test_symlink_file(self, tmp_path):
        """Symlinks a archivos se deben manejar sin error."""
        real = tmp_path / "real.py"
        real.write_text("x = 1")
        link = tmp_path / "link.py"
        try:
            link.symlink_to(real)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")
        files = collect_files([str(tmp_path)], languages=["python"])
        # Both real and symlink should be collected (they resolve to same path)
        assert any("real.py" in f for f in files)

    def test_multiple_paths_overlap(self, tmp_path):
        """Cuando se pasan paths solapados, no hay duplicados."""
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "app.py").write_text("x = 1")
        files = collect_files(
            [str(tmp_path), str(sub)], languages=["python"]
        )
        app_files = [f for f in files if "app.py" in f]
        assert len(app_files) == 1, (
            f"Expected 1 app.py, got {len(app_files)} due to missing dedup: {app_files}"
        )

    def test_binary_file_not_collected(self, tmp_path):
        """Archivos .pyc (binarios) no tienen extension .py y no se incluyen."""
        (tmp_path / "module.pyc").write_bytes(b"\x00\x01\x02\x03")
        files = collect_files([str(tmp_path)], languages=["python"])
        assert not any("module.pyc" in f for f in files)

    def test_default_languages_include_all(self, tmp_path):
        """Sin filtro de lenguaje, python y javascript se incluyen."""
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "app.js").write_text("const x = 1;")
        files = collect_files([str(tmp_path)])
        assert any("app.py" in f for f in files)
        assert any("app.js" in f for f in files)


class TestShouldIncludeFile:
    """Tests directos para _should_include_file."""

    def test_python_file_included(self, tmp_path):
        from pathlib import Path
        f = tmp_path / "app.py"
        f.write_text("")
        assert _should_include_file(f, {".py"}, []) is True

    def test_non_matching_extension_excluded(self, tmp_path):
        from pathlib import Path
        f = tmp_path / "readme.md"
        f.write_text("")
        assert _should_include_file(f, {".py"}, []) is False

    def test_dependency_file_always_included(self, tmp_path):
        from pathlib import Path
        f = tmp_path / "requirements.txt"
        f.write_text("")
        assert _should_include_file(f, {".py"}, []) is True

    def test_excluded_pattern_blocks(self, tmp_path):
        from pathlib import Path
        venv = tmp_path / ".venv"
        venv.mkdir()
        f = venv / "site.py"
        f.write_text("")
        assert _should_include_file(f, {".py"}, [".venv"]) is False
