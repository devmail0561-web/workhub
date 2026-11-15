import logging

import pytest

from workhub.interfaces.rest.logging import configure_logging, get_logger


def test_configure_logging_from_argument() -> None:
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    configure_logging("INFO")


def test_configure_logging_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging()
    assert logging.getLogger().level == logging.WARNING
    configure_logging("INFO")


def test_configure_logging_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_invalid_level_falls_back_to_info() -> None:
    configure_logging("BOGUS")
    assert logging.getLogger().level == logging.INFO
    configure_logging("INFO")


def test_get_logger_returns_a_logger() -> None:
    assert get_logger("workhub.test") is not None
