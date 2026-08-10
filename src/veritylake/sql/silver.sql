-- Input has already been normalized, timestamp-checked and quarantined in Python.
-- Deterministic winner selection makes retries stable without Spark or runtime extensions.
WITH content_ranked AS (
    SELECT *, row_number() OVER (
        PARTITION BY content_sha256 ORDER BY url ASC, doc_id ASC
    ) AS content_rank
    FROM prepared
    WHERE length(trim(text)) > 0 AND length(trim(title)) > 0
)
SELECT * EXCLUDE (content_rank)
FROM content_ranked
WHERE content_rank = 1
ORDER BY doc_id;
