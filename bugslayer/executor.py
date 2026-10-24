"""
Bug Slayer - Execution Harness
Runs README commands the way a beginner would type them into one terminal.

Two modes:
  * docker (preferred): every step runs inside a throwaway Linux container that
    holds a COPY of the repository. Nothing touches the user's computer, and
    results are the same on macOS, Windows and Linux.
  * local (fallback): steps run directly on this machine. Works on macOS,
    Linux and Windows, but is NOT isolated.

Between steps the harness remembers the current folder (`cd backend`) and, on
bash, exported variables (`export PORT=3000`, `source venv/bin/activate`).
"""

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

IS_WINDOWS = sys.platform.startswith("win")

# Generous default: real `pip install` / `npm install` steps often take minutes.
DEFAULT_TIMEOUT = int(os.environ.get("BUGSLAYER_TIMEOUT", "300"))
# How long a server must stay alive to count as "booted".
SERVER_WAIT = float(os.environ.get("BUGSLAYER_SERVER_WAIT", "4"))

SERVER_PATTERN = re.compile(
    r"\b(npm|yarn|pnpm|bun)\s+(run\s+)?(dev|start|serve)\b"
    r"|\buvicorn\b|\bgunicorn\b|\bflask\s+run\b|\bmanage\.py\s+runserver\b"
    r"|\bpython3?\s+(app|server|main|run)\.py\b"
    r"|\bdocker[- ]compose\s+up\b(?!.*\s-d\b)",
    re.IGNORECASE,
)

PWD_MARKER = "__BUGSLAYER_PWD__"

# A server whose process is still alive can still be broken: auto-reload
# watchers (uvicorn --reload, nodemon, flask --debug) keep running after the
# app itself crashes. These messages mean the app did NOT start.
SERVER_CRASH_PATTERN = re.compile(
    r"Traceback \(most recent call last\)"
    r"|Error loading ASGI app|Could not import module"
    r"|ModuleNotFoundError|ImportError:|SyntaxError:"
    r"|Cannot find module|ERR_MODULE_NOT_FOUND|EADDRINUSE|Address already in use"
    r"|\[nodemon\] app crashed|UnhandledPromiseRejection",
)


def _crashed(log_text: str) -> bool:
    return bool(SERVER_CRASH_PATTERN.search(log_text or ""))

# Makes installers non-interactive so a step can never hang waiting for input.
NONINTERACTIVE_ENV = {
    "CI": "1",
    "DEBIAN_FRONTEND": "noninteractive",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PIP_NO_INPUT": "1",
    "PYTHONUNBUFFERED": "1",
    "npm_config_yes": "true",
    "npm_config_fund": "false",
    "npm_config_audit": "false",
}

DOCKER_IMAGES = {
    "JavaScript/TypeScript": "node:20",
    "Python": "python:3.12",
    "Go": "golang:1.23",
    "Rust": "rust:1",
}


def _result(success: bool, code: int, stdout: str = "", stderr: str = "") -> Dict[str, Any]:
    return {"success": success, "exit_code": code, "stdout": stdout or "", "stderr": stderr or ""}


