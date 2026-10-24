// Sends a failed step to Gemma and returns a suggested fix.
// Owner: Person C
//
// Input:  one failed result from the runner (+ readmeSection)
// Output (see CONTRACTS.md):
//   { diagnosis, category, fixCommands: [], readmePatch: { afterLine, insert } }
//
// Uses Gemma through the Google AI API. Get a free key at aistudio.google.com
// and set it before running:   export GEMINI_API_KEY=your_key_here
// (On Windows PowerShell:      $env:GEMINI_API_KEY="your_key_here")

const MODEL = process.env.GEMMA_MODEL || "gemma-3-27b-it";

function buildPrompt(failure) {
  return `You are fixing a broken README. A beginner followed it and this step failed.

Failed command: ${failure.command}
Exit code: ${failure.exitCode}
Error output (last part):
${(failure.stderr || "").slice(-3000)}

README:
${(failure.readmeSection || "").slice(0, 6000)}

Reply with ONLY a JSON object, no other text:
{
  "diagnosis": "one sentence explaining why it failed",
  "category": "missing_prerequisite | changed_command | env_var | secret_required",
  "fixCommands": ["commands to run before or instead of the failed one"],
  "readmePatch": { "afterLine": <line number>, "insert": "markdown text to add to the README" }
}`;
}

async function diagnose(failure) {
  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    console.log("⚠️  GEMINI_API_KEY not set — skipping AI step.");
    return null;
  }

  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${key}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contents: [{ parts: [{ text: buildPrompt(failure) }] }] }),
  });

  if (!res.ok) throw new Error(`Gemma API error ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text || "";

  // Models sometimes wrap JSON in ```json fences — pull out the {...} part.
  const json = text.match(/\{[\s\S]*\}/);
  if (!json) throw new Error("Gemma did not return JSON:\n" + text);
  return JSON.parse(json[0]);
}

module.exports = { diagnose, buildPrompt };
