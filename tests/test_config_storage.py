import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from pydantic import ValidationError

from veritylake.config import Settings
from veritylake.storage import ConflictError
from veritylake.util import validate_run_id


@pytest.mark.parametrize("values", [
    {"min_documents": 4, "max_pages": 3}, {"chunk_words": 30, "chunk_overlap_words": 30},
    {"max_pages": 101}, {"max_fetches": 2, "max_pages": 3},
    {"environment": "production", "allow_private_sources": True},
])
def test_settings_reject_invalid(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_public_config_does_not_contain_secrets(settings):
    encoded = json.dumps(settings.public_pipeline_config())
    assert settings.api_key.get_secret_value() not in encoded
    assert "aws_secret_access_key" not in encoded


@pytest.mark.parametrize("key", ["../escape", "/absolute", "folder/../../escape", "bad\\key", "bad\x00key", ""])
def test_unsafe_object_key(store, key):
    with pytest.raises(ValueError):
        store.put(key, b"data")


def test_symlink_escape_rejected(store, tmp_path):
    external = tmp_path / "outside"
    external.mkdir()
    (store.root / "escape").symlink_to(external)
    with pytest.raises(ValueError):
        store.put("escape/file", b"no")


def test_store_roundtrip_and_version(store):
    store.put_json("raw/a.json", {"text": "hello"})
    assert store.get_json("raw/a.json") == {"text": "hello"}
    before = store.get_versioned("raw/a.json")[1]
    store.compare_and_swap("raw/a.json", b'{"text":"world"}', before)
    assert store.get_json("raw/a.json")["text"] == "world"
    with pytest.raises(ConflictError):
        store.compare_and_swap("raw/a.json", b"bad", before)
    assert store.list_keys("raw/") == ["raw/a.json"]


def test_atomic_compare_and_swap_has_one_winner(store):
    def compete(i):
        try:
            store.compare_and_swap("catalog/active.json", str(i).encode(), None)
            return True
        except ConflictError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(compete, range(20)))
    assert sum(results) == 1


@pytest.mark.parametrize("value", ["../x", "abc", "a" * 31, "A" * 32, "g" * 32])
def test_run_id_is_strict(value):
    with pytest.raises(ValueError):
        validate_run_id(value)
    assert validate_run_id(uuid4().hex)
