import json
import os
import subprocess
from pathlib import Path


def main():
    path = Path(os.environ["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"admin": os.environ["AIRFLOW_ADMIN_PASSWORD"]}))
    path.chmod(0o600)
    subprocess.run(["airflow", "db", "migrate"], check=True)
    print("Airflow metadata migrated. Local admin credentials are in your .env.")


if __name__ == "__main__":
    main()
