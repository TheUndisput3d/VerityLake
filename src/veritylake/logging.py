from __future__ import annotations

import json
import logging
import sys

from veritylake.util import utcnow


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Never log question bodies, query strings, credentials, raw HTML or model prompts.
        out = {"time": utcnow(), "level": record.levelname, "logger": record.name, "message": record.getMessage()}
        out.update(getattr(record, "fields", {}))
        if record.exc_info:
            out["exception_type"] = record.exc_info[0].__name__
        return json.dumps(out, ensure_ascii=False, default=str)


def configure(fmt: str = "json") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter() if fmt == "json" else logging.Formatter("%(levelname)s | %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("httpx", "httpcore", "botocore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
