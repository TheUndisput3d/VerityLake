# Third-party notices

The repository's MIT license applies to its original code, not to every item downloaded by Docker, pip, Go, Ollama or the runtime crawler. Dependencies, images, model weights and source content retain their own licenses and terms. Consult their upstream licenses and generated release SBOM before redistribution or business use.

The storage Dockerfile builds MinIO and its client from upstream source release tags and copies corresponding source archives and LICENSE files into the resulting images at `/usr/share/veritylake/source` and `/usr/share/licenses`. MinIO's upstream licensing includes copyleft obligations; review the actual included licenses and redistribution/deployment obligations. Including source archives is not a claim that every possible deployment is automatically compliant.

Downloaded embedding/generation models are not included in this ZIP and are not relicensed under MIT. Books to Scrape content is fetched at runtime from a scraping sandbox; its website content is not owned by this repository, and demo prices/inventory are not real commercial data. No scraped text corpus is bundled.

Airflow, DuckDB, Delta Lake, Chroma, Ollama, MinIO, Docker, GitHub, AWS, Terraform, Prometheus and Grafana names identify the respective projects/products. There is no affiliation or endorsement claim. Dependency/version/interface references are collected in `docs/SOURCES.md`.
