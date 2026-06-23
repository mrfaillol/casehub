"""
CaseHub Test Configuration
Shared fixtures for all test modules.
"""
import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables BEFORE importing app modules
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only-32chars!"
os.environ["DATABASE_URL"] = "sqlite:///test_casehub.db"
os.environ["ENCRYPTION_KEY"] = "dGVzdC1lbmNyeXB0aW9uLWtleS1mb3ItdGVzdHMxMjM="  # base64, 44 chars
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ORG_NAME"] = "TestOrg"

from models.base import Base

# In-memory SQLite for tests. check_same_thread=False + StaticPool lets the
# same in-memory DB be reused across threads (FastAPI TestClient runs handlers
# in a worker thread distinct from the main test thread; without these settings
# SQLite raises ProgrammingError "objects created in a thread can only be used
# in that same thread" on HTTP test cases).
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)
TestSession = sessionmaker(bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def setup_database():
    """Create all tables before each test, drop after."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    Base.metadata.create_all(bind=TEST_ENGINE)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=TEST_ENGINE)
        if not loop.is_closed():
            loop.close()
        asyncio.set_event_loop(None)


@pytest.fixture
def db():
    """Provide a transactional database session for tests."""
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = MagicMock()
    request.cookies = {}
    request.query_params = {}
    request.headers = {}
    request.app = MagicMock()
    request.app.version = "2.0.0-test"
    return request
