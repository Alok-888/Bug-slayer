"""
Bug Slayer - AI Engine
Powers diagnosis and setup synthesis using Google's Gemma models (via the Gemini API).
Includes an intelligent heuristic fallback for zero-downtime offline execution.

Model selection:
  * Default: Gemma 4 (gemma-4-26b-a4b-it, then gemma-4-31b-it as a backup).
  * Override with the BUGSLAYER_MODEL environment variable or the --model flag.
  * Needs GEMINI_API_KEY (free from https://aistudio.google.com).

Every result carries a "source" field that says which engine produced it
("gemma-4-26b-a4b-it" or "offline heuristic"), so the CLI can show honestly
whether the AI was really used.
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# Gemma 3 was removed from the Gemini API in May 2026; Gemma 4 is current.
# The 26B mixture-of-experts model answers fastest, the 31B model is the backup.
DEFAULT_MODELS = ["gemma-4-26b-a4b-it", "gemma-4-31b-it"]

REQUEST_TIMEOUT_MS = 60_000
OFFLINE_SOURCE = "offline heuristic"

# Root cause meaning "the README is fine, this machine is just different"
# (e.g. `python` vs `python3`). The CLI never rewrites the README for these.
ENVIRONMENT_ONLY = "ENVIRONMENT_ONLY"


def _host_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def extract_json_object(text: str, required_key: str) -> Optional[Dict[str, Any]]:
    """
    Pulls a JSON object out of a model reply. Handles ```json fences, text
    before/after the JSON, and several objects (returns the last one that
    contains `required_key`).
    """
    candidates: List[Dict[str, Any]] = []
    depth, start, in_str, escape = 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict):
                        candidates.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
    for obj in reversed(candidates):
        if required_key in obj:
            return obj
    return None


class AIEngine:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 environment: str = ""):
        """
        environment: a short description of where commands are executed,
        e.g. "Linux Docker container (python:3.12)" or "local macOS machine".
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        chosen = model or os.environ.get("BUGSLAYER_MODEL")
        self.models = [chosen] + [m for m in DEFAULT_MODELS if m != chosen] if chosen else list(DEFAULT_MODELS)
        self.environment = environment or f"local {_host_os()} machine"
        self.client = None
        self.last_error: Optional[str] = None
        self.last_model: Optional[str] = None

        if not HAS_GENAI:
            self.last_error = "the google-genai package is not installed"
        elif not self.api_key:
            self.last_error = "GEMINI_API_KEY is not set"
        else:
            try:
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
                )
            except Exception as e:  # pragma: no cover - depends on library/network
                self.last_error = f"could not create the AI client: {e}"

    @property
    def is_online(self) -> bool:
        return self.client is not None

    @property
    def model_label(self) -> str:
        return self.models[0] if self.client else f"{OFFLINE_SOURCE} ({self.last_error})"

    # ------------------------------------------------------------------ #
    # Model calls
    # ------------------------------------------------------------------ #
    def _ask_json(self, prompt: str, required_key: str) -> Dict[str, Any]:
        """
        Sends the prompt to Gemma and returns the parsed JSON reply.
        Tries the configured models in order. Each model is first called with
        thinking turned down (faster); if the model rejects that option the
        call is retried without it. Raises RuntimeError if nothing works.
        """
        errors = []
        fast_config = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=2048,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )
        plain_config = types.GenerateContentConfig(temperature=0.2, max_output_tokens=2048)

        for model in self.models:
            for config in (fast_config, plain_config):
                try:
                    response = self.client.models.generate_content(
                        model=model, contents=prompt, config=config
                    )
                    result = extract_json_object(response.text or "", required_key)
                    if result is None:
                        raise ValueError(f"reply did not contain JSON with '{required_key}'")
                    self.last_model = model
                    return result
                except Exception as e:
                    message = str(e)
                    errors.append(f"{model}: {message[:160]}")
                    lowered = message.lower()
                    if any(k in lowered for k in ("401", "403", "api key", "permission", "quota", "429")):
                        raise RuntimeError(message[:200])  # same key fails for every model
                    if config is fast_config and "thinking" in lowered:
                        continue  # model rejects the speed option; retry it without
                    if "404" in lowered or "not found" in lowered or "not supported" in lowered:
                        break  # this model is unavailable; try the next one
        raise RuntimeError(errors[-1] if errors else "no model available")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def diagnose_failure(self, failed_cmd: str, stderr: str, facts: Dict[str, Any],
                         readme_text: str = "", context: str = "") -> Dict[str, Any]:
        """
        Diagnoses why a README command failed and suggests the exact fix.
        context: optional extra line for repositories with several READMEs,
        e.g. "This is backend/README.md, a Python project in the folder backend/."
        """
        if self.client:
            context_line = f"{context}\n" if context else ""
            prompt = f"""You are Bug Slayer, an autonomous open-source setup healer.
A beginner followed a repository's README.md and this command failed.
{context_line}
Where the command ran: {self.environment}
Command: `{failed_cmd}`

Error output (last part):
```
{stderr[-3000:]}
```

Facts about the codebase:
- Languages: {facts.get('languages')}
- Manifest files: {facts.get('manifest_files')}
- Scripts in package/config: {json.dumps(facts.get('scripts', {}))}
- Entry points: {facts.get('entry_points')}
- Environment variables used by the code: {facts.get('env_variables')}

README (first part):
```
{readme_text[:4000]}
```

Diagnose the root cause and give one corrected command.
Rules:
- Prefer commands that work on Linux, macOS and Windows.
- If the README is actually correct and the failure only happens because of this
  particular machine (for example `python` vs `python3`, a tool that is simply not
  installed here, or a Windows-vs-Unix shell difference), use root_cause_type
  "ENVIRONMENT_ONLY" and still give a command that works on this machine.
- Never suggest commands that delete files outside the project or need sudo.

Reply with only a JSON object, no markdown:
{{
  "explanation": "1-2 sentence plain-English explanation of why it failed",
  "suggested_command": "the exact single command line to run instead",
  "root_cause_type": "SCRIPT_MISMATCH | MISSING_ENV | WRONG_ENTRYPOINT | DEPENDENCY_ERROR | PATH_ERROR | COMMAND_NOT_FOUND | ENVIRONMENT_ONLY"
}}"""
            try:
                result = self._ask_json(prompt, "suggested_command")
                result.setdefault("explanation", "The model did not explain the failure.")
                result.setdefault("root_cause_type", "UNKNOWN_ERROR")
                result["source"] = self.last_model
                return result
            except Exception as e:
                self.last_error = str(e)[:200]

        # Smart Heuristic Fallback (Ensures a reliable demo even offline)
        result = self._heuristic_diagnose(failed_cmd, stderr, facts)
        result["source"] = OFFLINE_SOURCE
        return result

    def generate_guide(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesizes a complete setup plan from scratch for an undocumented repo."""
        if self.client:
            safe_facts = {k: v for k, v in facts.items() if k != "readme_commands"}
            prompt = f"""You are Bug Slayer. This repository has no README setup instructions.
Commands will be tested on: {self.environment}
Facts about the repository: {json.dumps(safe_facts)}

Generate the exact setup and run commands a beginner needs.
Use reliable commands such as `python3 -m pip install -r requirements.txt` rather than bare `pip`.

Reply with only a JSON object, no markdown:
{{
  "project_title": "Clean Project Title",
  "description": "Short 1-sentence description based on language and files.",
  "prerequisites": ["tools needed, e.g. Python 3.10+, Node.js 18+"],
  "env_setup": "command to create the .env file if needed, or null",
  "install_commands": ["commands to install dependencies"],
  "run_command": "command to start or run the project",
  "test_command": "command to run tests if tests exist, else null"
}}"""
            try:
                result = self._ask_json(prompt, "install_commands")
                result.setdefault("install_commands", [])
                result["source"] = self.last_model
                return result
            except Exception as e:
                self.last_error = str(e)[:200]

        result = self._heuristic_generate(facts)
        result["source"] = OFFLINE_SOURCE
        return result

    # ------------------------------------------------------------------ #
    # Offline fallback rules
    # ------------------------------------------------------------------ #
    def _heuristic_diagnose(self, failed_cmd: str, stderr: str, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic fallback diagnostics when the AI is unavailable."""
        lower_err = stderr.lower()
        scripts = facts.get("scripts", {})
        entry_points = facts.get("entry_points", [])
        first_word = failed_cmd.split()[0] if failed_cmd.split() else ""
        not_found = any(k in lower_err for k in (
            "command not found", "not recognized as an internal or external command",
            "is not recognized as the name of", "python was not found",
        ))

        # Case 1: interpreter name differs on this machine (python vs python3)
        if not_found and first_word in ("python", "python3", "pip", "pip3"):
            if _host_os() == "windows":
                replacements = {"python3": "python", "pip3": "python -m pip", "pip": "python -m pip"}
            else:
                replacements = {"python": "python3", "pip": "python3 -m pip", "pip3": "python3 -m pip"}
            if first_word in replacements:
                new_cmd = replacements[first_word] + failed_cmd[len(first_word):]
                return {
                    "explanation": (f"`{first_word}` is not available on this {_host_os()} machine. "
                                    f"The README may still be right for other systems, so it is left unchanged."),
                    "suggested_command": new_cmd,
                    "root_cause_type": ENVIRONMENT_ONLY,
                }

        # Case 2: Script missing in package.json (e.g. npm start vs npm run dev)
        if "missing script:" in lower_err or "npm error missing script" in lower_err:
            for preferred in ["dev", "start", "serve"]:
                if preferred in scripts:
                    return {
                        "explanation": f"The README asked for `{failed_cmd}`, but package.json defines `{preferred}` as the active script.",
                        "suggested_command": f"npm run {preferred}",
                        "root_cause_type": "SCRIPT_MISMATCH",
                    }

        # Case 3: FileNotFoundError / no such file
        if "filenotfounderror" in lower_err or "no such file or directory" in lower_err or "can't open file" in lower_err:
            if entry_points and first_word.startswith("python"):
                valid_ep = entry_points[0]
                return {
                    "explanation": f"The target script in `{failed_cmd}` does not exist. Discovered entry point `{valid_ep}` in the repository.",
                    "suggested_command": f"{first_word} {valid_ep}",
                    "root_cause_type": "WRONG_ENTRYPOINT",
                }

        # Case 4: Missing Module
        if "modulenotfounderror" in lower_err or "cannot find module" in lower_err:
            if "requirements.txt" in facts.get("manifest_files", []):
                py = "python" if _host_os() == "windows" else "python3"
                return {
                    "explanation": "A required dependency was missing at runtime because requirements were not installed.",
                    "suggested_command": f"{py} -m pip install -r requirements.txt",
                    "root_cause_type": "DEPENDENCY_ERROR",
                }
            if "package.json" in facts.get("manifest_files", []):
                return {
                    "explanation": "Node modules were missing at runtime.",
                    "suggested_command": "npm install",
                    "root_cause_type": "DEPENDENCY_ERROR",
                }

        # Generic fallback
        return {
            "explanation": f"Execution failed with a non-zero exit code. Error trace: {stderr[:120].strip()}",
            "suggested_command": failed_cmd,
            "root_cause_type": "UNKNOWN_ERROR",
        }

    def _heuristic_generate(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic fallback generator for zero-doc repositories."""
        languages = facts.get("languages", []) or ["Unknown"]
        manifests = facts.get("manifest_files", [])
        entry_points = facts.get("entry_points", [])
        scripts = facts.get("scripts", {})

        plan = {
            "project_title": "Project Overview",
            "description": f"A {', '.join(languages)} project.",
            "prerequisites": [],
            "env_setup": None,
            "install_commands": [],
            "run_command": "echo 'No run command detected'",
            "test_command": None,
        }

        if facts.get("env_variables"):
            has_example = os.path.exists(os.path.join(facts.get("path", ""), ".env.example"))
            plan["env_setup"] = "cp .env.example .env" if has_example else "# Configure required environment variables"

        if "Python" in languages:
            plan["prerequisites"].append("Python 3.10+ and pip")
            if "requirements.txt" in manifests:
                plan["install_commands"].append("python3 -m pip install -r requirements.txt")
            elif "pyproject.toml" in manifests:
                plan["install_commands"].append("python3 -m pip install .")
            if entry_points:
                plan["run_command"] = f"python3 {entry_points[0]}"

        if "JavaScript/TypeScript" in languages:
            plan["prerequisites"].append("Node.js 18+ and npm")
            pkg_mgr = facts.get("package_manager") or "npm"
            if pkg_mgr not in ("npm", "yarn", "pnpm", "bun"):
                pkg_mgr = "npm"
            plan["install_commands"].append(f"{pkg_mgr} install")
            if "dev" in scripts:
                plan["run_command"] = f"{pkg_mgr} run dev"
            elif "start" in scripts:
                plan["run_command"] = f"{pkg_mgr} start"
            elif entry_points:
                plan["run_command"] = f"node {entry_points[0]}"

        return plan
