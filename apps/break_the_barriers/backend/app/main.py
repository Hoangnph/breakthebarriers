import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.database import engine, Base, get_db, SessionLocal
from backend.app.models_db import DBDocument
from backend.app.routers import documents, extraction, translation, compilation, volume, jobs
from backend.app.routers import auth

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

app.include_router(documents.router)
app.include_router(extraction.router)
app.include_router(translation.router)
app.include_router(compilation.router)
app.include_router(volume.router)
app.include_router(jobs.router)
app.include_router(auth.router)


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
