"""
Bug Slayer - AI Engine
Powers diagnosis and setup synthesis using Gemma / Gemini models.
Includes an intelligent heuristic fallback for zero-downtime offline execution.
"""

import os
import json
import shutil
from typing import Dict, Any, Optional

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class AIEngine:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.client = None
        if HAS_GENAI and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception:
                self.client = None

    def diagnose_failure(self, failed_cmd: str, stderr: str, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Diagnoses why a README command failed and suggests the exact fix."""
        if self.client:
            try:
                prompt = f"""
You are Bug Slayer, an autonomous open-source setup healer.
A developer tried to run this command from the README.md on macOS/Linux:
Command: `{failed_cmd}`

It failed with this error:
```{stderr}```

Here are the inspected facts about this codebase:
- Languages: {facts.get('languages')}
- Manifest files: {facts.get('manifest_files')}
- Detected scripts in package/config: {json.dumps(facts.get('scripts', {}))}
- Detected entry points: {facts.get('entry_points')}
- Detected required env vars: {facts.get('env_variables')}

Diagnose the root cause and provide the exact corrected command.
Respond in strict JSON with no markdown wrapping:
{{
  "explanation": "Clear 1-2 sentence human explanation of why it failed.",
  "suggested_command": "The exact single command line to run instead",
  "root_cause_type": "SCRIPT_MISMATCH | MISSING_ENV | WRONG_ENTRYPOINT | DEPENDENCY_ERROR | PATH_ERROR | COMMAND_NOT_FOUND"
}}
"""
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                return json.loads(response.text)
            except Exception:
                pass

        # Smart Heuristic Fallback (Ensures 100% reliable demo even offline)
        return self._heuristic_diagnose(failed_cmd, stderr, facts)

    def generate_guide(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesizes a complete setup plan from scratch for an undocumented repo."""
        if self.client:
            try:
                prompt = f"""
You are Bug Slayer. This repository has no README instructions.
Inspect these facts and generate the exact setup and run commands for a modern developer:
Facts: {json.dumps(facts)}

Use cross-platform reliable commands (e.g. `python3 -m pip install -r requirements.txt` instead of raw `pip`).

Respond in strict JSON with no markdown wrapping:
{{
  "project_title": "Clean Project Title",
  "description": "Short 1-sentence description based on language and files.",
  "prerequisites": ["List of tools, e.g. Python 3.10+, Node.js 18+"],
  "env_setup": "Command to setup .env if needed, or null",
  "install_commands": ["list of commands to install dependencies"],
  "run_command": "Command to start or run the project",
  "test_command": "Command to run tests if tests exist, else null"
}}
"""
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                return json.loads(response.text)
            except Exception:
                pass

        return self._heuristic_generate(facts)

    def _heuristic_diagnose(self, failed_cmd: str, stderr: str, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic fallback diagnostics when offline."""
        lower_err = stderr.lower()
        scripts = facts.get("scripts", {})
        entry_points = facts.get("entry_points", [])

        # Case 1: command not found (pip -> python3 -m pip)
        if "command not found" in lower_err:
            if "pip" in lower_err and failed_cmd.startswith("pip"):
                # Replace raw pip with python3 -m pip
                new_cmd = failed_cmd.replace("pip", "python3 -m pip", 1)
                return {
                    "explanation": "The system shell could not find `pip` directly in PATH. Using portable `python3 -m pip` instead.",
                    "suggested_command": new_cmd,
                    "root_cause_type": "COMMAND_NOT_FOUND"
                }
            if "python:" in lower_err and failed_cmd.startswith("python "):
                new_cmd = failed_cmd.replace("python", "python3", 1)
                return {
                    "explanation": "The `python` binary is not linked in PATH on this OS. Using `python3` instead.",
                    "suggested_command": new_cmd,
                    "root_cause_type": "COMMAND_NOT_FOUND"
                }

        # Case 2: Script missing in package.json (e.g. npm start vs npm run dev)
        if "missing script:" in lower_err or "npm error missing script" in lower_err:
            for preferred in ["dev", "start", "serve"]:
                if preferred in scripts:
                    return {
                        "explanation": f"The README asked for `{failed_cmd}`, but package.json defines `{preferred}` as the active script.",
                        "suggested_command": f"npm run {preferred}",
                        "root_cause_type": "SCRIPT_MISMATCH"
                    }

        # Case 3: FileNotFoundError / no such file
        if "filenotfounderror" in lower_err or "no such file or directory" in lower_err:
            if entry_points:
                valid_ep = entry_points[0]
                if "python" in failed_cmd:
                    return {
                        "explanation": f"The target script in `{failed_cmd}` does not exist. Discovered entry point `{valid_ep}` in the repository.",
                        "suggested_command": f"python3 {valid_ep}",
                        "root_cause_type": "WRONG_ENTRYPOINT"
                    }

        # Case 4: Missing Module
        if "modulenotfounderror" in lower_err or "cannot find module" in lower_err:
            if "requirements.txt" in facts.get("manifest_files", []):
                return {
                    "explanation": "A required dependency was missing at runtime because requirements were not installed.",
                    "suggested_command": "python3 -m pip install -r requirements.txt",
                    "root_cause_type": "DEPENDENCY_ERROR"
                }
            if "package.json" in facts.get("manifest_files", []):
                return {
                    "explanation": "Node modules were missing at runtime.",
                    "suggested_command": "npm install",
                    "root_cause_type": "DEPENDENCY_ERROR"
                }

        # Generic fallback
        return {
            "explanation": f"Execution failed with non-zero exit code. Error trace: {stderr[:120].strip()}",
            "suggested_command": failed_cmd,
            "root_cause_type": "UNKNOWN_ERROR"
        }

    def _heuristic_generate(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic fallback generator for zero-doc repositories."""
        languages = facts.get("languages", ["Unknown"])
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
            "test_command": None
        }

        # Environment
        if facts.get("env_variables"):
            plan["env_setup"] = "cp .env.example .env" if ".env.example" in os.listdir(facts["path"]) else "# Configure required environment variables"

        # Python (Using python3 -m pip for cross-platform resilience)
        if "Python" in languages:
            plan["prerequisites"].append("Python 3.10+ and pip")
            if "requirements.txt" in manifests:
                plan["install_commands"].append("python3 -m pip install -r requirements.txt")
            if entry_points:
                plan["run_command"] = f"python3 {entry_points[0]}"

        # Node.js
        if "JavaScript/TypeScript" in languages:
            plan["prerequisites"].append("Node.js 18+ and npm")
            pkg_mgr = facts.get("package_manager", "npm")
            plan["install_commands"].append(f"{pkg_mgr} install")
            if "dev" in scripts:
                plan["run_command"] = f"{pkg_mgr} run dev"
            elif "start" in scripts:
                plan["run_command"] = f"{pkg_mgr} start"
            elif entry_points:
                plan["run_command"] = f"node {entry_points[0]}"

        return plan
