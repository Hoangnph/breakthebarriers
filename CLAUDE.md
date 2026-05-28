# Agent Skill Creator — Project Guide

## Tổng quan

Dự án giáo dục AI gồm 2 ứng dụng:

| App | Mô tả |
|-----|-------|
| `apps/break_the_barriers` | Web app upload PDF → Extract HTML → AI Translation (Gemini) → Compile output |
| `apps/Agentic_Design_Patterns_Reader` | Web app đọc file Agentic Design Patterns PDF |

---

## Khởi động Dev Environment

**Dùng skill**: `/start-dev` để xem hướng dẫn chi tiết.

Tóm tắt nhanh:
```bash
# Terminal 1 — Backend (port 8000)
cd apps/break_the_barriers/backend
../.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend (port 8001)
cd apps/break_the_barriers
python3 server.py
```

URLs: Frontend `http://localhost:8001` | API `http://localhost:8000` | Swagger `http://localhost:8000/docs`

---

## Cấu trúc dự án

```
Agent_Skill_Creator/
├── apps/
│   ├── break_the_barriers/          # App chính
│   │   ├── backend/                 # FastAPI backend
│   │   │   ├── app/
│   │   │   │   ├── main.py          # Tất cả API endpoints (~34KB)
│   │   │   │   ├── models.py        # Pydantic request/response models
│   │   │   │   ├── models_db.py     # SQLAlchemy ORM models
│   │   │   │   ├── database.py      # DB connection + session
│   │   │   │   ├── config.py        # Đọc .env
│   │   │   │   └── services/
│   │   │   │       ├── extractor.py # PDF → HTML extraction
│   │   │   │       ├── translator.py # Gemini AI translation
│   │   │   │       └── compiler.py  # Compile translated output
│   │   │   ├── tests/
│   │   │   │   ├── conftest.py      # pytest fixtures (SQLite in-memory DB)
│   │   │   │   ├── test_api.py      # API endpoint tests
│   │   │   │   └── test_services.py # Service unit tests
│   │   │   ├── .venv/               # Python virtual environment
│   │   │   ├── data/                # Runtime data (raw_pdf, extracted_html, pages)
│   │   │   └── requirements.txt
│   │   ├── index.html               # Main frontend entry
│   │   ├── reader.html              # Document reader view
│   │   ├── preview.html             # Preview view
│   │   ├── app.js / style.css       # Main app JS/CSS
│   │   ├── reader_app.js            # Reader-specific JS
│   │   ├── preview_app.js           # Preview-specific JS
│   │   ├── server.py                # Frontend static server (port 8001)
│   │   └── .env                     # API keys + DB URL (KHÔNG sửa bằng Claude)
│   └── Agentic_Design_Patterns_Reader/
│       ├── index.html
│       ├── data/                    # HTML pages từ PDF
│       └── server.py               # Static server
├── assets/
│   └── Agentic_Design_Patterns.pdf  # Source PDF
└── outputs/
    ├── process_pdf.py               # Script xử lý PDF → HTML
    └── Agentic_Design_Patterns/     # Output của process_pdf.py
```

---

## Database (PostgreSQL)

**Connection**: `postgresql://postgres:postgres@localhost:5432/break_the_barriers`

| Bảng | Mô tả |
|------|-------|
| `documents` | Metadata tài liệu (id, filename, status, total_pages) |
| `pages` | Từng trang (original_html, translated_html, status) |
| `translations` | Từng span dịch (span_id, original_text, translated_text) |

**Document status flow**: `raw` → `extracted` → `translated` → `compiled`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.110+, Python 3, Uvicorn |
| ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL 15 (Homebrew) |
| AI Translation | Google Gemini (`google-generativeai`, đang migrate sang `google.genai`) |
| HTML Parsing | BeautifulSoup4 |
| Frontend | Vanilla HTML/JS/CSS |
| Testing | pytest, pytest-asyncio, httpx |

---

## Chạy Tests

**Dùng skill**: `/run-tests`

```bash
cd apps/break_the_barriers/backend
../.venv/bin/pytest tests/ -v
```

Tests dùng SQLite in-memory — không ảnh hưởng DB production.

---

## Lưu ý quan trọng

- **`.env` được bảo vệ** — Claude không được tự sửa file này
- **`GEMINI_API_KEY`** trong `.env` là key thật, đang hoạt động
- **`main.py`** rất lớn (~34KB) — khi thêm endpoint mới nên dùng `/api-reviewer` để review
- **Background tasks** trong FastAPI dùng `get_background_db()` riêng (không dùng `Depends(get_db)`)
- **Frontend và backend** chạy trên 2 port khác nhau, CORS đã enable `allow_origins=["*"]`
- **PDF processing** dùng `pdftohtml` tại `/opt/homebrew/bin/pdftohtml`
