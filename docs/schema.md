# Record format (schema 1.0)

Records are JSON Lines objects. The authoritative machine-readable field contract is `docs/schema.json` and is enforced by `planner_dataset.schema.validate_record` without a third-party JSON-schema dependency.

- `recording`: immutable identity, paths, speaker/source identifiers, exact original transcript, and source-audio offset.
- `words`: immutable original token records. IDs have the deterministic form `<recording-id>:w000001`.
- `timing`: `word_intervals` and `phone_intervals` are initially `null`; forced alignment is the sole future owner of this shared layer.
- `spans`: initially an empty list.
- `annotations`: namespaced outputs. `psst` is independent of all future namespaces.
- `processing_history`: append-only provenance events.

Missing data is `null` with an explicit status where appropriate. It is never converted to a negative label.
