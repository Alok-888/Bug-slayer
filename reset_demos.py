#!/usr/bin/env python3
"""
Helper script to reset demo repositories to their original broken states
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

# 2. Reset demo_undocumented_repo (remove README.md so it's zero-doc)
undoc_readme = Path("demo_undocumented_repo/README.md")
if undoc_readme.exists():
    undoc_readme.unlink()

undoc_env = Path("demo_undocumented_repo/.env")
if undoc_env.exists():
    undoc_env.unlink()

print("✅ Demo environments reset to their broken states!")
print("👉 You can now run: python3 run_bugslayer.py demo_broken_repo")
