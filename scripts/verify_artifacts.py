"""Check saved experiment or documentation manifests without modifying files."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("path", type=Path)
args = parser.parse_args()
root = args.path.resolve()
manifests = [root / "manifest.json"] if (root / "manifest.json").is_file() else sorted(root.rglob("manifest.json"))
if not manifests:
    parser.error("No manifest.json found")
checked = 0
for manifest in manifests:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for relative, expected in data["files_sha256"].items():
        path = (manifest.parent / relative).resolve()
        if not path.is_relative_to(manifest.parent.resolve()):
            parser.error(f"Path escapes artifact directory: {relative}")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            parser.error(f"Checksum mismatch or missing file: {path}")
        checked += 1
print(f"Verified {checked} files in {len(manifests)} manifests.")
