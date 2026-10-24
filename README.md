# 🗡️ Bug Slayer
> **Autonomous Setup & README Verifier for Open-Source Repositories.**  
> *Never lose a contributor to a broken setup step again.*

Built for **Hacktoberfest Hack Day 2026** (NST.ADYPU · NSTSDC).  
Track: **Best Open-Source AI Project**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AI Engine: Gemma](https://img.shields.io/badge/AI%20Engine-Gemma-blue.svg)](https://ai.google.dev/gemma)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)

---

## 📌 The Problem
Over **60% of open-source repositories** either have:
1. **Broken READMEs:** Setup instructions that crash on Step 1 or Step 2 because dependencies, scripts, or OS environment assumptions changed.
2. **Zero Documentation:** No instructions on how to install, configure, or run the project, forcing developers to spend hours reverse-engineering entry points and required environment variables.

Bad onboarding documentation is the single largest barrier for beginners contributing to open source.

---

## 💡 The Solution: Bug Slayer
**Bug Slayer** is an autonomous developer agent that treats documentation as an *executable, self-healing specification*.

It features a **Dual-Engine Architecture**:
- ⚔️ **Mode 1: The Healer (Existing README):** Parses shell commands from markdown, executes them in a controlled subshell, catches errors, calls **Gemma AI** to diagnose the failure against the codebase, tests the suggested fix, and surgically patches the `README.md` with a clean unified diff.
- 🏛️ **Mode 2: The Architect (Zero Documentation):** Inspects package managers, entry points, and environment variables across Python, Node.js, Go, and Rust. Gemma synthesizes a complete setup plan, empirically tests that the server boots, and generates a verified `README.md`.

---

## 🏗️ Architecture
```
+---------------+     +--------------------+     +---------------------+
| Target Repo   | --> | Codebase Inspector | --> | Execution Harness   |
| (Local/Clone) |     | (Facts & Env Vars) |     | (Runs commands)     |
+---------------+     +--------------------+     +----------+----------+
                                                            |
                                                   [Command Failed?]
                                                            |
                                                            v
+---------------+     +--------------------+     +----------+----------+
| Patched       | <-- | Self-Healing Loop  | <-- | Gemma AI Engine     |
| README.md     |     | (Verifies & diffs) |     | (Diagnoses & fixes) |
+---------------+     +--------------------+     +---------------------+
```

---

## 🚀 Quickstart & Installation

Choose your operating system below to copy the direct installation command:

### 🍏 For macOS & Linux
```bash
python3 -m pip install git+https://github.com/chauhanalok546-rgb/Bug-slayer.git
```

### 🪟 For Windows (Command Prompt / PowerShell)
```cmd
python -m pip install git+https://github.com/chauhanalok546-rgb/Bug-slayer.git
```

### ✅ Before your first run
1. **Docker Desktop (recommended):** install it from [docker.com](https://www.docker.com/products/docker-desktop/) and open it. Bug Slayer then tests every README step inside a throwaway Linux container, so nothing is installed or changed on your computer, and results are the same on macOS, Windows and Linux. The first run downloads a base image (about a minute).
2. **Gemma AI key:** get a free key from [Google AI Studio](https://aistudio.google.com) and set it in your terminal:

```bash
# macOS / Linux
export GEMINI_API_KEY="your_key_here"
```

```powershell
# Windows PowerShell
$env:GEMINI_API_KEY="your_key_here"
```

Without a key, Bug Slayer still works using built-in offline rules, and it tells you clearly that it did so.

---

## 💻 How to Use (Run From Anywhere)
Once installed, you can invoke `bugslayer` from **any folder on your computer**:

### 🌐 Test Any Public GitHub Repository:
```bash
bugslayer https://github.com/elieh999/readme-clt.git
```

### 📂 Test Any Local Project Directory:
```bash
bugslayer /path/to/any/project
```

*(💡 **Note for all platforms:** If your terminal does not have Python script binaries linked in PATH, you can universally run it as: `python3 -m bugslayer.cli <url-or-path>` on Mac/Linux or `python -m bugslayer.cli <url-or-path>` on Windows)*.

When run on a remote repository, Bug Slayer:
1. Downloads the code into a temporary folder.
2. Identifies dependencies, environment variables, and entry points.
3. Runs each setup step inside an isolated **Docker sandbox** (remembering `cd`, `export` and `source venv/bin/activate` between steps, like a real terminal).
4. Diagnoses failures with **Gemma AI** (`gemma-4-26b-a4b-it`) and re-runs the suggested fix to prove it works.
5. Patches only the broken line of the README. Differences that only affect one machine (such as `python` vs `python3`) are reported but never "fixed" in the README.
6. Saves the results to **`bugslayer_output/<repo-name>/`**: `VERIFIED_README.md`, `fix-readme.patch` (ready for a pull request) and `setup.sh`.

### ⚙️ Options
| Option | What it does |
|---|---|
| *(none)* | Uses Docker if it is running; otherwise asks before running anything on your computer |
| `--docker` | Requires the Docker sandbox; stops if Docker is not running |
| `--local` | Runs the steps directly on this computer (not isolated; use only for repos you trust) |
| `--model NAME` | Uses another model, e.g. `--model gemma-4-31b-it` |
| `--output DIR` | Saves results of a remote run to `DIR` |

Environment variables: `GEMINI_API_KEY` (AI key), `BUGSLAYER_MODEL`, `BUGSLAYER_IMAGE` (sandbox image), `BUGSLAYER_TIMEOUT` (seconds per step, default 300).

---

### 🧪 Try the Built-In Demos Locally:
```bash
# Clone the repository locally:
git clone https://github.com/chauhanalok546-rgb/Bug-slayer.git
cd Bug-slayer
python3 -m pip install -e .

# 1. Test Mode 1 (Heals a broken README instruction live)
bugslayer demo_broken_repo

# 2. Test Mode 2 (Synthesizes documentation from zero for an undocumented project)
bugslayer demo_undocumented_repo

# 3. Reset the demo environments anytime
python3 reset_demos.py
```

---

## 🛠️ Tech Stack & Open-Source Tools
- **Model:** Gemma 4 (`gemma-4-26b-a4b-it`, backup `gemma-4-31b-it`) via the Gemini API, with an offline rule-based fallback
- **CLI & Visualization:** Rich (Terminal UI, AST diff rendering)
- **Execution Harness:** Docker sandbox (copy of the repo, memory/CPU limits) with a cross-platform local fallback for macOS, Linux and Windows
- **License:** MIT License
