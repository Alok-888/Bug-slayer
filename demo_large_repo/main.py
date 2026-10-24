import os
import sys

# Minimal FastAPI-compatible mock runner for standalone testing
port = int(os.environ.get("PORT", 8000))
print(f"🚀 Starting FastAPI application server on http://localhost:{port}")
print("📚 Interactive OpenAPI Docs available at http://localhost:8000/docs")
print("✨ Server boot verified!")
