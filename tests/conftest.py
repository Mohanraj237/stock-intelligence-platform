"""Shared fixtures for the test suite."""
from __future__ import annotations
import sys
import pytest
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.main import app as fastapi_app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Session-scoped FastAPI TestClient — starts the app once for all tests."""
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def fresh_client() -> TestClient:
    """Request-scoped client — use when a test mutates shared state (e.g. watchlist)."""
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c
