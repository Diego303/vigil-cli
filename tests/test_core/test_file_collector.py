"""Tests para file_collector."""

from vigil.core.file_collector import collect_files


class TestCollectFiles:
    def test_collect_python_files(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "readme.md").write_text("# readme")
        files = collect_files([str(tmp_path)], languages=["python"])
        assert any("app.py" in f for f in files)
        assert not any("readme.md" in f for f in files)

    def test_collect_javascript_files(self, tmp_path):
        (tmp_path / "app.js").write_text("const x = 1;")
        (tmp_path / "app.ts").write_text("const x: number = 1;")
        (tmp_path / "app.py").write_text("x = 1")
        files = collect_files([str(tmp_path)], languages=["javascript"])
        assert any("app.js" in f for f in files)
        assert any("app.ts" in f for f in files)
        assert not any("app.py" in f for f in files)

    def test_collect_both_languages(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "app.js").write_text("const x = 1;")
        files = collect_files(
            [str(tmp_path)], languages=["python", "javascript"]
        )
        assert any("app.py" in f for f in files)
        assert any("app.js" in f for f in files)

    def test_exclude_patterns(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        venv_dir = tmp_path / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "site.py").write_text("# venv file")

        files = collect_files(
            [str(tmp_path)],
            exclude=[".venv/"],
            languages=["python"],
        )
        assert any("app.py" in f for f in files)
        assert not any(".venv" in f for f in files)

    def test_always_includes_dependency_files(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==3.0.0")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        files = collect_files([str(tmp_path)], languages=["python"])
        assert any("requirements.txt" in f for f in files)
        assert any("package.json" in f for f in files)

    def test_single_file_path(self, tmp_path):
        target = tmp_path / "specific.py"
        target.write_text("x = 1")
        files = collect_files([str(target)], languages=["python"])
        assert len(files) == 1
        assert "specific.py" in files[0]

    def test_nonexistent_path(self, tmp_path):
        files = collect_files(
            [str(tmp_path / "does_not_exist")], languages=["python"]
        )
        assert files == []

    def test_empty_directory(self, tmp_path):
        files = collect_files([str(tmp_path)], languages=["python"])
        assert files == []

    def test_nested_directories(self, tmp_path):
        deep = tmp_path / "src" / "app" / "models"
        deep.mkdir(parents=True)
        (deep / "user.py").write_text("class User: pass")
        files = collect_files([str(tmp_path)], languages=["python"])
        assert any("user.py" in f for f in files)

    def test_deduplication(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        files = collect_files(
            [str(tmp_path), str(tmp_path)], languages=["python"]
        )
        py_files = [f for f in files if "app.py" in f]
        assert len(py_files) == 1

    def test_pyproject_toml_included(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")
        files = collect_files([str(tmp_path)], languages=["python"])
        assert any("pyproject.toml" in f for f in files)
