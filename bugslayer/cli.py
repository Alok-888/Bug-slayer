"""
Bug Slayer - Main Command Line Interface
Supports local repository paths AND direct remote GitHub URLs.
"""

import sys
import os
import shutil
import tempfile
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich import box

from bugslayer.inspector import CodebaseInspector
from bugslayer.engine import AIEngine
from bugslayer.executor import CommandExecutor
from bugslayer.patcher import DocumentationPatcher

console = Console()


def print_banner():
    banner = """
[bold red]██████╗ ██╗   ██╗ ██████╗     ███████╗██╗      █████╗ ██╗   ██╗███████╗██████╗ [/bold red]
[bold red]██╔══██╗██║   ██║██╔════╝     ██╔════╝██║     ██╔══██╗╚██╗ ██╔╝██╔════╝██╔══██╗[/bold red]
[bold white]██████╔╝██║   ██║██║  ███╗    ███████╗██║     ███████║ ╚████╔╝ █████╗  ██████╔╝[/bold white]
[bold white]██╔══██╗██║   ██║██║   ██║    ╚════██║██║     ██╔══██║  ╚██╔╝  ██╔══╝  ██╔══██╗[/bold white]
[bold cyan]██████╔╝╚██████╔╝╚██████╔╝    ███████║███████╗██║  ██║   ██║   ███████╗██║  ██║[/bold cyan]
[bold cyan]╚═════╝  ╚═════╝  ╚═════╝     ╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝[/bold cyan]
    """
    console.print(banner)
    console.print("[dim italic center]Autonomous Setup & Documentation Healer for Open-Source Repositories[/dim italic center]\n")


def generate_setup_script(target_path: Path, commands: list):
    """Generates an executable setup.sh script for 1-click execution."""
    script_path = target_path / "setup.sh"
    lines = [
        "#!/usr/bin/env bash",
        "# Auto-generated 1-click installer by Bug Slayer",
        "set -e",
        "",
        "echo '🚀 Starting automated setup...'",
        ""
    ]
    for cmd in commands:
        lines.append(f"echo '▶ Running: {cmd}'")
        lines.append(cmd)
    lines.append("")
    lines.append("echo '✨ Setup completed successfully!'")

    script_path.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(script_path, 0o755)
    except Exception:
        pass


