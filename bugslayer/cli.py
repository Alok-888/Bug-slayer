"""
Bug Slayer - Main Command Line Interface
"""

import sys
import os
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


def run_pipeline(target_dir: str):
    print_banner()
    target_path = Path(target_dir).resolve()

    if not target_path.exists():
        console.print(f"[bold red]Error:[/bold red] Target directory '{target_dir}' does not exist.")
        sys.exit(1)

    with console.status("[bold green]Inspecting codebase facts...", spinner="dots"):
        inspector = CodebaseInspector(str(target_path))
        facts = inspector.inspect()

    # Display Facts Table
    table = Table(title="🔍 Repository Inspection", box=box.ROUNDED)
    table.add_column("Property", style="bold cyan")
    table.add_column("Discovered Fact", style="white")

    table.add_row("Directory", facts["path"])
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

        # Test running the synthesized commands
        for cmd in plan.get("install_commands", []):
            console.print(f"[bold cyan]▶ Testing Install:[/bold cyan] `{cmd}`")
            res = executor.run(cmd)
            status_text = "[green]✔ OK[/green]" if res["success"] else "[yellow]⚠ Warning[/yellow]"
            console.print(f"  {status_text}")

        run_cmd = plan.get("run_command")
        if run_cmd and run_cmd != "echo 'No run command detected'":
            console.print(f"[bold cyan]▶ Testing Run Command:[/bold cyan] `{run_cmd}`")
            res = executor.run(run_cmd)
            status_text = "[green]✔ Verified server/app boots![/green]" if res["success"] else "[red]✘ Execution error[/red]"
            console.print(f"  {status_text}")

        # Write the README.md
        readme_content = DocumentationPatcher.generate_new_readme(str(target_path), plan)
        console.print("\n[bold green]🎉 Brand new verified README.md generated successfully![/bold green]")
        console.print(Panel(
            Syntax(readme_content, "markdown", theme="monokai", line_numbers=False),
            title="[green]README.md[/green]",
            border_style="green"
        ))


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    run_pipeline(target)
