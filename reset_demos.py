#!/usr/bin/env python3
"""
Helper script to reset demo repositories to their original broken or undocumented states
so you can test Bug Slayer or show live demos repeatedly.
"""

from pathlib import Path

# 1. Reset demo_broken_repo
broken_readme = Path("demo_broken_repo/README.md")
broken_readme.write_text("""# Demo App

Welcome to our project.

## How to Run

Follow these instructions to boot the project:

```bash
python3 run_app.py
```
""", encoding="utf-8")

# Clean leftover artifacts
for leftover in ["demo_broken_repo/setup.sh", "demo_broken_repo/fix-readme.patch"]:
    p = Path(leftover)
    if p.exists():
        p.unlink()

# 2. Reset demo_undocumented_repo (remove README.md so it's zero-doc)
undoc_readme = Path("demo_undocumented_repo/README.md")
if undoc_readme.exists():
    undoc_readme.unlink()

undoc_env = Path("demo_undocumented_repo/.env")
if undoc_env.exists():
    undoc_env.unlink()

undoc_setup = Path("demo_undocumented_repo/setup.sh")
if undoc_setup.exists():
    undoc_setup.unlink()

# 3. Setup / Reset demo_large_repo (large multi-module repo with zero docs)
large_base = Path("demo_large_repo")
large_base.mkdir(exist_ok=True)

# Generate multi-module nested files (10 modules x 10 files = 100+ files)
for i in range(1, 11):
    mod_dir = large_base / f"app/module_{i}"
    mod_dir.mkdir(parents=True, exist_ok=True)
    for j in range(1, 11):
        f = mod_dir / f"service_{j}.py"
        if not f.exists():
            f.write_text(f"# Service {i}_{j}\ndef compute_{i}_{j}():\n    return {i} * {j}\n")

# Main FastAPI entrypoint
(large_base / "main.py").write_text("""import os
import sys

# Minimal FastAPI-compatible mock runner for standalone testing
port = int(os.environ.get("PORT", 8000))
print(f"🚀 Starting FastAPI application server on http://localhost:{port}")
print("📚 Interactive OpenAPI Docs available at http://localhost:8000/docs")
print("✨ Server boot verified!")
""".strip() + "\n")

# requirements.txt
(large_base / "requirements.txt").write_text("""fastapi>=0.110.0
uvicorn>=0.28.0
pydantic>=2.6.0
""".strip() + "\n")

# .env.example
(large_base / ".env.example").write_text("""# Server Configuration
PORT=8000
HOST=0.0.0.0
DEBUG=True

# Database & Cache
DATABASE_URL=postgresql://user:password@localhost:5432/production_db
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=dev_secret_key_change_in_production_jwt
LOG_LEVEL=INFO
""".strip() + "\n")

# docker-compose.yml
(large_base / "docker-compose.yml").write_text("""version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PORT=8000
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/app
    depends_on:
      - db
      - redis

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_PASSWORD: postgres

  redis:
    image: redis:7-alpine
""".strip() + "\n")

# Dockerfile
(large_base / "Dockerfile").write_text("""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
""".strip() + "\n")

# Clean generated files in demo_large_repo so it's zero-doc
for artifact in ["README.md", ".env", "setup.sh", "fix-readme.patch"]:
    p = large_base / artifact
    if p.exists():
        p.unlink()

print("✅ Demo environments reset to their test states!")
print("👉 Available test demos:")
print("   1. Broken README healing:  python3 run_bugslayer.py demo_broken_repo --local")
print("   2. Zero-docs synthesis:    python3 run_bugslayer.py demo_undocumented_repo --local")
print("   3. Large zero-docs repo:   python3 run_bugslayer.py demo_large_repo --local")
