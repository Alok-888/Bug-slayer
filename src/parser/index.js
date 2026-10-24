// Reads README markdown and returns the shell commands in order.
// Owner: Person A
//
// Output (see CONTRACTS.md):
//   [{ step: 1, command: "npm install", line: 12, longRunning: false }]

// "console" blocks usually show example output, so they are not run.
const SHELL_LANGS = ["bash", "sh", "shell", "zsh", ""];

// Commands that start a server and never exit on their own
const LONG_RUNNING = [
  /^npm (run )?(start|dev|serve)\b/,
  /^yarn (start|dev|serve)\b/,
  /^pnpm (start|dev|serve)\b/,
  /^node .*server/,
  /^docker compose up(?!.*-d)/,
  /^docker-compose up(?!.*-d)/,
  /^python .*manage\.py runserver/,
  /^flask run/,
  /^uvicorn /,
];

function parseReadme(markdownText) {
  const lines = markdownText.split(/\r?\n/);
  const steps = [];
  let inBlock = false;
  let blockIsShell = false;

  lines.forEach((rawLine, index) => {
    const fence = rawLine.trim().match(/^```(\w*)/);

    if (fence) {
      if (!inBlock) {
        inBlock = true;
        blockIsShell = SHELL_LANGS.includes(fence[1].toLowerCase());
      } else {
        inBlock = false;
      }
      return;
    }

    if (!inBlock || !blockIsShell) return;

    let line = rawLine.trim();
    if (!line || line.startsWith("#")) return; // blank or comment

    // Strip a leading "$ " prompt that people copy into READMEs.
    if (line.startsWith("$ ")) line = line.slice(2).trim();
    else if (/^[>\w-]+@[\w-]+.*[$#] /.test(line)) return; // user@host$ style output

    steps.push({
      step: steps.length + 1,
      command: line,
      line: index + 1,
      longRunning: LONG_RUNNING.some((re) => re.test(line)),
    });
  });

  return steps;
}

module.exports = { parseReadme };
