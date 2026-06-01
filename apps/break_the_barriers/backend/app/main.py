import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.database import engine, Base, get_db, SessionLocal
from backend.app.models_db import DBDocument
from backend.app.routers import documents, extraction, translation, compilation, volume, jobs
from backend.app.routers import auth, books, glossary
from backend.app.core import DATA_DIR

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Smart Documentations API",
    description="API-First Backend for Digitizing and High-Fidelity Translation of PDF books",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_covers_dir = os.path.join(DATA_DIR, "covers")
os.makedirs(_covers_dir, exist_ok=True)
app.mount("/covers", StaticFiles(directory=_covers_dir), name="covers")

app.include_router(documents.router)
app.include_router(extraction.router)
app.include_router(translation.router)
app.include_router(compilation.router)
app.include_router(volume.router)
app.include_router(jobs.router)
app.include_router(auth.router)
app.include_router(books.router)
app.include_router(glossary.router)


@app.on_event("startup")
def startup_populate():
    import sys
    if "pytest" in sys.modules:
        return
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        if not db.query(DBDocument).filter(DBDocument.id == "clean_code").first():
            db.add(DBDocument(id="clean_code", filename="Clean_Code.pdf", total_pages=10, status="raw"))
            db.commit()
    finally:
        db.close()
