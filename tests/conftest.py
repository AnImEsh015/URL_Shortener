"""Pytest configuration, fixtures, test database setup, and fakeredis mocking.

Uses:
- PostgreSQL test database configured by TEST_DATABASE_URL
- fakeredis for synchronous in-memory Redis emulation
- Celery task_always_eager for synchronous execution of analytics tasks
- TestClient with overridden get_db dependency
"""

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.main import create_app
from app.services.cache import set_redis_client
from app.worker import celery_app

# Create test engine using TEST_DATABASE_URL
test_engine = create_engine(
    settings.TEST_DATABASE_URL,
    pool_pre_ping=True,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Creates database schema once for the test session and tears down afterwards."""
    import app.db
    app.db.SessionLocal = TestingSessionLocal
    app.db.engine = test_engine
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def setup_fakeredis_and_celery():
    """Initializes in-memory fakeredis and forces synchronous Celery execution."""
    server = fakeredis.FakeServer()
    fake_r = fakeredis.FakeRedis(server=server, decode_responses=True)
    set_redis_client(fake_r)

    # Configure Celery for immediate local execution in tests
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
    yield fake_r
    fake_r.flushall()


@pytest.fixture
def db():
    """Yields a database session per test and truncates tables after each test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Clean tables between test runs for complete test isolation
        with test_engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE clicks, links, users RESTART IDENTITY CASCADE;"))
            conn.commit()


@pytest.fixture
def client(db):
    """Creates a FastAPI test client with database dependency override."""
    app = create_app()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client):
    """Helper fixture that registers and logs in a test user, returning auth Bearer headers."""
    def _create_user(email="user@test.com", password="password123"):
        client.post("/auth/register", json={"email": email, "password": password})
        login_resp = client.post(
            "/auth/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = login_resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _create_user
