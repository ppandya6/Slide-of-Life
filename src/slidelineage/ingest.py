"""Deterministic CSV manifest ingestion boundary."""

import csv
import hashlib
from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import Final

from slidelineage.config import AuditConfig
from slidelineage.errors import (
    DuplicateHeaderError,
    EmptyManifestError,
    ManifestCsvError,
    ManifestEncodingError,
    ManifestNotFoundError,
    ManifestUnreadableError,
    NormalizedHeaderCollisionError,
    SameManifestFileError,
)
from slidelineage.models import (
    LoadedManifest,
    LoadedManifestPair,
    Partition,
    RawManifestRow,
    SourceManifest,
)
from slidelineage.normalization import normalize_header, normalize_missing_value

_CHUNK_SIZE: Final[int] = 1024 * 1024
_UTF8_BOM: Final[bytes] = b"\xef\xbb\xbf"


def compute_file_sha256(path: Path) -> str:
    """Compute lowercase SHA-256 from original file bytes in chunks."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise ManifestNotFoundError(f"Manifest file not found: {path}") from exc
    except OSError as exc:
        raise ManifestUnreadableError(f"Manifest file is unreadable: {path}") from exc
    return digest.hexdigest()


def load_manifest(path: Path, partition: Partition, manifest_id: str) -> LoadedManifest:
    """Load one CSV manifest into typed raw-row provenance contracts."""

    _validate_manifest_file(path)
    source_sha256 = compute_file_sha256(path)
    source_bytes = _read_source_bytes(path)
    if not source_bytes:
        raise EmptyManifestError(f"Manifest is empty: {path}")
    newline_style = _detect_newline_style(source_bytes)
    text, encoding_used = _decode_source_bytes(source_bytes, path)
    rows = _parse_csv_text(text, path)
    header = _extract_header(rows, path)
    original_headers, normalized_headers = _validate_headers(header, path)
    raw_rows, warnings = _build_rows(
        rows[1:], original_headers, normalized_headers, partition, manifest_id, path
    )
    source = SourceManifest(
        manifest_id=manifest_id,
        path=path,
        assigned_partition=partition,
        sha256=source_sha256,
        row_count=len(raw_rows),
        columns=original_headers,
    )
    return LoadedManifest(
        source=source,
        original_headers=original_headers,
        normalized_headers=normalized_headers,
        rows=tuple(raw_rows),
        encoding_used=encoding_used,
        newline_style=newline_style,
        warnings=tuple(warnings),
    )


def load_manifest_pair(config: AuditConfig) -> LoadedManifestPair:
    """Load configured train and test manifests after same-file checks."""

    _validate_distinct_manifest_files(config.train_manifest, config.test_manifest)
    train = load_manifest(config.train_manifest, Partition.train, "train_manifest")
    test = load_manifest(config.test_manifest, Partition.test, "test_manifest")
    return LoadedManifestPair(train=train, test=test)


def _validate_manifest_file(path: Path) -> None:
    if not path.exists():
        raise ManifestNotFoundError(f"Manifest file not found: {path}")
    if not path.is_file():
        raise ManifestUnreadableError(f"Manifest path is not a regular file: {path}")


def _validate_distinct_manifest_files(train_path: Path, test_path: Path) -> None:
    _validate_manifest_file(train_path)
    _validate_manifest_file(test_path)
    if train_path == test_path:
        raise SameManifestFileError(
            f"Train and test manifests are the same path: {train_path}"
        )
    try:
        if train_path.resolve(strict=True) == test_path.resolve(strict=True):
            raise SameManifestFileError(
                "Train and test manifests resolve to the same file: "
                f"{train_path} and {test_path}"
            )
    except OSError as exc:
        raise ManifestUnreadableError(
            f"Unable to resolve manifest paths: {train_path}, {test_path}"
        ) from exc
    try:
        if train_path.samefile(test_path):
            raise SameManifestFileError(
                "Train and test manifests refer to the same file: "
                f"{train_path} and {test_path}"
            )
    except SameManifestFileError:
        raise
    except OSError:
        return


def _read_source_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ManifestUnreadableError(f"Manifest file is unreadable: {path}") from exc


def _decode_source_bytes(source_bytes: bytes, path: Path) -> tuple[str, str]:
    encoding_used = "utf-8-sig" if source_bytes.startswith(_UTF8_BOM) else "utf-8"
    bytes_to_decode = (
        source_bytes[len(_UTF8_BOM) :] if encoding_used == "utf-8-sig" else source_bytes
    )
    try:
        return bytes_to_decode.decode("utf-8", errors="strict"), encoding_used
    except UnicodeDecodeError as exc:
        raise ManifestEncodingError(f"Manifest is not strict UTF-8: {path}") from exc


def _parse_csv_text(text: str, path: Path) -> list[list[str]]:
    if not text.strip():
        raise EmptyManifestError(f"Manifest contains only blank text: {path}")
    try:
        return list(csv.reader(StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise ManifestCsvError(f"Malformed CSV in manifest: {path}") from exc


def _extract_header(rows: Sequence[Sequence[str]], path: Path) -> tuple[str, ...]:
    if not rows:
        raise EmptyManifestError(f"Manifest has no header row: {path}")
    header = tuple(rows[0])
    if not header or all(not cell.strip() for cell in header):
        raise EmptyManifestError(f"Manifest has no header row: {path}")
    return header


def _validate_headers(
    header: tuple[str, ...], path: Path
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    seen_original: set[str] = set()
    seen_normalized: dict[str, str] = {}
    normalized_headers: list[str] = []
    for original in header:
        if not original.strip():
            raise DuplicateHeaderError(f"Blank header in manifest: {path}")
        if original in seen_original:
            raise DuplicateHeaderError(
                f"Duplicate header {original!r} in manifest: {path}"
            )
        seen_original.add(original)
        try:
            normalized = normalize_header(original)
        except ValueError as exc:
            raise DuplicateHeaderError(
                f"Header {original!r} normalizes to empty in manifest: {path}"
            ) from exc
        previous = seen_normalized.get(normalized)
        if previous is not None:
            raise NormalizedHeaderCollisionError(
                "Headers "
                f"{previous!r} and {original!r} normalize to {normalized!r} "
                f"in manifest: {path}"
            )
        seen_normalized[normalized] = original
        normalized_headers.append(normalized)
    return header, tuple(normalized_headers)


def _build_rows(
    rows: Sequence[Sequence[str]],
    original_headers: tuple[str, ...],
    normalized_headers: tuple[str, ...],
    partition: Partition,
    manifest_id: str,
    path: Path,
) -> tuple[list[RawManifestRow], list[str]]:
    raw_rows: list[RawManifestRow] = []
    warnings: list[str] = []
    expected_cells = len(original_headers)
    for row_number, row in enumerate(rows):
        values: list[str | None] = list(row)
        if len(values) > expected_cells:
            raise ManifestCsvError(
                f"Row {row_number} has more cells than headers in manifest: {path}"
            )
        if len(values) < expected_cells:
            warnings.append(
                f"Row {row_number} has fewer cells than headers; "
                "missing trailing cells were set to None."
            )
            values.extend([None] * (expected_cells - len(values)))
        raw_values = dict(zip(original_headers, values, strict=True))
        normalized_values = {
            header: normalize_missing_value(value)
            for header, value in zip(normalized_headers, values, strict=True)
        }
        raw_rows.append(
            RawManifestRow(
                source_manifest_id=manifest_id,
                source_row_number=row_number,
                assigned_partition=partition,
                raw_values=raw_values,
                normalized_header_values=normalized_values,
            )
        )
    if not raw_rows:
        raise EmptyManifestError(f"Manifest has a header but no data rows: {path}")
    return raw_rows, warnings


def _detect_newline_style(source_bytes: bytes) -> str:
    index = 0
    styles: set[str] = set()
    while index < len(source_bytes):
        byte = source_bytes[index]
        if byte == 13:
            if index + 1 < len(source_bytes) and source_bytes[index + 1] == 10:
                styles.add("crlf")
                index += 2
                continue
            styles.add("cr")
        elif byte == 10:
            styles.add("lf")
        index += 1
    if not styles:
        return "none"
    if len(styles) == 1:
        return next(iter(styles))
    return "mixed"
