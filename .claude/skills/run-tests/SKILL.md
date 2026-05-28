---
name: run-tests
description: Run pytest for break_the_barriers backend — dùng đúng venv và working directory
disable-model-invocation: true
---

# Run Tests

## Chạy toàn bộ test suite

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend
../.venv/bin/pytest tests/ -v
```

## Chạy test nhanh (dừng khi fail đầu tiên)

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend
../.venv/bin/pytest tests/ -x -q
```

## Chạy 1 file test cụ thể

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend
../.venv/bin/pytest tests/test_api.py -v
../.venv/bin/pytest tests/test_services.py -v
```

## Chạy 1 test case cụ thể

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend
../.venv/bin/pytest tests/test_api.py::test_function_name -v
```

## Lưu ý

- Phải chạy từ thư mục `backend/` để Python resolve đúng package `backend.app.*`
- DB test dùng SQLite in-memory (xem `conftest.py`), không ảnh hưởng DB production
