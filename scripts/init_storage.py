import json
import os
import subprocess
import tempfile
from pathlib import Path


def mc(*args):
    # Do not echo argv: some MinIO admin commands contain credentials.
    subprocess.run(["mc", *args], check=True, stdout=subprocess.DEVNULL)


def main():
    bucket = os.environ.get("S3_BUCKET", "veritylake")
    root = f"arn:aws:s3:::{bucket}"
    mc("alias", "set", "local", "http://minio:9000", os.environ["MINIO_ROOT_USER"], os.environ["MINIO_ROOT_PASSWORD"])
    mc("mb", "--ignore-existing", "local/" + bucket)
    mc("version", "enable", "local/" + bucket)
    policies = {
        "writer": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation", "s3:ListBucketMultipartUploads"], "Resource": [root]},
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], "Resource": [root + "/*"]},
        ]},
        "reader": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": [root + "/catalog/*"]},
        ]},
    }
    with tempfile.TemporaryDirectory() as tmp:
        for role, policy in policies.items():
            path = Path(tmp) / f"{role}.json"
            path.write_text(json.dumps(policy))
            user = os.environ[f"LAKE_{role.upper()}_USER"]
            password = os.environ[f"LAKE_{role.upper()}_PASSWORD"]
            mc("admin", "user", "add", "local", user, password)
            mc("admin", "policy", "create", "local", "vl-" + role, str(path))
            mc("admin", "policy", "attach", "local", "vl-" + role, "--user", user)
    print("Storage ready: versioned bucket, writer account, catalog-only reader account.")


if __name__ == "__main__":
    main()
