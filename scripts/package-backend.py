"""Build a source-only backend package; runtime data and private keys stay out."""
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
backend = root / "backend"
destination = Path(sys.argv[1]) if len(sys.argv) > 1 else root / ".local-logs/security/backend.zip"
destination.parent.mkdir(parents=True, exist_ok=True)
files = [backend / name for name in ("main.py", "config.py", "requirements.txt", "startup.txt", "keys/known_hosts")]
for directory in ("api", "services", "models", "config"):
    files.extend(p for p in (backend / directory).rglob("*") if p.is_file()
                 and p.suffix in {".py", ".json", ".sql"} and "__pycache__" not in p.parts)
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, path.relative_to(backend))
print(f"Packaged {len(files)} source files: {destination}")
