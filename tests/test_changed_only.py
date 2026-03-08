"""Tests para _get_changed_files() y --changed-only flag."""

from unittest.mock import patch, MagicMock

from vigil.cli import _get_changed_files


class TestGetChangedFiles:
    """Tests unitarios para _get_changed_files."""

    def test_parses_porcelain_z_output(self):
        """Parsea correctamente output de git status --porcelain -u -z."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        # Formato: "XY filename\0" separados por NUL
        mock_result.stdout = " M src/app.py\0?? new_file.py\0"

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert "src/app.py" in files
        assert "new_file.py" in files

    def test_handles_renames(self):
        """Parsea correctamente renames (R status)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        # Rename: "R  old_name\0new_name\0"
        mock_result.stdout = "R  old.py\0new.py\0"

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert "new.py" in files
        assert "old.py" not in files

    def test_handles_filenames_with_spaces(self):
        """Maneja correctamente filenames con espacios."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M src/my file.py\0?? path with spaces/app.py\0"

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert "src/my file.py" in files
        assert "path with spaces/app.py" in files

    def test_excludes_deleted_files(self):
        """No incluye archivos eliminados."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " D deleted.py\0 M modified.py\0"

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert "deleted.py" not in files
        assert "modified.py" in files

    def test_includes_staged_and_unstaged(self):
        """Incluye archivos staged (A), modified (M), y untracked (??)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "A  staged.py\0 M unstaged.py\0?? untracked.py\0"

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert "staged.py" in files
        assert "unstaged.py" in files
        assert "untracked.py" in files

    def test_empty_output(self):
        """Sin cambios retorna lista vacia."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert files == []

    def test_git_not_found(self):
        """Sin git instalado retorna lista vacia."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            files = _get_changed_files()

        assert files == []

    def test_git_timeout(self):
        """Timeout retorna lista vacia."""
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)):
            files = _get_changed_files()

        assert files == []

    def test_not_a_git_repo(self):
        """En directorio sin git retorna lista vacia."""
        mock_result = MagicMock()
        mock_result.returncode = 128  # fatal: not a git repository

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert files == []

    def test_mixed_status_codes(self):
        """Maneja mixed status codes correctamente."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        # MM = staged + unstaged modification
        mock_result.stdout = "MM both.py\0AM added_modified.py\0"

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert "both.py" in files
        assert "added_modified.py" in files

    def test_excludes_staged_deletion(self):
        """Excluye archivos con staged deletion (D en primer campo)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "D  staged_delete.py\0 M ok.py\0"

        with patch("subprocess.run", return_value=mock_result):
            files = _get_changed_files()

        assert "staged_delete.py" not in files
        assert "ok.py" in files
