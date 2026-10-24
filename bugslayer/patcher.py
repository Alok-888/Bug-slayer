"""
Bug Slayer - Documentation Patcher & Generator
Surgically updates existing READMEs, generates git diffs, and synthesizes
brand-new verified documentation with configuration tables, endpoints, and container runtimes.
"""

import difflib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from bugslayer.safety import is_safe_to_read, safe_write_text


class DocumentationPatcher:
    @staticmethod
    def heal_readme(readme_path: str, old_cmd: str, new_cmd: str, explanation: str,
                    line_number: Optional[int] = None, display_name: str = "README.md") -> Tuple[bool, str]:
        """
        Replaces the broken command with the working command in README.md
        and returns a unified diff string.

        old_cmd is the exact README line. When line_number is given, only that
        line is changed, so the same command elsewhere in the README (for
        example in a Windows section) is left alone.
        """
        path = Path(readme_path)
        if not path.exists() or path.is_symlink() or not is_safe_to_read(path):
            return False, ""

        original_text = path.read_text(encoding="utf-8", errors="ignore")
        lines = original_text.splitlines(keepends=True)

        patched_text = None
        if line_number and 1 <= line_number <= len(lines) and old_cmd.strip() in lines[line_number - 1]:
            target = lines[line_number - 1]
            lines[line_number - 1] = target.replace(old_cmd.strip(), new_cmd.strip(), 1)
            patched_text = "".join(lines)
        elif old_cmd in original_text:
            patched_text = original_text.replace(old_cmd, new_cmd, 1)

        if patched_text is None or patched_text == original_text:
            return False, ""

        # Generate unified diff
        diff = list(difflib.unified_diff(
            original_text.splitlines(keepends=True),
            patched_text.splitlines(keepends=True),
            fromfile=f"a/{display_name}",
            tofile=f"b/{display_name}"
        ))

        # Write the patched file
        safe_write_text(path, patched_text)

        return True, "".join(diff)

    @staticmethod
    def generate_new_readme(target_dir: str, plan: Dict[str, Any]) -> str:
        """Generates a complete, beautiful README.md from an AI setup plan."""
        title = plan.get("project_title", "Project Documentation")
        desc = plan.get("description", "A modern project setup.")
        framework = plan.get("framework")
        prereqs = plan.get("prerequisites", [])
        env_cmd = plan.get("env_setup")
        install_cmds = plan.get("install_commands", [])
        run_cmd = plan.get("run_command", "")
        docker_cmd = plan.get("docker_command")
        service_url = plan.get("service_url")
        api_docs_url = plan.get("api_docs_url")
        test_cmd = plan.get("test_command")
        env_details = plan.get("env_details", [])

        lines = [
            f"# {title}",
            "",
            "> 🛡️ *Setup instructions synthesized and verified by [Bug Slayer](https://github.com/chauhanalok546-rgb/Bug-slayer).* ",
            "",
            desc,
            "",
        ]

        if framework and framework != "Generic":
            lines.extend([
                f"**Architecture & Framework:** `{framework}`",
                "",
            ])

        # Prerequisites
        lines.extend([
            "## 📋 Prerequisites",
            "",
        ])
        if prereqs:
            for p in prereqs:
                lines.append(f"- {p}")
        else:
            lines.append("- Standard developer tools")
        lines.append("")

        # Environment Configuration
        if env_details:
            lines.extend([
                "## ⚙️ Configuration & Environment",
                "",
            ])
            if env_cmd and not env_cmd.startswith("#"):
                lines.extend([
                    "Create your local environment configuration file:",
                    "```bash",
                    env_cmd,
                    "```",
                    "",
                ])

            lines.extend([
                "| Variable | Default / Example | Purpose |",
                "|:---|:---|:---|",
            ])
            def cell(text) -> str:
                # A | or ` in a value would break the Markdown table
                return str(text).replace("\\", "\\\\").replace("|", "\\|").replace("`", "'").replace("\n", " ")

            for item in env_details:
                name = cell(item.get("name", ""))
                default = cell(item.get("default", "(none)"))
                description = cell(item.get("description", "Configuration setting"))
                lines.append(f"| `{name}` | `{default}` | {description} |")
            lines.append("")

        # Quickstart Guide
        lines.extend([
            "## 🚀 Quickstart Guide",
            "",
            "### 💻 Option A: Local Setup",
            "",
        ])

        step_num = 1
        if env_cmd and not env_details:
            lines.extend([
                f"#### {step_num}. Configure Environment",
                "```bash",
                env_cmd,
                "```",
                "",
            ])
            step_num += 1

        if install_cmds:
            lines.extend([
                f"#### {step_num}. Install Dependencies",
                "```bash",
                "\n".join(install_cmds),
                "```",
                "",
            ])
            step_num += 1

        if run_cmd:
            lines.extend([
                f"#### {step_num}. Run the Application",
                "```bash",
                run_cmd,
                "```",
                "",
            ])
            step_num += 1

        if test_cmd:
            lines.extend([
                f"#### {step_num}. Run Tests",
                "```bash",
                test_cmd,
                "```",
                "",
            ])

        # Docker Quickstart Option
        if docker_cmd:
            lines.extend([
                "### 🐳 Option B: Docker Quickstart",
                "",
                "Run the complete application inside isolated containers:",
                "```bash",
                docker_cmd,
                "```",
                "",
            ])

        # Endpoints
        if service_url or api_docs_url:
            lines.extend([
                "## 🌐 Endpoints & Access",
                "",
                "Once the service is started:",
            ])
            if service_url:
                lines.append(f"- **Service URL:** [{service_url}]({service_url})")
            if api_docs_url:
                lines.append(f"- **Interactive API Documentation:** [{api_docs_url}]({api_docs_url})")
            lines.append("")

        # Windows notice
        all_cmds = [c for c in [env_cmd, *install_cmds, run_cmd, test_cmd] if c]
        if any(str(c).startswith(("python3 ", "pip3 ")) for c in all_cmds):
            lines.extend([
                "> 🪟 **Windows users:** type `python` instead of `python3`.",
                "",
            ])

        # 1-Click Installer
        lines.extend([
            "> ⚡ **1-Click Installer:** A pre-verified installer `setup.sh` is generated in this repository for zero-effort onboarding.",
            "",
        ])

        content = "\n".join(lines)
        readme_file = Path(target_dir) / "README.md"
        safe_write_text(readme_file, content, root=target_dir)

        return content
