"""
Bug Slayer - Documentation Patcher & Generator
Surgically updates existing READMEs, generates git diffs, and synthesizes
brand-new verified documentation.
"""

import difflib
from pathlib import Path
from typing import Dict, Any, Tuple


class DocumentationPatcher:
    @staticmethod
    def heal_readme(readme_path: str, old_cmd: str, new_cmd: str, explanation: str) -> Tuple[bool, str]:
        """
        Replaces the broken command with the working command in README.md
        and returns a unified diff string.
        """
        path = Path(readme_path)
        if not path.exists():
            return False, ""

        original_text = path.read_text(errors="ignore")
        if old_cmd not in original_text:
            return False, ""

        # Surgical replacement
        patched_text = original_text.replace(old_cmd, new_cmd)

        # Generate unified diff
        diff = list(difflib.unified_diff(
            original_text.splitlines(keepends=True),
            patched_text.splitlines(keepends=True),
            fromfile="a/README.md",
            tofile="b/README.md"
        ))

        # Write the patched file
        path.write_text(patched_text, encoding="utf-8")

        return True, "".join(diff)

    @staticmethod
    def generate_new_readme(target_dir: str, plan: Dict[str, Any]) -> str:
        """Generates a complete, beautiful README.md from an AI setup plan."""
        title = plan.get("project_title", "Project Documentation")
        desc = plan.get("description", "A modern project setup.")
        prereqs = plan.get("prerequisites", [])
        env_cmd = plan.get("env_setup")
        install_cmds = plan.get("install_commands", [])
        run_cmd = plan.get("run_command", "")
        test_cmd = plan.get("test_command")

        lines = [
            f"# {title}",
            "",
            "> 🛡️ *Setup instructions verified by [Bug Slayer](https://github.com/NSTSDC/bug-slayer).* ",
            "",
            desc,
            "",
            "## 📋 Prerequisites",
            ""
        ]

        if prereqs:
            for p in prereqs:
                lines.append(f"- {p}")
        else:
            lines.append("- Standard developer tools")

        lines.extend(["", "## 🚀 Quickstart Guide", ""])

        if env_cmd:
            lines.extend([
                "### 1. Configure Environment",
                "```bash",
                env_cmd,
                "```",
                ""
            ])

        step_num = 2 if env_cmd else 1
        if install_cmds:
            lines.extend([
                f"### {step_num}. Install Dependencies",
                "```bash",
                "\n".join(install_cmds),
                "```",
                ""
            ])
            step_num += 1

        if run_cmd:
            lines.extend([
                f"### {step_num}. Run the Application",
                "```bash",
                run_cmd,
                "```",
                ""
            ])
            step_num += 1

        if test_cmd:
            lines.extend([
                f"### {step_num}. Run Tests",
                "```bash",
                test_cmd,
                "```",
                ""
            ])

        content = "\n".join(lines)
        readme_file = Path(target_dir) / "README.md"
        readme_file.write_text(content, encoding="utf-8")

        return content
