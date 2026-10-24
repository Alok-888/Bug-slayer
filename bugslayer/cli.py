"""
Bug Slayer - Main Command Line Interface
Supports local repository paths AND direct remote GitHub URLs.

Usage:
    bugslayer <github-url-or-folder> [--local | --docker] [--model NAME] [--output DIR]
"""

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markup import escape as _e  # shows outside text literally (brackets are Rich formatting codes)
from rich.table import Table

from bugslayer.engine import AIEngine, ENVIRONMENT_ONLY, OFFLINE_SOURCE
from bugslayer.executor import CommandExecutor, choose_image, docker_status
from bugslayer.inspector import CodebaseInspector
from bugslayer.patcher import DocumentationPatcher
from bugslayer.safety import UnsafePathError, is_safe_to_read, safe_read_text, safe_write_text

# Windows terminals sometimes use a code page that cannot print emoji.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

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
    console.print("[dim italic]Autonomous Setup & Documentation Healer for Open-Source Repositories[/dim italic]\n")


def generate_setup_script(target_path: Path, commands: list, sections: list = None):
    """
    Generates an executable setup.sh script for 1-click execution.
    sections: optional [(folder, commands)] for READMEs in sub-folders; each
    section runs from its own folder.
    """
    script_path = target_path / "setup.sh"
    lines = [
        "#!/usr/bin/env bash",
        "# Auto-generated 1-click installer by Bug Slayer",
        "# Windows users: run this from Git Bash or WSL.",
        "set -e",
        "",
        "echo '🚀 Starting automated setup...'",
        "",
    ]
    if sections:
        lines[4:4] = ['BS_ROOT="$(pwd)"']
    for cmd in commands:
        safe = cmd.replace("'", "'\"'\"'")
        lines.append(f"echo '▶ Running: {safe}'")
        lines.append(cmd)
    for folder, section_cmds in sections or []:
        lines += ["", f"# --- {folder}/README.md", f'cd "$BS_ROOT/{folder}"', f"echo '📂 {folder}/'"]
        for cmd in section_cmds:
            safe = cmd.replace("'", "'\"'\"'")
            lines.append(f"echo '▶ Running: {safe}'")
            lines.append(cmd)
        lines.append('cd "$BS_ROOT"')
    lines.append("")
    lines.append("echo '✨ Setup completed successfully!'")

    safe_write_text(script_path, "\n".join(lines) + "\n", root=target_path, newline="\n")
    try:
        os.chmod(script_path, 0o755)
    except Exception:
        pass


def _remove_tree(path: str):
    """rmtree that also works on Windows, where git marks some files read-only."""
    def on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    shutil.rmtree(path, onerror=on_error)


def _repo_name(target: str) -> str:
    name = target.rstrip("/").split("/")[-1]
    name = re.sub(r"\.git$", "", name)
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "repository"


def _choose_sandbox(requested: str) -> str:
    """
    Decides where commands will run. Returns "docker" or "local", or "" to abort.
    Running a stranger's README on your own computer is risky, so local mode
    is only used when the user agrees.
    """
    if requested == "local":
        return "local"

    status = docker_status()
    if status["available"]:
        return "docker"

    if requested == "docker":
        console.print(f"[bold red]✘ Docker sandbox requested but unavailable:[/bold red] {_e(status['reason'])}")
        return ""

    console.print(Panel(
        f"{_e(status['reason'])}.\n\n"
        "Without Docker, README commands would run [bold]directly on this computer[/bold] "
        "(they can install packages or change files).\n\n"
        "• Recommended: install/open Docker Desktop and run again.\n"
        "• Or run with [bold]--local[/bold] to allow running on this computer.",
        title="[yellow]⚠ No isolated sandbox available[/yellow]",
        border_style="yellow",
    ))
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            answer = console.input("[bold]Run the README commands on this computer anyway? \\[y/N]: [/bold]")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer.strip().lower() in ("y", "yes"):
            return "local"
    console.print("[dim]Stopped without running anything.[/dim]")
    return ""


