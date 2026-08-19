"""Dependency-light structural checks. These do NOT replace Docker Compose or Terraform validation."""
import ast
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
errors = []
for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "scripts").glob("*.py")) + list((ROOT / "dags").glob("*.py")):
    try:
        ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        errors.append(str(exc))
for path in ROOT.rglob("*.json"):
    if not any(part.startswith(".") for part in path.relative_to(ROOT).parts):
        try:
            json.loads(path.read_text())
        except (ValueError, UnicodeError) as exc:
            errors.append(f"{path}: {exc}")
for pattern in ("*.yaml", "*.yml"):
    for path in ROOT.rglob(pattern):
        try:
            list(yaml.safe_load_all(path.read_text()))
        except yaml.YAMLError as exc:
            errors.append(f"{path}: {exc}")
compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
for name in ("minio", "chroma", "ollama", "airflow-api", "airflow-scheduler", "airflow-dag-processor", "api"):
    assert name in compose["services"]
assert compose["services"]["api"]["environment"]["AWS_ACCESS_KEY_ID"].startswith("${LAKE_READER_USER")
assert "MINIO_ROOT_PASSWORD" not in compose["services"]["api"]["environment"]
assert compose["services"]["api"]["read_only"] is True
assert "ports" not in compose["services"]["chroma"]
assert "ports" not in compose["services"]["ollama"]
assert "innerHTML" not in (ROOT / "src/veritylake/ui/app.js").read_text()
if errors:
    raise SystemExit("\n".join(errors))
print("Python AST, JSON/YAML syntax and selected isolation invariants passed.")
