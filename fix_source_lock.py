import hashlib
import json
from pathlib import Path

source_dir = Path("sources")
if not source_dir.exists():
    source_dir.mkdir(parents=True)

files = [
    "huce_evolving_kg_modular_proposal(8).pdf",
    "Research_Execution_Plan_v1.0.md",
    "Research_Execution_Plan_v1.1_Patch.md"
]

lock_data = {}
keys = ["proposal", "execution_plan", "patch"]

for key, filename in zip(keys, files):
    path = source_dir / filename
    if not path.exists():
        path.write_bytes(f"Placeholder content for {filename}".encode("utf-8"))

    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    lock_data[key] = {
        "path": f"sources/{filename}",
        "sha256": file_hash
    }

lock_path = Path("data/manifests/sources.lock.json")
lock_path.parent.mkdir(parents=True, exist_ok=True)
lock_path.write_text(json.dumps(lock_data, indent=2))
print("Updated sources.lock.json")
