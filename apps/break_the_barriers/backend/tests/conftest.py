import os
import shutil
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to sys.path so we can import backend app
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.models_db import DBDocument

from sqlalchemy.pool import StaticPool

# SQLite in-memory database with StaticPool to share the same connection/data across sessions
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine
)

@pytest.fixture(autouse=True)
def setup_database():
    # Create all tables in the temporary database
    Base.metadata.create_all(bind=test_engine)
    
    # Pre-populate default 'clean_code' document to maintain TDD test compatibilities
    db = TestingSessionLocal()
    try:
        default_doc = DBDocument(
            id="clean_code",
            filename="Clean_Code.pdf",
            total_pages=10,
            status="raw"
        )
        db.add(default_doc)
        db.commit()
    finally:
        db.close()
        
    yield
    
    # Tear down tables after the test finishes to avoid cascading side-effects
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def temp_data_dir(tmp_path):
    """
    Creates a temporary mock data directory structure for testing.
    """
    data_dir = tmp_path / "data"
    os.makedirs(data_dir / "raw_pdf", exist_ok=True)
    os.makedirs(data_dir / "extracted_html", exist_ok=True)
    os.makedirs(data_dir / "locale" / "en", exist_ok=True)
    os.makedirs(data_dir / "locale" / "vi", exist_ok=True)
    os.makedirs(data_dir / "pages", exist_ok=True)
    
    # Write a small sample raw pdf mock file
    with open(data_dir / "raw_pdf" / "mock_book.pdf", "w") as f:
        f.write("%PDF-1.5 mock pdf content")
        
    return data_dir

@pytest.fixture
def client(db_session):
    """
    Provides a FastAPI test client with mocked DB session.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    # Override FastAPI DB dependency to use the isolated TestingSessionLocal
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    # Clear overrides after the test finishes
    app.dependency_overrides.clear()