def _export_outputs(target_path: Path, out_dir: Path, readme_changed: bool, extra_readmes: list = None):
    """
    Copies the results out of the temporary clone before it is deleted.
    extra_readmes: relative paths of fixed READMEs in sub-folders, saved as
    VERIFIED_<folder>_README.md (e.g. VERIFIED_backend_README.md).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    readme = target_path / "README.md"
    if readme_changed and is_safe_to_read(readme, target_path) and not readme.is_symlink():
        dest = out_dir / "VERIFIED_README.md"
        shutil.copyfile(readme, dest)
        saved.append(("Verified README", dest))
    for rel in extra_readmes or []:
        src = target_path / rel
        if is_safe_to_read(src, target_path) and not src.is_symlink():
            dest = out_dir / ("VERIFIED_" + re.sub(r"[^A-Za-z0-9._-]", "_", rel))
            shutil.copyfile(src, dest)
            saved.append((f"Verified {rel}", dest))
    for name, label in (("fix-readme.patch", "PR patch"), ("setup.sh", "1-Click installer")):
        src = target_path / name
        if is_safe_to_read(src, target_path) and not src.is_symlink():
            dest = out_dir / name
            shutil.copyfile(src, dest)
            if name == "setup.sh":
                try:
                    os.chmod(dest, 0o755)
                except Exception:
                    pass
            saved.append((label, dest))
    return saved


def _resolve_readme(target_path: Path, readme: str):
    """Finds the README given with --readme (a path relative to the repository)."""
    rel = readme.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    candidate = (target_path / rel.lstrip("/")).resolve()
    try:
        candidate.relative_to(target_path)  # must stay inside the repository
    except ValueError:
        return None
    return str(candidate) if candidate.is_file() else None


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


def _print_all_readmes_summary(facts, process_root: bool, root_result, extra_results: list):
    """One table for repositories with several READMEs."""
    table = Table(title="📊 All READMEs", box=box.ROUNDED)
    for col in ("README", "Language", "Steps", "✔ Passed", "🛡️ Healed", "✘ Failed"):
        table.add_column(col, style="bold cyan" if col == "README" else "white")
    if process_root:
        name = os.path.basename(facts.get("readme_path") or "README.md")
        langs = ", ".join(facts["languages"]) or "Unknown"
        if root_result:
            table.add_row(_e(name), _e(langs), str(root_result["steps"]), str(root_result["passed"]),
                          str(root_result["healed"]), str(root_result["failed"]))
        else:
            table.add_row(_e(name), _e(langs), "-", "-", "-", "[cyan]new README written[/cyan]")
    for row in extra_results:
        if row["note"]:
            table.add_row(_e(row["name"]), _e(row["languages"]), str(row["steps"]), "-", "-", f"[yellow]{row['note']}[/yellow]")
        else:
            table.add_row(_e(row["name"]), _e(row["languages"]), str(row["steps"]), str(row["passed"]),
                          str(row["healed"]), str(row["failed"]))
    console.print()
    console.print(table)


def _heal_readme_steps(executor, engine, facts, target_path: Path, readme_text: str,
                       display_name: str = "README.md", context: str = "",
                       patch_paths: list = None) -> dict:
    """
    Mode 1 for one README: runs its steps, diagnoses failures, verifies fixes
    and patches the README. Used for the main README and, unchanged, for each
    extra README in a sub-folder.

    patch_paths: README files whose changes go into fix-readme.patch
    (default: just this README).
    """
    verified_commands = []
    readme_changed = False
    passed = failed = healed = 0
    patch_paths = patch_paths if patch_paths is not None else [facts["readme_path"]]

    for idx, cmd_info in enumerate(facts["readme_commands"], 1):
        cmd = cmd_info["command"]
        console.print(f"[bold cyan]▶ Step {idx}:[/bold cyan] [white]`{_e(cmd)}`[/white]")

        with console.status(f"Running step {idx}...", spinner="bouncingBar"):
            res = executor.run(cmd)

        if res["success"]:
            console.print("  [bold green]✔ Passed cleanly[/bold green] (Exit code 0)\n")
            verified_commands.append(cmd)
            passed += 1
            continue

        console.print(f"  [bold red]✘ FAILED (Exit code {res['exit_code']})[/bold red]")
        error_text = (res["stderr"] or res["stdout"] or "").strip()
        console.print(Panel(_e(error_text[-2000:]) or "Command failed with a non-zero exit code",
                            title="[red]Terminal Error[/red]", border_style="red"))

        # Invoke AI diagnosis
        label = engine.models[0] if engine.is_online else "offline rules"
        console.print(f"\n[bold magenta]🤖 Slaying the bug with {_e(label)}...[/bold magenta]")
        with console.status("Diagnosing root cause...", spinner="dots"):
            diagnosis = engine.diagnose_failure(cmd, error_text, facts, readme_text, context=context)

        explanation = diagnosis.get("explanation", "An error occurred during execution.")
        suggested_cmd = str(diagnosis.get("suggested_command") or cmd).strip()
        source = diagnosis.get("source", "unknown")
        env_only = diagnosis.get("root_cause_type") == ENVIRONMENT_ONLY

        if source == OFFLINE_SOURCE and engine.last_error:
            console.print(f"[yellow]⚠ AI unavailable ({_e(str(engine.last_error))}). Using offline rules.[/yellow]")

        console.print(Panel(
            f"[bold white]Diagnosis:[/bold white] {_e(explanation)}\n\n"
            f"[bold green]Suggested Fix:[/bold green] [bold yellow]`{_e(suggested_cmd)}`[/bold yellow]",
            title=f"[magenta]Diagnosis by {_e(source)}[/magenta]",
            border_style="magenta",
        ))

        if suggested_cmd == cmd:
            console.print("  [bold red]No different command to try. Manual fix needed - stopping here.[/bold red]\n")
            failed += 1
            break

        console.print(f"\n[bold cyan]🔁 Verifying suggested fix:[/bold cyan] [white]`{_e(suggested_cmd)}`[/white]")
        with console.status("Verifying fix...", spinner="bouncingBar"):
            test_res = executor.run(suggested_cmd)

        if not test_res["success"]:
            console.print("  [bold red]Suggested fix also failed. Manual fix needed - stopping here.[/bold red]\n")
            failed += 1
            break

        console.print("  [bold green]✔ Fix verified successfully![/bold green]\n")
        verified_commands.append(suggested_cmd)

        if env_only:
            console.print(Panel(
                "The README is fine for other computers. This failure only happens on this "
                "machine, so the README was [bold]not[/bold] changed.\n"
                f"On this machine use: [bold yellow]{_e(suggested_cmd)}[/bold yellow]",
                title="[cyan]ℹ Machine-specific difference[/cyan]",
                border_style="cyan",
            ))
            passed += 1
            continue

        new_raw = cmd_info["raw"].replace(cmd, suggested_cmd, 1)
        ok, diff = DocumentationPatcher.heal_readme(
            facts["readme_path"], cmd_info["raw"], new_raw, explanation,
            line_number=cmd_info.get("line"), display_name=display_name,
        )
        if ok and diff:
            readme_changed = True
            healed += 1
            console.print(Panel(
                Syntax(diff, "diff", theme="monokai", line_numbers=True),
                title=f"[green]🛡️ Patched {_e(display_name)} (Unified Diff)[/green]",
                border_style="green",
            ))
            patch_file = target_path / "fix-readme.patch"
            existing = safe_read_text(patch_file, target_path)
            # Re-diff the whole file against git so several fixes become one patch.
            try:
                safe_write_text(patch_file, _full_patch(target_path, patch_paths) or (existing + diff),
                                root=target_path, newline="\n")
            except UnsafePathError as e:
                console.print(f"[yellow]⚠ Did not write fix-readme.patch: {_e(str(e))}[/yellow]")
            console.print("[bold green]✨ Documentation healed and verified![/bold green]\n")

    console.print(Panel(
        f"[green]✔ {passed} passed[/green]   [cyan]🛡️ {healed} healed[/cyan]   "
        f"[red]✘ {failed} need a manual fix[/red]   of {len(facts['readme_commands'])} steps",
        title="[bold]Summary[/bold]", border_style="white",
    ))
    return {"verified_commands": verified_commands, "readme_changed": readme_changed,
            "passed": passed, "healed": healed, "failed": failed,
            "steps": len(facts["readme_commands"])}


def run_pipeline(target: str, sandbox: str = "auto", model: str = None, output: str = None,
                 readme: str = None, max_readmes: int = 10) -> int:
    """Runs Bug Slayer on a GitHub URL or local folder. Returns an exit code."""
    print_banner()

    is_remote = target.startswith(("http://", "https://", "git@")) or target.endswith(".git")
    temp_dir = None
    executor = None

    try:
        # ---------------------------------------------------------- 1. Get the code
        if is_remote:
            if not shutil.which("git"):
                console.print("[bold red]Error:[/bold red] git is not installed, so the repository cannot be cloned.")
                return 1
            console.print(f"[bold cyan]🌐 Remote GitHub URL detected:[/bold cyan] [underline]{_e(target)}[/underline]")
            temp_dir = tempfile.mkdtemp(prefix="bugslayer_")
            with console.status("[bold green]Downloading repository...", spinner="dots"):
                try:
                    res = subprocess.run(
                        ["git", "clone", "--depth", "1", "--", target, temp_dir],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        stdin=subprocess.DEVNULL, timeout=180,
                    )
                except subprocess.TimeoutExpired:
                    console.print("[bold red]Cloning took longer than 3 minutes. Check your internet connection.[/bold red]")
                    return 1
            if res.returncode != 0:
                console.print(f"[bold red]Failed to clone remote repository:[/bold red]\n{_e(res.stderr)}")
                return 1
            target_path = Path(temp_dir).resolve()
            console.print("[bold green]✔ Downloaded into a temporary folder[/bold green]\n")
        else:
            target_path = Path(target).resolve()
            if not target_path.is_dir():
                console.print(f"[bold red]Error:[/bold red] Target directory '{_e(target)}' does not exist.")
                return 1

        # ---------------------------------------------------------- 2. Inspect
        with console.status("[bold green]Inspecting codebase facts...", spinner="dots"):
            inspector = CodebaseInspector(str(target_path))
            facts = inspector.inspect()

            # Extra READMEs in sub-folders (e.g. frontend/, backend/). With none,
            # everything below runs exactly as for a single-README repository.
            main_readme = facts.get("readme_path")
            process_root = True
            if readme:
                selected = _resolve_readme(target_path, readme)
                if selected is None:
                    console.print(f"[bold red]Error:[/bold red] README '{_e(readme)}' was not found in this repository.")
                    return 1
                if main_readme and _same_file(selected, main_readme):
                    extra_paths = []
                else:
                    process_root = False
                    extra_paths = [selected]
            else:
                extra_paths = inspector.find_extra_readmes(main_readme)
            skipped_extra = max(0, len(extra_paths) - max(0, max_readmes))
            extra_paths = extra_paths[:max(0, max_readmes)]
            extras = [inspector.inspect_readme(p) for p in extra_paths]
        all_readme_paths = ([main_readme] if main_readme and process_root else []) + [e["readme_path"] for e in extras]

        # ---------------------------------------------------------- 3. Sandbox
        mode = _choose_sandbox(sandbox)
        if not mode:
            return 2
        if mode == "docker":
            image = choose_image(facts["languages"])
            with console.status(f"[bold green]Preparing Docker sandbox ({_e(image)}) - the first run downloads it...", spinner="dots"):
                pulled = CommandExecutor.ensure_image(image)
            if not pulled["success"]:
                console.print(f"[bold red]Could not download the Docker image {_e(image)}:[/bold red]\n{_e(pulled['stderr'])}")
                return 1
            with console.status("[bold green]Starting sandbox...", spinner="dots"):
                executor = CommandExecutor(str(target_path), mode="docker", image=image)
        else:
            executor = CommandExecutor(str(target_path), mode="local")

        engine = AIEngine(model=model, environment=executor.environment_for_ai())

        # ---------------------------------------------------------- 4. Show facts
        table = Table(title="🔍 Repository Inspection", box=box.ROUNDED)
        table.add_column("Property", style="bold cyan")
        table.add_column("Discovered Fact", style="white")
        table.add_row("Repository", _e(target if is_remote else str(target_path)))
        table.add_row("Languages", _e(", ".join(facts["languages"])) if facts["languages"] else "Unknown")
        table.add_row("Package Manager", _e(facts["package_manager"] or "None detected"))
        table.add_row("Manifests", _e(", ".join(facts["manifest_files"])) if facts["manifest_files"] else "None")
        table.add_row("Entry Points", _e(", ".join(facts["entry_points"])) if facts["entry_points"] else "None")
        table.add_row("Env Variables", _e(", ".join(facts["env_variables"])) if facts["env_variables"] else "None detected")
        table.add_row("README Status", f"[green]Found ({len(facts['readme_commands'])} commands)[/green]" if facts["has_readme"] else "[red]Missing or empty[/red]")
        table.add_row("Runs In", f"[green]{_e(executor.describe())}[/green]" if mode == "docker" else f"[yellow]{_e(executor.describe())}[/yellow]")
        table.add_row("AI Engine", f"[green]{_e(engine.model_label)}[/green]" if engine.is_online else f"[yellow]{_e(engine.model_label)}[/yellow]")
        if extras:
            table.add_row("Other READMEs", _e("\n".join(
                f"{e['relative_path']} ({', '.join(e['languages']) or 'Unknown'})" for e in extras)))
        if not process_root:
            table.add_row("Main README", "[dim]skipped (--readme chose another README)[/dim]")
        if skipped_extra:
            table.add_row("Not checked", f"[yellow]{skipped_extra} more README(s) over the --max-readmes limit[/yellow]")
        console.print(table)
        console.print()

        verified_commands = []
        readme_changed = False
        readme_text = ""
        if facts.get("readme_path"):
            readme_text = safe_read_text(facts["readme_path"], target_path)

        # ---------------------------------------------------------- 5a. Healer mode
        root_result = None
        if process_root and facts["has_readme"] and facts["readme_commands"]:
            console.print("[bold yellow]⚔️ Mode 1: Verifying README Setup Instructions...[/bold yellow]\n")
            root_result = _heal_readme_steps(executor, engine, facts, target_path, readme_text,
                                             patch_paths=all_readme_paths or None)
            verified_commands = root_result["verified_commands"]
            readme_changed = root_result["readme_changed"]

        # ---------------------------------------------------------- 5b. Architect mode
        elif process_root:
            console.print("[bold yellow]🏛️ Mode 2: No Setup Documentation Found. Synthesizing from Scratch...[/bold yellow]\n")
            with console.status("Synthesizing setup & run instructions...", spinner="dots"):
                plan = engine.generate_guide(facts)
            if plan.get("source") == OFFLINE_SOURCE and engine.last_error:
                console.print(f"[yellow]⚠ AI unavailable ({_e(str(engine.last_error))}). Using offline rules.[/yellow]")

            console.print(Panel(
                f"[bold cyan]Title:[/bold cyan] {_e(str(plan.get('project_title')))}\n"
                f"[bold cyan]Prerequisites:[/bold cyan] {_e(', '.join(map(str, plan.get('prerequisites') or [])))}\n"
                f"[bold cyan]Install:[/bold cyan] {_e(', '.join(map(str, plan.get('install_commands') or [])))}\n"
                f"[bold cyan]Run Command:[/bold cyan] {_e(str(plan.get('run_command')))}",
                title=f"[cyan]Synthesized Blueprint (by {_e(str(plan.get('source', 'unknown')))})[/cyan]",
                border_style="cyan",
            ))

            env_setup = plan.get("env_setup")
            if env_setup and not str(env_setup).startswith("#"):
                res = executor.run(env_setup)
                console.print(f"[bold cyan]▶ Environment:[/bold cyan] `{_e(str(env_setup))}`  " + ("[green]✔ OK[/green]" if res["success"] else "[yellow]⚠ Warning[/yellow]"))
                verified_commands.append(env_setup)

            for cmd in plan.get("install_commands") or []:
                console.print(f"[bold cyan]▶ Testing Install:[/bold cyan] `{_e(str(cmd))}`")
                with console.status("Installing...", spinner="bouncingBar"):
                    res = executor.run(_host_python(cmd, mode))
                console.print("  [green]✔ OK[/green]" if res["success"] else f"  [yellow]⚠ Warning:[/yellow] {_e((res['stderr'] or '').strip()[:200])}")
                verified_commands.append(cmd)

            run_cmd = plan.get("run_command")
            if run_cmd and run_cmd != "echo 'No run command detected'":
                console.print(f"[bold cyan]▶ Testing Run Command:[/bold cyan] `{_e(str(run_cmd))}`")
                with console.status("Starting the app...", spinner="bouncingBar"):
                    res = executor.run(_host_python(run_cmd, mode))
                console.print("  [green]✔ Verified server/app boots![/green]" if res["success"] else f"  [red]✘ Execution error:[/red] {_e((res['stderr'] or '').strip()[:200])}")
                verified_commands.append(run_cmd)

            try:
                readme_content = DocumentationPatcher.generate_new_readme(str(target_path), plan)
                readme_changed = True
                console.print("\n[bold green]🎉 Brand new verified README.md generated successfully![/bold green]")
            except UnsafePathError as e:
                console.print(f"[bold red]⚠ Did not write README.md: {_e(str(e))}[/bold red] "
                              "[red](this repository may be trying to overwrite a file on your computer)[/red]")
                return 1
            console.print(Panel(
                Syntax(readme_content, "markdown", theme="monokai", line_numbers=False),
                title="[green]README.md[/green]",
                border_style="green",
            ))

        # ---------------------------------------------------------- 5c. Extra READMEs
        extra_results, extra_sections, extra_changed = [], [], []
        main_environment = engine.environment
        for ef in extras:
            rel, folder = ef["relative_path"], ef["relative_folder"]
            langs = ", ".join(ef["languages"]) or "Unknown"
            row = {"name": rel, "languages": langs, "steps": len(ef["readme_commands"]),
                   "passed": 0, "healed": 0, "failed": 0, "note": ""}
            console.print(f"\n[bold yellow]📄 Checking {_e(rel)}[/bold yellow] [dim]({_e(langs)})[/dim]\n")
            if not ef["readme_commands"]:
                console.print("[dim]No setup commands in this README - nothing to test.[/dim]")
                row["note"] = "no commands"
                extra_results.append(row)
                continue

            sub_executor = None
            try:
                if mode == "docker":
                    sub_image = choose_image(ef["languages"])
                    with console.status(f"[bold green]Preparing Docker sandbox ({_e(sub_image)})...", spinner="dots"):
                        pulled = CommandExecutor.ensure_image(sub_image)
                    if not pulled["success"]:
                        console.print(f"[bold red]Could not download the Docker image {_e(sub_image)}:[/bold red]\n{_e(pulled['stderr'])}")
                        row["note"] = "sandbox image unavailable"
                        extra_results.append(row)
                        continue
                    with console.status("[bold green]Starting a fresh sandbox...", spinner="dots"):
                        sub_executor = CommandExecutor(str(target_path), mode="docker", image=sub_image, start_in=folder)
                else:
                    sub_executor = CommandExecutor(str(target_path), mode="local", start_in=folder)
                console.print(f"[dim]Runs in: {_e(sub_executor.describe())}, starting in {_e(folder)}/[/dim]\n")

                engine.environment = sub_executor.environment_for_ai()
                result = _heal_readme_steps(
                    sub_executor, engine, ef, target_path,
                    safe_read_text(ef["readme_path"], target_path),
                    display_name=rel,
                    context=f"This is {rel}, a {langs} project in the folder {folder}/ of the repository.",
                    patch_paths=all_readme_paths,
                )
                row.update({k: result[k] for k in ("passed", "healed", "failed")})
                if result["verified_commands"]:
                    extra_sections.append((folder, result["verified_commands"]))
                if result["readme_changed"]:
                    extra_changed.append(rel)
            except RuntimeError as e:
                console.print(f"[bold red]Could not test {_e(rel)}:[/bold red] {_e(str(e))}")
                row["note"] = "sandbox failed to start"
            finally:
                if sub_executor:
                    sub_executor.close()
                engine.environment = main_environment
            extra_results.append(row)

        if extras:
            _print_all_readmes_summary(facts, process_root, root_result, extra_results)

        # ---------------------------------------------------------- 6. Outputs
        if verified_commands or extra_sections:
            try:
                generate_setup_script(target_path, verified_commands, sections=extra_sections)
                console.print("[bold green]⚡ Generated 1-Click Installer:[/bold green] `setup.sh`")
            except UnsafePathError as e:
                console.print(f"[bold red]⚠ Did not write setup.sh: {_e(str(e))}[/bold red] "
                              "[red](this repository may be trying to overwrite a file on your computer)[/red]")

        if is_remote:
            out_dir = Path(output) if output else Path.cwd() / "bugslayer_output" / _repo_name(target)
            saved = _export_outputs(target_path, out_dir.resolve(), readme_changed, extra_readmes=extra_changed)
            if saved:
                console.print(Panel(
                    "\n".join(f"{_e(label)}: [bold yellow]{_e(str(path))}[/bold yellow]" for label, path in saved),
                    title="[bold green]📦 Results saved[/bold green]",
                    border_style="green",
                ))
        else:
            console.print(f"[dim]Results were written into {_e(str(target_path))}[/dim]")
        console.print()
        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped by user.[/yellow]")
        return 130
    finally:
        if executor:
            executor.close()
        if temp_dir and os.path.exists(temp_dir):
            _remove_tree(temp_dir)


def _host_python(cmd: str, mode: str) -> str:
    """On local Windows, `python3` usually does not exist; run `python` instead."""
    if mode == "local" and sys.platform.startswith("win") and cmd.startswith("python3 "):
        return "python " + cmd[len("python3 "):]
    return cmd


def _full_patch(repo: Path, readme_path) -> str:
    """
    git diff of the README(s) if the folder is a git repo, so all fixes are in
    one patch. readme_path: one path, or a list of paths.
    """
    try:
        paths = [readme_path] if isinstance(readme_path, (str, Path)) else list(readme_path)
        rels = [os.path.relpath(p, repo) for p in paths]
        res = subprocess.run(["git", "-C", str(repo), "diff", "--", *rels], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=30)
        return res.stdout if res.returncode == 0 else ""
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(
        prog="bugslayer",
        description="Runs a repository's README setup steps, finds what breaks, and heals it with Gemma AI.",
    )
    parser.add_argument("target", nargs="?", default=".", help="GitHub URL or local project folder (default: current folder)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--docker", action="store_const", const="docker", dest="sandbox",
                       help="require the Docker sandbox (stop if Docker is not running)")
    group.add_argument("--local", action="store_const", const="local", dest="sandbox",
                       help="run commands directly on this computer (not isolated)")
    parser.add_argument("--model", help="AI model to use (default: gemma-4-26b-a4b-it)")
    parser.add_argument("--output", help="folder for results of a remote run (default: ./bugslayer_output/<repo>)")
    parser.add_argument("--readme", help="check only this README, e.g. backend/README.md (default: the main README "
                                         "plus READMEs found in sub-folders)")
    parser.add_argument("--max-readmes", type=int, default=10,
                        help="most READMEs in sub-folders to check (default: 10)")
    args = parser.parse_args()
    sys.exit(run_pipeline(args.target, sandbox=args.sandbox or "auto", model=args.model, output=args.output,
                          readme=args.readme, max_readmes=args.max_readmes))


if __name__ == "__main__":
    main()
