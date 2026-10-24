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

## 🚀 Quickstart

### ⚡ 1-Line Global Installation (Recommended)
Install Bug Slayer directly from GitHub with pip:
```bash
pip install git+https://github.com/chauhanalok546-rgb/Bug-slayer.git
```

### 💻 Usage
Run Bug Slayer from **any folder on your computer**:

```bash
# 🌐 Pass any public GitHub URL directly:
bugslayer https://github.com/elieh999/readme-clt.git

# 📂 Or point to any local project folder:
bugslayer /path/to/any/project
```

When run on a remote repository, Bug Slayer:
1. Clones the code into an isolated sandbox.
2. Identifies dependencies, environment variables, and entry points.
3. Tests each setup step and diagnoses errors using **Gemma AI**.
4. Automatically exports a verified **`VERIFIED_README.md`** and **`setup.sh`** into your current directory!

---

### 🧪 Try the Built-In Demos Locally:
```bash
# Clone the repository locally:
git clone https://github.com/chauhanalok546-rgb/Bug-slayer.git
cd Bug-slayer
pip install -e .

# 1. Test Mode 1 (Heals a broken README instruction live)
bugslayer demo_broken_repo

# 2. Test Mode 2 (Synthesizes documentation from zero for an undocumented project)
bugslayer demo_undocumented_repo

# 3. Reset the demo environments anytime
python3 reset_demos.py
```

---

## 🛠️ Tech Stack & Open-Source Tools
- **Model:** Gemma (Google's open-weights family) / Gemini API
- **CLI & Visualization:** Rich (Terminal UI, AST diff rendering)
- **Execution Harness:** Subprocess with timeout & daemon process group management
- **License:** MIT License
