import boto3
import pytest

moto = pytest.importorskip("moto", reason="moto not installed in this test environment")
from veritylake.storage import ConflictError, S3Store

pytestmark = pytest.mark.integration


def test_s3_boto_adapter_versioning_and_conditional_writes(settings):
    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="fixture", aws_secret_access_key="fixture")
        store = S3Store(settings, client=client)
        store.ensure_bucket()
        assert client.get_bucket_versioning(Bucket=settings.s3_bucket)["Status"] == "Enabled"
        tag = store.compare_and_swap("catalog/active.json", b"one", None)
        store.compare_and_swap("catalog/active.json", b"two", tag)
        with pytest.raises(ConflictError):
            store.compare_and_swap("catalog/active.json", b"stale", tag)
        assert store.get("catalog/active.json") == b"two"
