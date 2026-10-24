"""
Bug Slayer - Documentation Patcher & Generator
Surgically updates existing READMEs, generates git diffs, and synthesizes
brand-new verified documentation.
"""

import difflib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


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
        if not path.exists():
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
            "> 🛡️ *Setup instructions verified by [Bug Slayer](https://github.com/chauhanalok546-rgb/Bug-slayer).* ",
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

        all_cmds = [c for c in [env_cmd, *install_cmds, run_cmd, test_cmd] if c]
        if any(str(c).startswith(("python3 ", "pip3 ")) for c in all_cmds):
            lines.extend([
                "> 🪟 **Windows users:** type `python` instead of `python3`.",
                "",
            ])

        content = "\n".join(lines)
        readme_file = Path(target_dir) / "README.md"
        readme_file.write_text(content, encoding="utf-8")

        return content
