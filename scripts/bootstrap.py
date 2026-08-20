#!/usr/bin/env python3
"""Create local secrets without pip, and never overwrite existing credentials."""
import base64
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / ".env"
    if destination.exists():
        print(".env already exists; it was not changed.")
        return
    text = (ROOT / ".env.example").read_text()
    token = "CHANGE_ME_GENERATE_WITH_BOOTSTRAP"
    lines = []
    for line in text.splitlines():
        if token in line:
            key = line.split("=", 1)[0]
            value = base64.urlsafe_b64encode(os.urandom(32)).decode() if key == "AIRFLOW_FERNET_KEY" else secrets.token_hex(24)
            line = key + "=" + value
        if line.startswith("LOCAL_UID="):
            line = f"LOCAL_UID={os.getuid() if hasattr(os, 'getuid') else 1000}"
        if line.startswith("LOCAL_GID="):
            line = f"LOCAL_GID={os.getgid() if hasattr(os, 'getgid') else 1000}"
        lines.append(line)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write("\n".join(lines) + "\n")
    (ROOT / "reports").mkdir(exist_ok=True)
    print("Created .env with unique local secrets. Keep it private. Next: docker compose up --build -d")


if __name__ == "__main__":
    main()