def _run(args, timeout: Optional[float] = 60, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run with UTF-8 decoding that can never crash on odd bytes."""
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL, timeout=timeout, **kwargs,
    )


def docker_status() -> Dict[str, Any]:
    """Returns {"available": bool, "reason": str}."""
    if not shutil.which("docker"):
        return {"available": False, "reason": "Docker is not installed"}
    try:
        info = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=15)
    except Exception as e:
        return {"available": False, "reason": f"Docker did not respond ({e})"}
    if info.returncode != 0:
        return {"available": False, "reason": "Docker is installed but not running (open Docker Desktop)"}
    return {"available": True, "reason": f"Docker {info.stdout.strip()}"}


def choose_image(languages: List[str]) -> str:
    override = os.environ.get("BUGSLAYER_IMAGE")
    if override:
        return override
    for lang in ["JavaScript/TypeScript", "Python", "Go", "Rust"]:
        if lang in (languages or []):
            return DOCKER_IMAGES[lang]
    return DOCKER_IMAGES["Python"]


def looks_like_server(command: str) -> bool:
    return bool(SERVER_PATTERN.search(command))


def _bash_step_script(command: str, env_file: str) -> str:
    """
    Wraps one README step so that exported variables and the final folder are
    carried over to the next step. The command's real exit code is preserved.
    """
    return (
        f'[ -f "{env_file}" ] && . "{env_file}" >/dev/null 2>&1\n'
        f"{command}\n"
        "__bs_rc=$?\n"
        f'export -p > "{env_file}" 2>/dev/null\n'
        f'echo "{PWD_MARKER}$(pwd)"\n'
        "exit $__bs_rc\n"
    )


def _split_marker(stdout: str):
    """Removes the folder marker from output; returns (clean_stdout, folder or None)."""
    folder, lines = None, []
    for line in stdout.splitlines():
        if line.startswith(PWD_MARKER):
            folder = line[len(PWD_MARKER):].strip()
        else:
            lines.append(line)
    return "\n".join(lines), folder


class CommandExecutor:
    """
    Usage:
        with CommandExecutor(path, mode="auto", languages=["Python"]) as ex:
            ex.run("pip install -r requirements.txt")
    """

    def __init__(self, working_dir: str, mode: str = "local", languages: Optional[List[str]] = None,
                 image: Optional[str] = None):
        self.root_dir = os.path.abspath(working_dir)
        self.mode = mode
        self.image = image or choose_image(languages or [])
        self.container: Optional[str] = None
        self._state_dir = tempfile.mkdtemp(prefix="bugslayer_state_")
        self._env_file = os.path.join(self._state_dir, "env.sh").replace("\\", "/")
        self.cwd = self.root_dir

        if self.mode == "docker":
            self._start_container()
            self.cwd = "/work"

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def describe(self) -> str:
        if self.mode == "docker":
            return f"Docker sandbox ({self.image}) - isolated"
        os_name = "Windows" if IS_WINDOWS else ("macOS" if sys.platform == "darwin" else "Linux")
        return f"Local {os_name} machine - NOT isolated"

    def environment_for_ai(self) -> str:
        if self.mode == "docker":
            return f"a clean Linux Docker container (image {self.image}), running as root, bash shell"
        if IS_WINDOWS:
            return "a local Windows machine (cmd.exe shell)"
        return f"a local {'macOS' if sys.platform == 'darwin' else 'Linux'} machine (bash shell)"

    def close(self):
        if self.container:
            try:
                _run(["docker", "rm", "-f", self.container], timeout=30)
            except Exception:
                pass
            self.container = None
        shutil.rmtree(self._state_dir, ignore_errors=True)

    @staticmethod
    def ensure_image(image: str) -> Dict[str, Any]:
        """Downloads the image if it is not on this computer yet (first run only)."""
        if _run(["docker", "image", "inspect", image], timeout=30).returncode == 0:
            return _result(True, 0, "cached")
        pull = _run(["docker", "pull", image], timeout=900)
        return _result(pull.returncode == 0, pull.returncode, pull.stdout[-500:], pull.stderr[-1000:])

    def _start_container(self):
        name = f"bugslayer-{uuid.uuid4().hex[:10]}"
        start = _run([
            "docker", "run", "-d", "--rm", "--name", name,
            "--memory", "2g", "--cpus", "2", "--pids-limit", "512",
            "-w", "/work", "--entrypoint", "sleep", self.image, "infinity",
        ], timeout=120)
        if start.returncode != 0:
            raise RuntimeError(f"Could not start the Docker sandbox: {start.stderr.strip()[:300]}")
        self.container = start.stdout.strip() or name
        # The harness keeps its state files in /tmp; make sure it exists in any image.
        _run(["docker", "exec", self.container, "mkdir", "-p", "/tmp", "/work"], timeout=30)
        _run(["docker", "exec", self.container, "chmod", "1777", "/tmp"], timeout=30)
        # Copy (not mount) the repository, so the user's files are never modified.
        copy = _run(["docker", "cp", os.path.join(self.root_dir, "."), f"{self.container}:/work"], timeout=300)
        if copy.returncode != 0:
            self.close()
            raise RuntimeError(f"Could not copy the repository into the sandbox: {copy.stderr.strip()[:300]}")

    # ------------------------------------------------------------------ #
    # Running steps
    # ------------------------------------------------------------------ #
    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT, is_server: bool = False) -> Dict[str, Any]:
        """
        Executes one README step. Commands that start a server (npm run dev,
        uvicorn, ...) count as successful if they stay alive for a few seconds.
        """
        server = is_server or looks_like_server(command)
        try:
            if self.mode == "docker":
                return self._docker_server(command) if server else self._docker_once(command, timeout)
            if IS_WINDOWS:
                return self._windows_server(command) if server else self._windows_once(command, timeout)
            return self._posix_server(command) if server else self._posix_once(command, timeout)
        except subprocess.TimeoutExpired:
            return _result(False, -1, "", f"Command timed out after {timeout} seconds.")
        except Exception as e:
            return _result(False, -1, "", str(e))

    # ----- Docker -------------------------------------------------------
    def _docker_exec(self, args: List[str], timeout: Optional[float], detach: bool = False):
        cmd = ["docker", "exec"]
        if detach:
            cmd.append("-d")
        for k, v in NONINTERACTIVE_ENV.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += ["-w", self.cwd, self.container] + args
        return _run(cmd, timeout=timeout)

    def _docker_once(self, command: str, timeout: int) -> Dict[str, Any]:
        script = _bash_step_script(command, "/tmp/.bugslayer_env.sh")
        res = self._docker_exec(["bash", "-c", script], timeout=timeout)
        stdout, folder = _split_marker(res.stdout)
        if res.returncode == 0 and folder:
            self.cwd = folder
        return _result(res.returncode == 0, res.returncode, stdout, res.stderr)

    def _docker_server(self, command: str) -> Dict[str, Any]:
        log, pid_file, rc_file = "/tmp/.bs_server.log", "/tmp/.bs_server.pid", "/tmp/.bs_server.rc"
        launcher = (
            f'rm -f {rc_file} {log} {pid_file}; '
            f'[ -f /tmp/.bugslayer_env.sh ] && . /tmp/.bugslayer_env.sh >/dev/null 2>&1; '
            f'setsid bash -c "$1" > {log} 2>&1 & echo $! > {pid_file}; '
            f'wait $!; echo $? > {rc_file}'
        )
        self._docker_exec(["bash", "-c", launcher, "bugslayer", command], timeout=30, detach=True)
        time.sleep(SERVER_WAIT)

        check = self._docker_exec(["bash", "-c", f"[ -f {pid_file} ] || echo NOPID; cat {rc_file} 2>/dev/null; "
                                                 f"echo ---; tail -c 4000 {log} 2>/dev/null"], timeout=30)
        rc_text, _, output = check.stdout.partition("---\n")
        rc_text = rc_text.strip()
        if "NOPID" in rc_text:
            return _result(False, -1, "", "The server command could not be started in the sandbox.\n" + output)
        if rc_text == "":
            # Still running: it booted. Stop it so the next step starts clean.
            self._docker_exec(["bash", "-c", f'kill -TERM -- -$(cat {pid_file}) 2>/dev/null; sleep 0.5; '
                                             f'kill -KILL -- -$(cat {pid_file}) 2>/dev/null; true'], timeout=30)
            if _crashed(output):
                return _result(False, 1, "", "The process kept running, but the app crashed:\n" + output)
            return _result(True, 0, "Server started successfully and remained active.\n" + output[-1500:])
        code = int(rc_text) if rc_text.lstrip("-").isdigit() else 1
        return _result(code == 0, code, output if code == 0 else "", "" if code == 0 else output)

    # ----- macOS / Linux -----------------------------------------------
    def _local_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        env.update(NONINTERACTIVE_ENV)
        return env

    def _posix_once(self, command: str, timeout: int) -> Dict[str, Any]:
        script = _bash_step_script(command, self._env_file)
        res = _run(["bash", "-c", script], timeout=timeout, cwd=self.cwd, env=self._local_env())
        stdout, folder = _split_marker(res.stdout)
        if res.returncode == 0 and folder and os.path.isdir(folder):
            self.cwd = folder
        return _result(res.returncode == 0, res.returncode, stdout, res.stderr)

    def _posix_server(self, command: str) -> Dict[str, Any]:
        script = f'[ -f "{self._env_file}" ] && . "{self._env_file}" >/dev/null 2>&1\n{command}\n'
        log_path = os.path.join(self._state_dir, "server.log")
        with open(log_path, "w+", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(
                ["bash", "-c", script], cwd=self.cwd, env=self._local_env(),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            return self._watch_server(process, log, lambda: os.killpg(os.getpgid(process.pid), signal.SIGTERM))

    # ----- Windows -----------------------------------------------------
    def _windows_cd(self, target: str) -> Optional[str]:
        target = target.strip().strip('"')
        if target.lower().startswith("/d "):
            target = target[3:].strip().strip('"')
        new_dir = os.path.abspath(os.path.join(self.cwd, os.path.expanduser(target)))
        return new_dir if os.path.isdir(new_dir) else None

    def _windows_once(self, command: str, timeout: int) -> Dict[str, Any]:
        # cmd.exe forgets `cd` between steps, so leading `cd X &&` parts are handled here.
        parts = [p.strip() for p in command.split("&&")]
        while parts and re.match(r"^cd(\s|$)", parts[0], re.IGNORECASE):
            target = parts.pop(0)[2:].strip()
            if not target:
                continue
            new_dir = self._windows_cd(target)
            if new_dir is None:
                return _result(False, 1, "", f"The system cannot find the path specified: {target}")
            self.cwd = new_dir
        if not parts:
            return _result(True, 0)
        res = _run(" && ".join(parts), timeout=timeout, cwd=self.cwd, env=self._local_env(), shell=True)
        return _result(res.returncode == 0, res.returncode, res.stdout, res.stderr)

    def _windows_server(self, command: str) -> Dict[str, Any]:
        log_path = os.path.join(self._state_dir, "server.log")
        with open(log_path, "w+", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(
                command, shell=True, cwd=self.cwd, env=self._local_env(),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            return self._watch_server(
                process, log,
                lambda: _run(["taskkill", "/T", "/F", "/PID", str(process.pid)], timeout=30),
            )

    # ----- shared --------------------------------------------------------
    @staticmethod
    def _watch_server(process, log, stop) -> Dict[str, Any]:
        deadline = time.time() + SERVER_WAIT
        while time.time() < deadline and process.poll() is None:
            time.sleep(0.2)
        code = process.poll()
        if code is None:
            try:
                stop()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            log.seek(0)
            output = log.read()[-4000:]
            if _crashed(output):
                return _result(False, 1, "", "The process kept running, but the app crashed:\n" + output)
            return _result(True, 0, "Server started successfully and remained active.\n" + output[-1500:])
        log.seek(0)
        output = log.read()[-4000:]
        return _result(code == 0, code, output if code == 0 else "", "" if code == 0 else output)
