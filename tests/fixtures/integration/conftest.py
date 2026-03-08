"""Prevent pytest from collecting fixture files as tests."""

collect_ignore_glob = ["**/test_*.py", "**/*.test.js"]
