"""
Bug Slayer - Codebase Inspector
Scans any repository to discover language, frameworks, dependencies,
environment variables, and entry points.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, Any, List


class CodebaseInspector:
    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir).resolve()

    def inspect(self) -> Dict[str, Any]:
        """Performs a comprehensive scan of the repository."""
        facts = {
            "path": str(self.target_dir),
            "languages": [],
            "package_manager": None,
            "manifest_files": [],
            "scripts": {},
            "env_variables": [],
            "entry_points": [],
            "has_readme": False,
            "readme_path": None,
            "readme_commands": []
        }

        if not self.target_dir.exists():
            return facts

        # 1. Check for README
        for name in ["README.md", "readme.md", "README", "readme.txt"]:
            readme_file = self.target_dir / name
            if readme_file.exists():
                facts["has_readme"] = True
                facts["readme_path"] = str(readme_file)
                facts["readme_commands"] = self._extract_readme_commands(readme_file)
                break

        # 2. Detect Ecosystems & Manifests
        self._detect_manifests(facts)

        # 3. Detect Entry Points
        self._detect_entry_points(facts)

        # 4. Harvest Environment Variables
        facts["env_variables"] = self._harvest_env_variables()

        return facts

    def _detect_manifests(self, facts: Dict[str, Any]):
        """Detects package managers, frameworks, and scripts."""
        # Node.js
        pkg_json = self.target_dir / "package.json"
        if pkg_json.exists():
            facts["languages"].append("JavaScript/TypeScript")
            facts["manifest_files"].append("package.json")
            if (self.target_dir / "pnpm-lock.yaml").exists():
                facts["package_manager"] = "pnpm"
            elif (self.target_dir / "yarn.lock").exists():
                facts["package_manager"] = "yarn"
            elif (self.target_dir / "bun.lockb").exists():
                facts["package_manager"] = "bun"
            else:
                facts["package_manager"] = "npm"

            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    facts["scripts"] = data.get("scripts", {})
                    if "main" in data:
                        facts["entry_points"].append(data["main"])
            except Exception:
                pass

        # Python
        pyproject = self.target_dir / "pyproject.toml"
        req_txt = self.target_dir / "requirements.txt"
        pipfile = self.target_dir / "Pipfile"
        setup_py = self.target_dir / "setup.py"

        if pyproject.exists() or req_txt.exists() or pipfile.exists() or setup_py.exists():
            facts["languages"].append("Python")
            if pyproject.exists():
                facts["manifest_files"].append("pyproject.toml")
                facts["package_manager"] = "poetry" if "poetry" in pyproject.read_text(errors="ignore") else "pip"
            if req_txt.exists():
                facts["manifest_files"].append("requirements.txt")
                facts["package_manager"] = facts["package_manager"] or "pip"
            if pipfile.exists():
                facts["manifest_files"].append("Pipfile")
                facts["package_manager"] = "pipenv"

        # Go
        if (self.target_dir / "go.mod").exists():
            facts["languages"].append("Go")
            facts["manifest_files"].append("go.mod")
            facts["package_manager"] = "go"

        # Rust
        if (self.target_dir / "Cargo.toml").exists():
            facts["languages"].append("Rust")
            facts["manifest_files"].append("Cargo.toml")
            facts["package_manager"] = "cargo"

    def _detect_entry_points(self, facts: Dict[str, Any]):
        """Hunts for standard entry points like main.py, app.py, index.js, etc."""
        common_candidates = [
            "main.py", "app.py", "server.py", "index.py", "run.py",
            "src/main.py", "src/app.py",
            "index.js", "server.js", "app.js", "src/index.js", "src/server.js",
            "src/index.ts", "src/main.ts", "src/App.tsx",
            "main.go", "src/main.rs"
        ]
        for candidate in common_candidates:
            if (self.target_dir / candidate).exists():
                if candidate not in facts["entry_points"]:
                    facts["entry_points"].append(candidate)

    def _harvest_env_variables(self) -> List[str]:
        """Grep source files for required environment variables."""
        env_vars = set()

        # Check .env.example / .env.sample
        for env_sample in [".env.example", ".env.sample", "sample.env"]:
            sample_file = self.target_dir / env_sample
            if sample_file.exists():
                for line in sample_file.read_text(errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        var_name = line.split("=")[0].strip()
                        if var_name:
                            env_vars.add(var_name)

        # Static regex across source code (Python & JS/TS)
        py_pattern = re.compile(r'(?:os\.environ\.get|os\.getenv)\s*\(\s*["\']([A-Z0-9_]+)["\']')
        js_pattern = re.compile(r'process\.env\.([A-Z0-9_]+)')

        for root, dirs, files in os.walk(self.target_dir):
            # Ignore heavy dirs
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "venv", "__pycache__", ".next", "dist", "build"}]
            for file in files:
                if file.endswith((".py", ".js", ".ts", ".jsx", ".tsx")):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text(errors="ignore")
                        for match in py_pattern.findall(content):
                            env_vars.add(match)
                        for match in js_pattern.findall(content):
                            env_vars.add(match)
                    except Exception:
                        pass

        return sorted(list(env_vars))

    def _extract_readme_commands(self, readme_path: Path) -> List[Dict[str, Any]]:
        """Extracts bash/sh command blocks from a README.md file, filtering out text prose."""
        commands = []
        KNOWN_COMMAND_PREFIXES = {
            "git", "cd", "cp", "mv", "rm", "mkdir", "export", "source", "chmod",
            "npm", "npx", "yarn", "pnpm", "bun", "node",
            "pip", "pip3", "python", "python3", "poetry", "pytest", "pytest-3", "uvicorn", "flask",
            "cargo", "rustc", "go", "make", "docker", "docker-compose",
            "curl", "wget", "cat", "echo", "sed", "awk", "grep", "find", "brew", "apt", "sudo"
        }

        try:
            content = readme_path.read_text(errors="ignore")
            # Only match explicit shell/terminal code blocks
            pattern = re.compile(r'```(?:bash|sh|shell|zsh|console)?\n(.*?)```', re.DOTALL | re.IGNORECASE)
            for block in pattern.findall(content):
                for line in block.splitlines():
                    cleaned = line.strip()
                    if not cleaned or cleaned.startswith("#"):
                        continue

                    # Strip leading '$ ' prompt symbol if present
                    is_prompt = False
                    if cleaned.startswith("$ "):
                        cleaned = cleaned[2:].strip()
                        is_prompt = True

                    first_token = cleaned.split()[0].lower() if cleaned.split() else ""
                    # Remove flags or ./
                    if first_token.startswith("./"):
                        commands.append({"raw": line, "command": cleaned})
                    elif is_prompt or first_token in KNOWN_COMMAND_PREFIXES or "=" in first_token:
                        # Exclude lines that end like full English sentences
                        if not (cleaned.endswith(".") and len(cleaned.split()) > 6 and first_token not in KNOWN_COMMAND_PREFIXES):
                            commands.append({"raw": line, "command": cleaned})
        except Exception:
            pass
        return commands
