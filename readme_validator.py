import re
import shutil
from pathlib import Path

readme = Path("README.md").read_text()

blocks = re.findall(
    r"```(?:bash|sh|shell)\s*\n(.*?)```",
    readme,
    flags=re.DOTALL
)

commands = []

for block in blocks:
    for line in block.splitlines():
        line = line.strip()

        if line and not line.startswith("#"):
            commands.append(line)

print("=== RunMyREADME: README Validator ===\n")

for command in commands:
    print(f"[FOUND] {command}")

print("\n=== Checking setup instructions ===")

install_index = -1
dev_index = -1

for i, command in enumerate(commands):
    if command == "npm install":
        install_index = i
    if command == "npm run dev":
        dev_index = i

if dev_index != -1 and install_index == -1:
    print("[WARNING] npm install is missing.")
elif dev_index != -1 and install_index > dev_index:
    print("[WARNING] npm install appears too late.")
elif dev_index != -1:
    print("[OK] Installation appears before development.")

print("\n=== Checking installed tools ===")

for tool in ["python3", "npm", "git"]:
    if shutil.which(tool):
        print(f"[AVAILABLE] {tool}")
    else:
        print(f"[NOT FOUND] {tool}")

print("\nValidation complete.")
print("\n=== Checking file references ===")

for command in commands:
    match = re.match(r"python3\s+([^\s]+\.py)$", command)

    if match:
        filename = match.group(1)

        if Path(filename).is_file():
            print(f"[OK] {filename} exists.")
        else:
            print(f"[WARNING] {filename} was not found.")

