from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from backend.app.config import DATABASE_URL

# Create the SQLAlchemy engine for PostgreSQL
# pool_pre_ping ensures the pool checks connections before using them
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

# Set up local session maker
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Declarative base class for models
Base = declarative_base()

# Dependency generator to inject DB sessions into FastAPI endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
