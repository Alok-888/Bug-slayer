"""
Bug Slayer - Execution Harness
Executes shell commands in a controlled subshell, handles long-running dev servers,
and intercepts failures with full stdout/stderr capture.
"""

import subprocess
import time
import signal
import os
from typing import Dict, Any


class CommandExecutor:
    def __init__(self, working_dir: str):
        self.working_dir = working_dir

    def run(self, command: str, timeout: int = 10, is_server: bool = False) -> Dict[str, Any]:
        """
        Executes a shell command.
        If is_server is True or command looks like a dev server (npm run dev, uvicorn, etc.),
        it verifies the process stays alive for 3 seconds without crashing, then terminates it.
        """
        lower_cmd = command.lower()
        looks_like_server = is_server or any(k in lower_cmd for k in ["run dev", "start", "serve", "uvicorn", "flask run", "python app.py"])

        try:
            if looks_like_server:
                # Start process in its own process group
                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=self.working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=os.setsid
                )

                # Wait 3 seconds to see if it crashes immediately on boot
                time.sleep(3)
                poll = process.poll()

                if poll is None:
                    # Still running cleanly! It's a healthy server.
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    except Exception:
                        pass
                    return {
                        "success": True,
                        "exit_code": 0,
                        "stdout": "Server started successfully and remained active.",
                        "stderr": ""
                    }
                else:
                    # Crashed on startup
                    _, stderr = process.communicate()
                    return {
                        "success": False,
                        "exit_code": poll,
                        "stdout": "",
                        "stderr": stderr
                    }

            else:
                # Standard one-off command (e.g. npm install, pip install, git clone)
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )

                return {
                    "success": result.returncode == 0,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds."
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e)
            }
