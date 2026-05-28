---
name: start-dev
description: Start the break_the_barriers dev environment (backend FastAPI + frontend static server)
disable-model-invocation: true
---

# Start Dev Environment

Khởi động 2 server cho dự án break_the_barriers. Mở **2 terminal riêng** và chạy:

## Terminal 1 — Backend FastAPI (port 8000)

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

## Terminal 2 — Frontend Static Server (port 8001)

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers
python3 server.py
```

## URLs

| Service | URL |
|---------|-----|
| Frontend App | http://localhost:8001 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (Redoc) | http://localhost:8000/redoc |

## Prerequisites

- PostgreSQL đang chạy: `brew services list | grep postgres`
- `.env` file có `GEMINI_API_KEY` và `DATABASE_URL`
- DB `break_the_barriers` tồn tại: `psql -U postgres -c "\l" | grep break`
