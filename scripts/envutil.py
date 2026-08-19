from pathlib import Path


def local_env():
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        raise SystemExit("Run python3 scripts/bootstrap.py first")
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value.strip().strip("'\"")
    return result
