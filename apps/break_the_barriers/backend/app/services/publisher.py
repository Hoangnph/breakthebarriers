import os
import re

from fastapi import UploadFile

from backend.app.core import DATA_DIR

SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$')
MAX_COVER_SIZE = 5 * 1024 * 1024  # 5 MB
COVERS_DIR = os.path.join(DATA_DIR, "covers")


def validate_slug(slug: str) -> bool:
    """True if slug is lowercase a-z0-9-, length 3-80, no leading/trailing dash."""
    return bool(SLUG_RE.match(slug))


def slug_from_filename(filename: str) -> str:
    """Suggest a slug from a PDF/EPUB filename."""
    name = os.path.splitext(filename)[0]
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if len(slug) < 3:
        slug = (slug + '-book').strip('-')
    return slug[:80].strip('-')


async def save_cover_file(file: UploadFile, doc_id: str, slug: str) -> str:
    """Save uploaded cover image to DATA_DIR/covers, return the stored filename.

    Raises ValueError if the file is too large or not an image.
    """
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise ValueError("Cover must be an image")
    content = await file.read()
    if len(content) > MAX_COVER_SIZE:
        raise ValueError("Cover file too large (max 5MB)")
    ext = os.path.splitext(file.filename or "")[-1].lower() or ".jpg"
    filename = f"{doc_id}_{slug}{ext}"
    os.makedirs(COVERS_DIR, exist_ok=True)
    with open(os.path.join(COVERS_DIR, filename), "wb") as f:
        f.write(content)
    return filename
