"""
Bug Slayer - Codebase Inspector
Scans any repository to discover language, frameworks, dependencies,
environment variables, entry points, container configurations, and service ports.
Optimized with bounded shallow walks to scan 500MB+ / 10,000+ file repos in < 0.5s.
"""

import os
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Set

from bugslayer.safety import is_safe_to_read, safe_read_text


class CodebaseInspector:
    IGNORED_DIRS = {
        ".git", "node_modules", "venv", ".venv", "env", "__pycache__",
        ".next", "dist", "build", "target", ".idea", ".vscode", "vendor",
        ".pytest_cache", "coverage", ".turbo", "out", "assets", "static", "public"
    }

    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir).resolve()

    def inspect(self) -> Dict[str, Any]:
        """Performs a comprehensive, bounded scan of the repository."""
        start_time = time.time()
        facts: Dict[str, Any] = {
            "path": str(self.target_dir),
            "languages": [],
            "frameworks": [],
            "package_manager": None,
            "manifest_files": [],
            "scripts": {},
            "env_variables": [],
            "env_details": [],
            "entry_points": [],
            "has_readme": False,
            "readme_path": None,
            "readme_commands": [],
            "docker_compose": None,
            "has_dockerfile": False,
            "docker_services": [],
            "ports": [],
            "primary_port": None,
            "repo_scale": "standard",
            "files_scanned": 0,
            "scan_duration_ms": 0,
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

        # 2. Detect Ecosystems, Manifests & Containers
        self._detect_manifests(facts)
        self._detect_containers(facts)

        # 3. Detect Entry Points (root and key subdirectories)
        self._detect_entry_points(facts)

        # 4. Detect Frameworks (FastAPI, Next.js, Flask, Django, etc.); after the
        #    entry points, so their imports can be checked too
        self._detect_frameworks(facts)

        # 5. Harvest Environment Variables (bounded scan)
        self._harvest_env(facts)

        # 6. Sniff Network / Web Ports
        self._sniff_ports(facts)

        scan_ms = int((time.time() - start_time) * 1000)
        facts["scan_duration_ms"] = scan_ms
        if facts["files_scanned"] > 200:
            facts["repo_scale"] = f"large ({facts['files_scanned']}+ files)"

        return facts

    def _detect_manifests(self, facts: Dict[str, Any]):
        """Detects package managers, frameworks, and scripts at root and depth 1."""
        candidate_dirs = [self.target_dir]
        try:
            for item in self.target_dir.iterdir():
                if item.is_dir() and item.name not in self.IGNORED_DIRS and not item.name.startswith("."):
                    candidate_dirs.append(item)
        except Exception:
            pass

        for cdir in candidate_dirs:
            prefix = "" if cdir == self.target_dir else f"{cdir.name}/"

            # Node.js
            pkg_json = cdir / "package.json"
            if pkg_json.exists():
                if "JavaScript/TypeScript" not in facts["languages"]:
                    facts["languages"].append("JavaScript/TypeScript")
                facts["manifest_files"].append(f"{prefix}package.json")

                if (cdir / "pnpm-lock.yaml").exists():
                    facts["package_manager"] = "pnpm"
                elif (cdir / "yarn.lock").exists():
                    facts["package_manager"] = "yarn"
                elif (cdir / "bun.lockb").exists():
                    facts["package_manager"] = "bun"
                elif not facts["package_manager"]:
                    facts["package_manager"] = "npm"

                try:
                    data = json.loads(safe_read_text(pkg_json, self.target_dir) or "{}")
                    scripts = data.get("scripts", {})
                    if not facts["scripts"] and isinstance(scripts, dict):
                        facts["scripts"] = scripts
                    if isinstance(data.get("main"), str):
                        facts["entry_points"].append(f"{prefix}{data['main']}")
                except Exception:
                    pass

            # Python
            pyproject = cdir / "pyproject.toml"
            req_txt = cdir / "requirements.txt"
            pipfile = cdir / "Pipfile"
            setup_py = cdir / "setup.py"

            if pyproject.exists() or req_txt.exists() or pipfile.exists() or setup_py.exists():
                if "Python" not in facts["languages"]:
                    facts["languages"].append("Python")
                if pyproject.exists():
                    facts["manifest_files"].append(f"{prefix}pyproject.toml")
                    if "poetry" in safe_read_text(pyproject, self.target_dir):
                        facts["package_manager"] = "poetry"
                    elif not facts["package_manager"]:
                        facts["package_manager"] = "pip"
                if req_txt.exists():
                    facts["manifest_files"].append(f"{prefix}requirements.txt")
                    facts["package_manager"] = facts["package_manager"] or "pip"
                if pipfile.exists():
                    facts["manifest_files"].append(f"{prefix}Pipfile")
                    facts["package_manager"] = "pipenv"

            # Go
            if (cdir / "go.mod").exists():
                if "Go" not in facts["languages"]:
                    facts["languages"].append("Go")
                facts["manifest_files"].append(f"{prefix}go.mod")
                facts["package_manager"] = facts["package_manager"] or "go"

            # Rust
            if (cdir / "Cargo.toml").exists():
                if "Rust" not in facts["languages"]:
                    facts["languages"].append("Rust")
                facts["manifest_files"].append(f"{prefix}Cargo.toml")
                facts["package_manager"] = facts["package_manager"] or "cargo"

    def _detect_containers(self, facts: Dict[str, Any]):
        """Detects Dockerfile and Docker Compose configurations."""
        dockerfile = self.target_dir / "Dockerfile"
        if dockerfile.exists():
            facts["has_dockerfile"] = True

        for compose_name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            compose_file = self.target_dir / compose_name
            if compose_file.exists():
                facts["docker_compose"] = compose_name
                try:
                    content = safe_read_text(compose_file, self.target_dir)
                    # Extract service names (heuristically look for top-level service keys)
                    service_match = re.findall(r"^\s{2}([a-zA-Z0-9_-]+):", content, flags=re.MULTILINE)
                    if service_match:
                        facts["docker_services"] = [s for s in service_match if s not in {"services", "version", "networks", "volumes"}][:5]

                    # Extract exposed ports
                    port_matches = re.findall(r'["\']?(\d{2,5}):\d{2,5}["\']?', content)
                    for p in port_matches:
                        port_int = int(p)
                        if port_int not in facts["ports"]:
                            facts["ports"].append(port_int)
                except Exception:
                    pass
                break

    # Dependency name -> framework. Matched against real package names, not any
    # text in the file (plain text search found "vite" in "invite", "next" in
    # "next generation").
    FRAMEWORK_PACKAGES = {
        "fastapi": "FastAPI", "flask": "Flask", "django": "Django", "streamlit": "Streamlit",
        "tornado": "Tornado", "next": "Next.js", "express": "Express", "@nestjs/core": "NestJS",
        "vite": "Vite",
    }

    def _dependency_names(self, mf_path: Path) -> Set[str]:
        """Package names listed in a requirements.txt, pyproject.toml, Pipfile or package.json."""
        text = safe_read_text(mf_path, self.target_dir)
        names: Set[str] = set()
        if mf_path.name == "package.json":
            try:
                data = json.loads(text or "{}")
                for key in ("dependencies", "devDependencies", "peerDependencies"):
                    deps = data.get(key)
                    if isinstance(deps, dict):
                        names.update(str(k).lower() for k in deps)
            except Exception:
                pass
            return names
        if mf_path.name == "requirements.txt":
            for line in text.splitlines():
                m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
                if m and not line.lstrip().startswith(("#", "-")):
                    names.add(m.group(1).lower())
            return names
        # pyproject.toml / Pipfile: quoted or bare names followed by a version marker,
        # e.g. "fastapi>=0.110", fastapi = "^0.110", django = "*"
        for m in re.finditer(r'(?m)(?:^|["\'\s])([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:[<>=!~^]|=\s*["\'{])', text):
            names.add(m.group(1).lower())
        return names

    def _detect_frameworks(self, facts: Dict[str, Any]):
        """Identifies specific modern frameworks from dependencies and entry-file imports."""
        frameworks: Set[str] = set()

        for mf in facts["manifest_files"]:
            mf_path = self.target_dir / mf
            if not mf_path.exists():
                continue
            names = self._dependency_names(mf_path)
            for package, framework in self.FRAMEWORK_PACKAGES.items():
                if package in names:
                    frameworks.add(framework)

        # Check entry files for import signatures
        for ep in facts["entry_points"][:3]:
            ep_path = self.target_dir / ep
            if ep_path.exists():
                code = safe_read_text(ep_path, self.target_dir)
                if "FastAPI(" in code or "from fastapi" in code:
                    frameworks.add("FastAPI")
                elif "Flask(__name__)" in code or "from flask" in code:
                    frameworks.add("Flask")
                elif "streamlit as st" in code:
                    frameworks.add("Streamlit")
                elif "express()" in code or 'require("express")' in code or "from 'express'" in code:
                    frameworks.add("Express")

        facts["frameworks"] = sorted(list(frameworks))

    def _detect_entry_points(self, facts: Dict[str, Any]):
        """Hunts for standard entry points across root and common nested subdirectories."""
        candidates = [
            "main.py", "app.py", "server.py", "index.py", "run.py", "manage.py",
            "src/main.py", "src/app.py", "api/main.py", "api/app.py",
            "backend/main.py", "backend/app.py", "server/main.py",
            "index.js", "server.js", "app.js",
            "src/index.js", "src/server.js", "src/index.ts", "src/main.ts", "src/App.tsx",
            "server/index.js", "server/server.js",
            "main.go", "cmd/main.go", "cmd/server/main.go", "src/main.rs"
        ]
        for candidate in candidates:
            if (self.target_dir / candidate).exists():
                if candidate not in facts["entry_points"]:
                    facts["entry_points"].append(candidate)

    def _harvest_env(self, facts: Dict[str, Any]):
        """
        Parses .env.example / .env.sample templates and performs a bounded,
        fast static regex across source code (depth <= 3, max 50 source files).
        """
        env_vars = set()
        env_details = []

        # 1. Parse .env.example / .env.sample
        for env_sample in [".env.example", ".env.sample", "sample.env", ".env.template"]:
            sample_file = self.target_dir / env_sample
            if sample_file.exists():
                for line in safe_read_text(sample_file, self.target_dir).splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    parts = line.split("=", 1)
                    var_name = parts[0].strip()
                    default_val = parts[1].strip() if len(parts) > 1 else ""

                    # Strip trailing comments if any
                    comment = ""
                    if "#" in default_val:
                        val_parts = default_val.split("#", 1)
                        default_val = val_parts[0].strip()
                        comment = val_parts[1].strip()

                    # Strip enclosing quotes
                    default_val = default_val.strip("\"'")
                    # Never copy secret-looking values into the README or the AI prompt
                    default_val = self._redact_env_value(var_name, default_val)
                    if var_name:
                        env_vars.add(var_name)
                        env_details.append({
                            "name": var_name,
                            "default": default_val or "(none)",
                            "description": comment or self._infer_env_description(var_name),
                        })
                break

        # 2. Fast bounded walk (depth <= 3, max 50 source files)
        py_pattern = re.compile(r'(?:os\.environ\.get|os\.getenv)\s*\(\s*["\']([A-Z0-9_]+)["\']')
        js_pattern = re.compile(r'process\.env\.([A-Z0-9_]+)')

        files_inspected = 0
        total_files = 0

        for root, dirs, files in os.walk(self.target_dir):
            rel_path = Path(root).relative_to(self.target_dir)
            if len(rel_path.parts) >= 3:
                dirs[:] = []  # Do not recurse deeper than depth 3
                continue

            # Prune ignored directory trees
            dirs[:] = [d for d in dirs if d not in self.IGNORED_DIRS and not d.startswith(".")]

            total_files += len(files)
            if files_inspected >= 50:
                continue

            for file in files:
                if file.endswith((".py", ".js", ".ts", ".jsx", ".tsx")):
                    files_inspected += 1
                    file_path = Path(root) / file
                    try:
                        content = safe_read_text(file_path, self.target_dir)
                        for match in py_pattern.findall(content):
                            env_vars.add(match)
                        for match in js_pattern.findall(content):
                            env_vars.add(match)
                    except Exception:
                        pass
                if files_inspected >= 50:
                    break

        ignored_prefixes = ("GITHUB_", "RUNNER_", "INPUT_", "ACTIONS_")
        ignored = {"CI", "HOME", "PATH", "PWD", "USER", "SHELL", "TERM", "LANG", "TMPDIR", "NODE_ENV"}
        cleaned_env = sorted([v for v in env_vars if v not in ignored and not v.startswith(ignored_prefixes)])

        # Ensure env_details has entries for all cleaned_env
        known_detail_names = {d["name"] for d in env_details}
        for var in cleaned_env:
            if var not in known_detail_names:
                env_details.append({
                    "name": var,
                    "default": "(required)",
                    "description": self._infer_env_description(var),
                })

        facts["env_variables"] = cleaned_env
        facts["env_details"] = env_details
        facts["files_scanned"] = total_files

    SECRET_NAME = re.compile(r"SECRET|PASSWORD|PASSWD|PASS(?:$|_)|TOKEN|(?:^|_)KEY(?:$|_)|APIKEY|PRIVATE|CREDENTIAL|AUTH", re.IGNORECASE)

    @classmethod
    def _redact_env_value(cls, var_name: str, value: str) -> str:
        """
        Example values for secrets are replaced by a placeholder, and passwords
        inside connection URLs (scheme://user:password@host) are masked.
        """
        if not value:
            return value
        if cls.SECRET_NAME.search(var_name):
            return "<your value>"
        return re.sub(r"(://[^:/@\s]+:)[^@\s]+@", r"\1****@", value)

    def _infer_env_description(self, var_name: str) -> str:
        """Infers a clean description for an environment variable name."""
        upper = var_name.upper()
        if "PORT" in upper:
            return "Application server listening port"
        if "HOST" in upper:
            return "Network host binding address"
        if any(k in upper for k in ("DB", "DATABASE", "POSTGRES", "MYSQL", "MONGO")):
            return "Database connection string or URI"
        if any(k in upper for k in ("REDIS", "CACHE")):
            return "Cache / Redis service connection URI"
        if any(k in upper for k in ("SECRET", "KEY", "TOKEN", "AUTH", "PASS")):
            return "Authentication secret or API access token"
        if "DEBUG" in upper:
            return "Enable or disable verbose debug mode"
        if "ENV" in upper or "ENVIRONMENT" in upper:
            return "Runtime environment (e.g. development, production)"
        return "Application configuration setting"

    def _sniff_ports(self, facts: Dict[str, Any]):
        """Infers active server ports from environment variables, compose, or framework defaults."""
        ports = list(facts.get("ports", []))

        # Check env_details for PORT
        for item in facts.get("env_details", []):
            if "PORT" in item["name"].upper():
                val = item.get("default", "")
                if val.isdigit():
                    p_int = int(val)
                    if p_int not in ports:
                        ports.append(p_int)

        # Framework defaults
        frameworks = facts.get("frameworks", [])
        if "FastAPI" in frameworks and 8000 not in ports:
            ports.append(8000)
        elif "Flask" in frameworks and 5000 not in ports:
            ports.append(5000)
        elif "Django" in frameworks and 8000 not in ports:
            ports.append(8000)
        elif "Streamlit" in frameworks and 8501 not in ports:
            ports.append(8501)
        elif "Next.js" in frameworks and 3000 not in ports:
            ports.append(3000)
        elif "Vite" in frameworks and 5173 not in ports:
            ports.append(5173)
        elif "Express" in frameworks and 3000 not in ports:
            ports.append(3000)

        facts["ports"] = ports
        if ports:
            facts["primary_port"] = ports[0]

    def _extract_readme_commands(self, readme_path: Path) -> List[Dict[str, Any]]:
        """Extracts bash/sh command blocks from a README.md file, filtering out text prose."""
        commands = []
        KNOWN_COMMAND_PREFIXES = {
            "git", "cd", "cp", "mv", "rm", "mkdir", "export", "source", "chmod",
            "npm", "npx", "yarn", "pnpm", "bun", "node",
            "pip", "pip3", "python", "python3", "poetry", "pytest", "pytest-3", "uvicorn", "flask",
            "cargo", "rustc", "go", "make", "docker", "docker-compose",
            "curl", "wget", "cat", "echo", "sed", "awk", "grep", "find", "brew", "apt", "sudo",
            "py", "uv", "pipx", "conda", "deno", "java", "mvn", "gradle", "dotnet",
            "bundle", "gem", "composer", "php", "touch", "ls", "set", "rustup", "make"
        }

        try:
            content = safe_read_text(readme_path, self.target_dir)
            for line_no, line in self._shell_block_lines(content):
                cleaned = line.strip()
                if not cleaned or cleaned.startswith("#"):
                    continue

                # Strip leading '$ ' / '> ' prompt symbols if present
                is_prompt = False
                if cleaned.startswith("$ ") or cleaned.startswith("> "):
                    cleaned = cleaned[2:].strip()
                    is_prompt = True

                first_token = cleaned.split()[0].lower() if cleaned.split() else ""
                entry = {"raw": line, "command": cleaned, "line": line_no}
                if first_token.startswith("./") or first_token.startswith(".\\"):
                    commands.append(entry)
                elif is_prompt or first_token in KNOWN_COMMAND_PREFIXES or "=" in first_token:
                    # Exclude lines that end like full English sentences
                    if not (cleaned.endswith(".") and len(cleaned.split()) > 6 and first_token not in KNOWN_COMMAND_PREFIXES):
                        commands.append(entry)
        except Exception:
            pass
        return commands

    @staticmethod
    def _shell_block_lines(content: str) -> List[Tuple[int, str]]:
        """
        Walks the README line by line and returns (line_number, text) for lines
        inside shell code blocks (```bash, ```sh, ```shell, ```zsh, ```console
        or unlabeled ```). Tracking open/close fences explicitly prevents prose
        between two code blocks from being mistaken for a command.
        """
        shell_langs = {"", "bash", "sh", "shell", "zsh", "console", "terminal"}
        lines: List[Tuple[int, str]] = []
        in_block, is_shell = False, False
        for number, raw in enumerate(content.splitlines(), start=1):
            fence = re.match(r"^\s*```\s*([\w+-]*)", raw)
            if fence:
                if not in_block:
                    in_block, is_shell = True, fence.group(1).lower() in shell_langs
                else:
                    in_block = False
                continue
            if in_block and is_shell:
                lines.append((number, raw))
        return lines

    # ------------------------------------------------------------------ #
    # Multiple READMEs (e.g. frontend/README.md, backend/README.md)
    # ------------------------------------------------------------------ #
    README_NAMES = {"readme.md", "readme", "readme.txt", "readme.markdown"}
    SKIP_DIRS = {
        ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build",
        "vendor", "target", "site-packages", ".tox", ".next", ".nuxt", "coverage",
        "fixtures", "testdata", "third_party",
    }
    MAX_DEPTH = 4

    # Used when a README's folder has no manifest file of its own.
    COMMAND_LANGUAGES = {
        "npm": "JavaScript/TypeScript", "npx": "JavaScript/TypeScript", "yarn": "JavaScript/TypeScript",
        "pnpm": "JavaScript/TypeScript", "node": "JavaScript/TypeScript", "bun": "JavaScript/TypeScript",
        "pip": "Python", "pip3": "Python", "python": "Python", "python3": "Python",
        "poetry": "Python", "uvicorn": "Python", "flask": "Python", "pytest": "Python",
        "go": "Go", "cargo": "Rust", "rustc": "Rust",
    }

    def find_extra_readmes(self, main_readme: str = None) -> List[str]:
        """
        Returns README files in sub-folders that contain at least one shell
        command, sorted by path. The main README (in the repository's own
        folder) is never included, so the existing single-README flow is
        unaffected.
        """
        found = []
        root = str(self.target_dir)
        for folder, subfolders, files in os.walk(root):
            depth = os.path.relpath(folder, root).count(os.sep) + (0 if folder == root else 1)
            subfolders[:] = sorted(
                d for d in subfolders
                if d not in self.SKIP_DIRS and not d.startswith(".") and depth < self.MAX_DEPTH
            )
            if folder == root:
                continue  # the main README is handled by inspect()
            for name in sorted(files):
                if name.lower() not in self.README_NAMES:
                    continue
                path = os.path.join(folder, name)
                if main_readme and os.path.exists(main_readme):
                    try:
                        if os.path.samefile(path, main_readme):
                            continue
                    except OSError:
                        pass
                if self._extract_readme_commands(Path(path)):
                    found.append(path)
                break  # one README per folder
        return found

    def inspect_readme(self, readme_path: str) -> Dict[str, Any]:
        """
        Facts for one README in a sub-folder: its folder's languages, manifests,
        entry points and environment variables (detected with the same code as
        inspect()), plus that README's own commands.
        """
        readme = Path(readme_path).resolve()
        facts = CodebaseInspector(str(readme.parent)).inspect()
        facts["has_readme"] = True
        facts["readme_path"] = str(readme)
        facts["readme_commands"] = self._extract_readme_commands(readme)
        facts["relative_path"] = os.path.relpath(str(readme), str(self.target_dir)).replace(os.sep, "/")
        facts["relative_folder"] = os.path.dirname(facts["relative_path"])

        if not facts["languages"]:
            for cmd in facts["readme_commands"]:
                words = cmd["command"].split()
                lang = self.COMMAND_LANGUAGES.get(words[0].lower()) if words else None
                if lang and lang not in facts["languages"]:
                    facts["languages"].append(lang)
        return facts