def run_pipeline(target: str):
    print_banner()

    is_remote = target.startswith("http://") or target.startswith("https://") or target.endswith(".git")
    temp_dir = None

    if is_remote:
        console.print(f"[bold cyan]🌐 Remote GitHub URL detected:[/bold cyan] [underline]{target}[/underline]")
        temp_dir = tempfile.mkdtemp(prefix="bugslayer_")
        with console.status("[bold green]Cloning repository for sandboxed verification...", spinner="dots"):
            res = subprocess.run(["git", "clone", "--depth", "1", target, temp_dir], capture_output=True, text=True)
            if res.returncode != 0:
                console.print(f"[bold red]Failed to clone remote repository:[/bold red]\n{res.stderr}")
                return
        target_path = Path(temp_dir).resolve()
        console.print(f"[bold green]✔ Cloned successfully into sandbox:[/bold green] {target_path}\n")
    else:
        target_path = Path(target).resolve()
        if not target_path.exists():
            console.print(f"[bold red]Error:[/bold red] Target directory '{target}' does not exist.")
            sys.exit(1)

    try:
        with console.status("[bold green]Inspecting codebase facts...", spinner="dots"):
            inspector = CodebaseInspector(str(target_path))
            facts = inspector.inspect()

        # Display Facts Table
        table = Table(title="🔍 Repository Inspection", box=box.ROUNDED)
        table.add_column("Property", style="bold cyan")
        table.add_column("Discovered Fact", style="white")

        table.add_row("Directory", str(target_path))
        table.add_row("Languages", ", ".join(facts["languages"]) if facts["languages"] else "Unknown")
        table.add_row("Package Manager", facts["package_manager"] or "None detected")
        table.add_row("Manifests", ", ".join(facts["manifest_files"]) if facts["manifest_files"] else "None")
        table.add_row("Entry Points", ", ".join(facts["entry_points"]) if facts["entry_points"] else "None")
        table.add_row("Env Variables", ", ".join(facts["env_variables"]) if facts["env_variables"] else "None detected")
        table.add_row("README Status", f"[green]Found ({len(facts['readme_commands'])} commands)[/green]" if facts["has_readme"] else "[red]Missing or empty[/red]")

        console.print(table)
        console.print()

        engine = AIEngine()
        executor = CommandExecutor(str(target_path))
        verified_commands = []

        # SCENARIO 1: Existing README with commands (Healer Mode)
        if facts["has_readme"] and facts["readme_commands"]:
            console.print("[bold yellow]⚔️ Mode 1: Verifying README Setup Instructions...[/bold yellow]\n")

            for idx, cmd_info in enumerate(facts["readme_commands"], 1):
                cmd = cmd_info["command"]
                console.print(f"[bold cyan]▶ Step {idx}:[/bold cyan] [white]`{cmd}`[/white]")

                with console.status(f"Running step {idx}...", spinner="bouncingBar"):
                    res = executor.run(cmd)

                if res["success"]:
                    console.print(f"  [bold green]✔ Passed cleanly[/bold green] (Exit code 0)\n")
                    verified_commands.append(cmd)
                else:
                    console.print(f"  [bold red]✘ FAILED (Exit code {res['exit_code']})[/bold red]")
                    console.print(Panel(res["stderr"].strip() or "Command failed with non-zero exit code", title="[red]Terminal Error[/red]", border_style="red"))

                    # Invoke AI Diagnosis
                    console.print("\n[bold magenta]🤖 Slaying the bug with Gemma AI...[/bold magenta]")
                    with console.status("Diagnosing root cause...", spinner="dots"):
                        diagnosis = engine.diagnose_failure(cmd, res["stderr"], facts)

                    explanation = diagnosis.get("explanation", "An error occurred during execution.")
                    suggested_cmd = diagnosis.get("suggested_command", cmd)

                    console.print(Panel(
                        f"[bold white]Diagnosis:[/bold white] {explanation}\n\n[bold green]Suggested Fix:[/bold green] [bold yellow]`{suggested_cmd}`[/bold yellow]",
                        title="[magenta]Gemma AI Diagnosis[/magenta]",
                        border_style="magenta"
                    ))

                    # Verify the fix
                    console.print(f"\n[bold cyan]🔁 Verifying suggested fix:[/bold cyan] [white]`{suggested_cmd}`[/white]")
                    with console.status("Verifying fix...", spinner="bouncingBar"):
                        test_res = executor.run(suggested_cmd)

                    if test_res["success"]:
                        console.print(f"  [bold green]✔ Fix verified successfully![/bold green]\n")
                        verified_commands.append(suggested_cmd)
                        # Heal the README
                        healed, diff = DocumentationPatcher.heal_readme(
                            facts["readme_path"],
                            cmd_info["raw"],
                            suggested_cmd,
                            explanation
                        )
                        if healed and diff:
                            console.print(Panel(
                                Syntax(diff, "diff", theme="monokai", line_numbers=True),
                                title="[green]🛡️ Patched README.md (Unified Diff)[/green]",
                                border_style="green"
                            ))
                            # Write patch file
                            patch_file = target_path / "fix-readme.patch"
                            patch_file.write_text(diff, encoding="utf-8")
                            console.print(f"[bold green]✨ Exported PR patch to:[/bold green] `{patch_file.name}`")
                            console.print("[bold green]✨ Documentation successfully healed and verified![/bold green]\n")
                    else:
                        console.print(f"  [bold red]Suggested fix also failed. Manual intervention needed.[/bold red]\n")

        # SCENARIO 2: No README / Zero Documentation (Architect Mode)
        else:
            console.print("[bold yellow]🏛️ Mode 2: No Setup Documentation Found. Synthesizing from Scratch...[/bold yellow]\n")
            with console.status("Gemma is synthesizing setup & run instructions...", spinner="dots"):
                plan = engine.generate_guide(facts)

            console.print(Panel(
                f"[bold cyan]Title:[/bold cyan] {plan.get('project_title')}\n"
                f"[bold cyan]Prerequisites:[/bold cyan] {', '.join(plan.get('prerequisites', []))}\n"
                f"[bold cyan]Install:[/bold cyan] {', '.join(plan.get('install_commands', []))}\n"
                f"[bold cyan]Run Command:[/bold cyan] {plan.get('run_command')}",
                title="[cyan]Synthesized Blueprint[/cyan]",
                border_style="cyan"
            ))

            if plan.get("env_setup"):
                verified_commands.append(plan["env_setup"])

            # Test running the synthesized commands
            for cmd in plan.get("install_commands", []):
                console.print(f"[bold cyan]▶ Testing Install:[/bold cyan] `{cmd}`")
                res = executor.run(cmd)
                status_text = "[green]✔ OK[/green]" if res["success"] else "[yellow]⚠ Warning[/yellow]"
                console.print(f"  {status_text}")
                verified_commands.append(cmd)

            run_cmd = plan.get("run_command")
            if run_cmd and run_cmd != "echo 'No run command detected'":
                console.print(f"[bold cyan]▶ Testing Run Command:[/bold cyan] `{run_cmd}`")
                res = executor.run(run_cmd)
                status_text = "[green]✔ Verified server/app boots![/green]" if res["success"] else "[red]✘ Execution error[/red]"
                console.print(f"  {status_text}")
                verified_commands.append(run_cmd)

            # Write the README.md
            readme_content = DocumentationPatcher.generate_new_readme(str(target_path), plan)
            console.print("\n[bold green]🎉 Brand new verified README.md generated successfully![/bold green]")
            console.print(Panel(
                Syntax(readme_content, "markdown", theme="monokai", line_numbers=False),
                title="[green]README.md[/green]",
                border_style="green"
            ))

        # Generate 1-Click Setup Script
        if verified_commands:
            generate_setup_script(target_path, verified_commands)
            console.print(f"[bold green]⚡ Generated 1-Click Installer:[/bold green] `setup.sh` in the repository!\n")

        # If it was a remote URL, copy the fixed README/setup.sh to current directory so user can see it!
        if is_remote:
            result_readme = target_path / "README.md"
            if result_readme.exists():
                local_export = Path.cwd() / "VERIFIED_README.md"
                local_export.write_text(result_readme.read_text(errors="ignore"), encoding="utf-8")
                console.print(Panel(
                    f"Saved verified documentation to: [bold yellow]{local_export}[/bold yellow]",
                    title="[bold green]📦 Remote Verification Saved Locally[/bold green]",
                    border_style="green"
                ))

            result_setup = target_path / "setup.sh"
            if result_setup.exists():
                local_setup = Path.cwd() / "setup.sh"
                local_setup.write_text(result_setup.read_text(errors="ignore"), encoding="utf-8")
                try:
                    os.chmod(local_setup, 0o755)
                except Exception:
                    pass
                console.print(f"[bold green]⚡ Saved 1-Click Installer locally to:[/bold green] [bold yellow]{local_setup}[/bold yellow]\n")

    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    run_pipeline(target)


if __name__ == "__main__":
    main()

