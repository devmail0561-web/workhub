"""Configuration commune aux tests."""

from __future__ import annotations

import os

os.environ.setdefault("WORKHUB_ENV", "test")
os.environ.setdefault("WORKHUB_SECRET_KEY", "test-secret-key-0123456789abcdef")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://workhub_app:test@localhost:5432/workhub_test",
)
