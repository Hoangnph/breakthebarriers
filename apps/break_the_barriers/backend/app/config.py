import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# PostgreSQL Connection String config
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/break_the_barriers"
)
