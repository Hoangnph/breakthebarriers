import sys
import inspect
import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from backend.app.config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_background_db():
    """DB session for background tasks — test-aware."""
    from backend.app.main import app

    if get_db in app.dependency_overrides:
        override = app.dependency_overrides[get_db]
        globals_dict = getattr(override, "__globals__", {})
        TestingSessionLocal = globals_dict.get("TestingSessionLocal")
        if TestingSessionLocal is not None:
            return TestingSessionLocal()
        if inspect.isgeneratorfunction(override):
            try:
                return next(override())
            except StopIteration:
                pass
        else:
            return override()

    if "pytest" in sys.modules:
        for name, mod in list(sys.modules.items()):
            if name.endswith("conftest") and hasattr(mod, "TestingSessionLocal"):
                try:
                    return getattr(mod, "TestingSessionLocal")()
                except Exception:
                    pass

    return SessionLocal()
