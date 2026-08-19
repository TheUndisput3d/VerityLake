#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.request

from envutil import local_env


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python3 scripts/ask.py "Your question"')
    env = local_env()
    request = urllib.request.Request("http://127.0.0.1:8000/ask",
        data=json.dumps({"question": " ".join(sys.argv[1:]), "top_k": 4}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": env["API_KEY"]}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            print(json.dumps(json.load(response), indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode(), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
