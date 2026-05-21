"""Shared pytest fixtures for the analysis test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Path to the tests/fixtures directory containing tiny CSVs."""
    return Path(__file__).parent / "fixtures"
