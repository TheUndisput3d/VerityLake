from __future__ import annotations

import tempfile
from importlib.resources import files
from pathlib import Path

from veritylake.storage import ObjectStore, S3Store
from veritylake.util import utcnow

DOCUMENT_COLUMNS = {
    "doc_id": "string", "url": "string", "title": "string", "text": "string",
    "fetched_at": "string", "content_sha256": "string", "raw_key": "string",
    "etag": "string", "last_modified": "string", "status": "int64", "html_bytes": "int64",
}
CHUNK_COLUMNS = {
    "chunk_id": "string", "doc_id": "string", "ordinal": "int64", "title": "string", "url": "string",
    "text": "string", "char_start": "int64", "char_end": "int64", "content_sha256": "string",
    "fetched_at": "string", "raw_key": "string", "chunker_version": "string",
}


class DeltaTables:
    """Each run owns its own Delta tables. Completed versions are immutable by application convention."""
    def __init__(self, store: ObjectStore):
        self.store = store
        self.options = store.delta_options() if isinstance(store, S3Store) else {}

    def write(self, key: str, rows: list[dict], kind: str) -> dict:
        import pyarrow as pa
        from deltalake import DeltaTable, write_deltalake

        columns = DOCUMENT_COLUMNS if kind == "documents" else CHUNK_COLUMNS
        schema = pa.schema([(name, pa.string() if dtype == "string" else pa.int64())
                            for name, dtype in columns.items()])
        table = pa.Table.from_pylist(rows, schema=schema)
        uri = self.store.uri(key)
        write_deltalake(uri, table, mode="overwrite", storage_options=self.options)
        delta = DeltaTable(uri, storage_options=self.options)
        return {"key": key, "uri": uri, "version": delta.version(), "rows": len(rows),
                "format": "delta", "schema": columns, "created_at": utcnow()}

    def read(self, table: dict) -> list[dict]:
        from deltalake import DeltaTable

        # Resolve the URI from a trusted local key, not an arbitrary URI embedded in metadata.
        delta = DeltaTable(self.store.uri(table["key"]), version=table["version"], storage_options=self.options)
        return delta.to_pyarrow_table().to_pylist()

    @staticmethod
    def deduplicate(rows: list[dict]) -> list[dict]:
        import duckdb
        import pyarrow as pa

        if not rows:
            return []
        with duckdb.connect(":memory:", config={"threads": 2}) as con:
            con.register("prepared", pa.Table.from_pylist(rows))
            query = files("veritylake").joinpath("sql/silver.sql").read_text()
            return con.execute(query).to_arrow_table().to_pylist()

    def build_catalog(self, run_id: str, tables: dict, quality: dict) -> dict:
        import duckdb

        key = f"catalog/runs/{run_id}/catalog.duckdb"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.duckdb"
            with duckdb.connect(str(path)) as con:
                con.execute("CREATE TABLE datasets(name VARCHAR, uri VARCHAR, delta_version BIGINT, row_count BIGINT, run_id VARCHAR)")
                con.execute("CREATE TABLE columns(dataset VARCHAR, name VARCHAR, type VARCHAR)")
                con.execute("CREATE TABLE checks(stage VARCHAR, name VARCHAR, passed BOOLEAN)")
                for name, table in tables.items():
                    con.execute("INSERT INTO datasets VALUES (?, ?, ?, ?, ?)",
                                [name, table["uri"], table["version"], table["rows"], run_id])
                    con.executemany("INSERT INTO columns VALUES (?, ?, ?)",
                                    [(name, column, dtype) for column, dtype in table["schema"].items()])
                for stage, report in quality.items():
                    con.executemany("INSERT INTO checks VALUES (?, ?, ?)",
                                    [(stage, c["name"], c["passed"]) for c in report["checks"]])
            self.store.put(key, path.read_bytes())
        return {"key": key, "uri": self.store.uri(key), "format": "duckdb"}
