#!/usr/bin/env node
// DocVerify entry point. Connects parser -> runner -> ai.
// Owner: Person A
//
// Usage:
//   node src/cli.js <path-to-README.md> [--parse-only] [--image node:20]

const fs = require("fs");
const path = require("path");
const { parseReadme } = require("./parser");
const { runSteps } = require("./runner");
const { diagnose } = require("./ai");

async function main() {
  const args = process.argv.slice(2);
  const readmePath = args.find((a) => !a.startsWith("--"));
  const parseOnly = args.includes("--parse-only");
  const imageFlag = args.indexOf("--image");
  const image = imageFlag !== -1 ? args[imageFlag + 1] : "node:20";

  if (!readmePath) {
    console.log("Usage: docverify <README.md> [--parse-only] [--image node:20]");
    process.exit(1);
  }

  const markdown = fs.readFileSync(readmePath, "utf8");
  const steps = parseReadme(markdown);

  console.log(`\n📄 Found ${steps.length} command(s) in ${path.basename(readmePath)}\n`);
  steps.forEach((s) =>
    console.log(`  ${s.step}. ${s.command}${s.longRunning ? "  (long-running)" : ""}`)
  );

  if (parseOnly) return;

  console.log(`\n🐳 Running steps in Docker (${image})...\n`);
  const results = await runSteps(steps, {
    image,
    repoDir: path.dirname(path.resolve(readmePath)),
  });

  for (const r of results) {
    console.log(`  ${r.exitCode === 0 ? "✅" : "❌"} Step ${r.step}: ${r.command}`);
  }

  const failure = results.find((r) => r.exitCode !== 0);
  if (!failure) {
    console.log("\n🎉 README works! Every step passed.\n");
    return;
  }

  console.log(`\n🤖 Asking Gemma why step ${failure.step} failed...\n`);
  failure.readmeSection = markdown;
  const fix = await diagnose(failure);

  if (!fix) {
    console.log("No fix suggested yet (AI module not finished).");
    return;
  }
  console.log(`Diagnosis: ${fix.diagnosis}`);
  console.log(`Suggested commands: ${fix.fixCommands.join(" && ")}`);
}

main().catch((err) => {
  console.error("DocVerify crashed:", err.message);
  process.exit(1);
});
