# Contract Tests

Use this directory for deployable agent contract checks, query schema validation, and skill registration guarantees.
This file is a controlled testing document and must be updated when the contract-test scope changes.
Include entrypoint guarantees here, such as forcing `CLOUD` mode during deployment bootstrap, preserving the source deployment entrypoint module, returning structured query payloads, and exposing newly registered business skills through stable root-agent responses.
Also include the verified knowledge base contract here, including deployment env-var propagation for `TAILMATE_KB_ENABLED`, `TAILMATE_EMBEDDING_MODEL`, and `TAILMATE_KB_THRESHOLD`, plus root-agent behavior that keeps internal knowledge metadata out of the public response payload.
