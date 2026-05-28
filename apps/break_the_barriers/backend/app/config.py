import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/break_the_barriers"
)

GEMINI_PRICE_PER_1M_TOKENS = float(os.getenv("GEMINI_PRICE_PER_1M_TOKENS", "0.075"))
