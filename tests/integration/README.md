# Integration Tests

Use this directory for adapter and wiring tests that cross module boundaries.
This file is a controlled testing document and must be updated when the integration-test scope changes.
Include runtime-mode container wiring checks here, especially `LOCAL` local-filesystem storage selection, `CLOUD` GCS selection, runtime database URL assembly, Secret Manager password resolution, and end-to-end `Contract -> Adapter -> Skill -> Orchestration` feature wiring such as `strip_metadata`.
Also include verified knowledge base routing checks here, covering disabled-by-default behavior, direct PostgreSQL retrieval, Cloud Run gateway retrieval, locale fallback after misses or low-confidence hits, and the orchestrator-port fallback path.
