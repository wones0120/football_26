"""Restore checksum-verified Sunday evidence without overwriting existing files."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import tarfile


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        checksum = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
        return checksum.hexdigest()


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=repository)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((repository / "artifacts/sunday_preparation_archives/manifest.json").read_text())
    restored = verified = 0
    for entry in manifest["archives"]:
        archive_path = repository / entry["path"]
        if digest(archive_path) != entry["sha256"]:
            raise ValueError(f"Archive checksum mismatch: {archive_path}")
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) != entry["file_count"] or {m.name for m in members} != set(entry["files"]):
                raise ValueError("Archive file inventory differs from manifest")
            for member in members:
                destination = root / member.name
                if not member.isfile() or destination.is_symlink() or not destination.resolve().is_relative_to(root):
                    raise ValueError(f"Unsafe archive member: {member.name}")
                expected = entry["files"][member.name]
                if destination.exists():
                    if digest(destination) != expected:
                        raise ValueError(f"Refusing to overwrite different evidence: {destination}")
                    verified += 1
                    continue
                stream = archive.extractfile(member)
                assert stream is not None
                payload = stream.read()
                if sha256(payload).hexdigest() != expected:
                    raise ValueError(f"Evidence checksum mismatch: {member.name}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as output:
                    output.write(payload)
                destination.chmod(member.mode)
                restored += 1
    print(json.dumps({"restored_files": restored, "verified_existing_files": verified}))


if __name__ == "__main__":
    main()
