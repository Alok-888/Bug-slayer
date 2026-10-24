// Runs README commands inside a throwaway Docker container.
// Owner: Person B
//
// Input:  steps from the parser
// Output (see CONTRACTS.md):
//   [{ step, command, exitCode, stdout, stderr }]

const { execFile } = require("child_process");

const STEP_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes per normal step
const READY_TIMEOUT_MS = 60 * 1000; // how long to wait for a server to start
const READY_PATTERNS = /listening on|ready in|compiled successfully|server started|running on|localhost:\d+/i;

function sh(cmd, args, timeout = STEP_TIMEOUT_MS) {
  return new Promise((resolve) => {
    execFile(cmd, args, { timeout, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
      resolve({
        exitCode: err ? (typeof err.code === "number" ? err.code : 1) : 0,
        stdout: stdout || "",
        stderr: stderr || (err && err.killed ? "Timed out" : ""),
      });
    });
  });
}

async function runSteps(steps, { image = "node:20", repoDir } = {}) {
  // 1. Start a container that stays alive so steps share the same filesystem.
  //    The repo is COPIED in (not mounted) so the user's files are never touched.
  const start = await sh("docker", [
    "run", "-d", "--rm",
    "--memory", "2g", "--cpus", "2",
    "-w", "/work",
    image, "sleep", "infinity",
  ]);
  if (start.exitCode !== 0) {
    throw new Error("Could not start Docker. Is Docker Desktop running?\n" + start.stderr);
  }
  const container = start.stdout.trim();

  const results = [];
  try {
    if (repoDir) await sh("docker", ["cp", `${repoDir}/.`, `${container}:/work`]);

    for (const s of steps) {
      const result = s.longRunning
        ? await runUntilReady(container, s.command)
        : await sh("docker", ["exec", container, "bash", "-lc", s.command]);

      results.push({ step: s.step, command: s.command, ...result });
      if (result.exitCode !== 0) break; // stop at first failure
    }
  } finally {
    await sh("docker", ["rm", "-f", container]);
  }
  return results;
}

// For servers: start in background, then watch the log for a "ready" message.
async function runUntilReady(container, command) {
  await sh("docker", ["exec", "-d", container, "bash", "-lc", `${command} > /tmp/server.log 2>&1`]);

  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2000));
    const log = (await sh("docker", ["exec", container, "cat", "/tmp/server.log"])).stdout;
    if (READY_PATTERNS.test(log)) return { exitCode: 0, stdout: log, stderr: "" };
    if (/error|ERR!|exception|cannot find/i.test(log)) return { exitCode: 1, stdout: "", stderr: log };
  }
  return { exitCode: 1, stdout: "", stderr: "Server did not report ready within 60s" };
}

module.exports = { runSteps };
