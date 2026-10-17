"""Verify frozen artifact bytes, including external read-only input references."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent

def verify(manifest):
    errors = []
    for name, expected in manifest.get('files', {}).items():
        path = ROOT / name
        if not path.is_file():
            errors.append('missing artifact: ' + name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append('changed artifact: ' + name)
    for name, expected in manifest.get('local_input_hashes', {}).items():
        path = Path(name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append('external input changed or missing: ' + name)
    return errors

if __name__ == '__main__':
    result = verify(json.loads((ROOT/'manifest.json').read_text()))
    print(json.dumps({'valid':not result,'errors':result},indent=2))
    sys.exit(bool(result))
