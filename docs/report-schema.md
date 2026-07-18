# Typed Report Contracts

The report schema is represented by provisional typed Pydantic contracts. The contracts define serialization semantics for later stages, but no report writer or audit pipeline is operational yet.

## Planned output files

- `report.json`: future machine-readable serialization of `AuditReport`.
- `report.html`: future human-readable rendering from `AuditReport`.
- `findings.csv`: future tabular export of factual and evaluated findings.
- `repair_proposal.csv`: future export of `RepairProposal`, generated only with `--repair`.

## Top-level `AuditReport` fields

- `schema_version`: literal `1.0.0`.
- `tool`: `ToolMetadata` with tool name and package version.
- `run`: `RunMetadata` with run ID, timezone-aware timestamps, and command tuple.
- `inputs`: `InputSummary` with source manifest summaries, optional image root, and total record count.
- `configuration`: `AuditConfig`, including deterministic configuration digest behavior.
- `policy`: `SplitPolicy`, beginning with `patient_independent_pathology_benchmark`.
- `schema_mapping`: optional `SchemaMapping` with per-field provenance.
- `summary`: `FindingSummary`.
- `factual_findings`: immutable sequence of `FactualFinding` detector-stage records without policy outcomes.
- `evaluated_findings`: immutable sequence of `EvaluatedFinding` records with `PolicyOutcome` and policy reason.
- `relationship_graph`: `RelationshipGraph` serialization contract.
- `policy_evaluation`: `PolicyEvaluationSummary`.
- `repair_proposal`: optional `RepairProposal` requiring researcher review.
- `reproducibility`: `ReproducibilityMetadata`.
- `warnings`: immutable warning strings.

## Implemented ingestion provenance contracts

Task 3 adds `RawManifestRow`, `LoadedManifest`, and `LoadedManifestPair` as typed ingestion-boundary contracts. `RawManifestRow` preserves original-header keyed values, normalized-header keyed minimally cleaned values, zero-based source row numbers, source manifest ID, and assigned partition. `LoadedManifest` records the `SourceManifest`, original and normalized headers, loaded rows, UTF-8 encoding mode, newline style, and nonblank warnings. `LoadedManifestPair` carries the assigned train and test manifests and rejects same-file inputs. These contracts do not perform schema mapping or detector logic.

## Contract status

The typed models prohibit arbitrary extra fields and use immutable tuples where practical. Serialization is deterministic when callers provide canonical ordering. Later stages may add report writers and typed model migrations, but they must preserve the factual-versus-evaluated finding distinction.
