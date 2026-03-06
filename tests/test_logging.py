"""Tests para logging setup."""

import logging

from vigil.logging.setup import setup_logging


class TestLoggingSetup:
    def test_verbose_sets_debug_level(self):
        setup_logging(verbose=True)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_non_verbose_sets_warning_level(self):
        setup_logging(verbose=False)
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_setup_idempotent(self):
        """Llamar setup_logging multiples veces no crashea."""
        setup_logging(verbose=False)
        setup_logging(verbose=True)
        setup_logging(verbose=False)
        root = logging.getLogger()
        assert root.level == logging.WARNING
