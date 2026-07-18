"""Tests for deterministic CSV manifest ingestion."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

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
from slidelineage.ingest import compute_file_sha256, load_manifest, load_manifest_pair
from slidelineage.models import (
    LoadedManifest,
    LoadedManifestPair,
    Partition,
    RawManifestRow,
)


def write_bytes(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def write_text(path: Path, content: str, newline: str = "") -> Path:
    path.write_text(content, encoding="utf-8", newline=newline)
    return path


def basic_manifest(path: Path, content: str = "Patient ID,Label\nP1,Tumor\n") -> Path:
    return write_text(path, content)


def test_compute_file_sha256_known_bytes(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "manifest.csv", b"abc\r\n")

    assert compute_file_sha256(path) == hashlib.sha256(b"abc\r\n").hexdigest()


def test_missing_file_and_directory_rejected(tmp_path: Path) -> None:
    with pytest.raises(ManifestNotFoundError, match="missing.csv"):
        load_manifest(tmp_path / "missing.csv", Partition.train, "train_manifest")
    with pytest.raises(ManifestUnreadableError, match="not a regular file"):
        load_manifest(tmp_path, Partition.train, "train_manifest")


def test_zero_byte_and_blank_only_files_rejected(tmp_path: Path) -> None:
    with pytest.raises(EmptyManifestError, match="empty"):
        load_manifest(
            write_bytes(tmp_path / "zero.csv", b""), Partition.train, "train_manifest"
        )
    with pytest.raises(EmptyManifestError, match="blank"):
        load_manifest(
            write_text(tmp_path / "blank.csv", "  \n\t\n"),
            Partition.train,
            "train_manifest",
        )


def test_strict_utf8_and_bom_handling(tmp_path: Path) -> None:
    utf8 = basic_manifest(tmp_path / "utf8.csv")
    bom = write_bytes(tmp_path / "bom.csv", b"\xef\xbb\xbfPatient ID\nP1\n")

    assert (
        load_manifest(utf8, Partition.train, "train_manifest").encoding_used == "utf-8"
    )
    assert (
        load_manifest(bom, Partition.train, "train_manifest").encoding_used
        == "utf-8-sig"
    )
    with pytest.raises(ManifestEncodingError, match="UTF-8"):
        load_manifest(
            write_bytes(tmp_path / "bad.csv", b"Patient\n\xff\n"),
            Partition.train,
            "train_manifest",
        )


def test_newline_detection_lf_crlf_cr_mixed_and_none(tmp_path: Path) -> None:
    assert (
        load_manifest(
            write_bytes(tmp_path / "lf.csv", b"A\n1\n"), Partition.train, "m"
        ).newline_style
        == "lf"
    )
    assert (
        load_manifest(
            write_bytes(tmp_path / "crlf.csv", b"A\r\n1\r\n"), Partition.train, "m"
        ).newline_style
        == "crlf"
    )
    assert (
        load_manifest(
            write_bytes(tmp_path / "cr.csv", b"A\r1\r"), Partition.train, "m"
        ).newline_style
        == "cr"
    )
    assert (
        load_manifest(
            write_bytes(tmp_path / "mixed.csv", b"A\r\n1\n"), Partition.train, "m"
        ).newline_style
        == "mixed"
    )


def test_valid_csv_preserves_order_rows_digest_and_minimal_values(
    tmp_path: Path,
) -> None:
    path = basic_manifest(
        tmp_path / "manifest.csv",
        "Patient ID,Label,Image Path\n  P1  ,Tumor A,img/One.PNG\n",
    )
    loaded = load_manifest(path, Partition.train, "train_manifest")

    assert loaded.source.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert loaded.original_headers == ("Patient ID", "Label", "Image Path")
    assert loaded.normalized_headers == ("patient_id", "label", "image_path")
    assert loaded.rows[0].source_row_number == 0
    assert loaded.rows[0].raw_values["Patient ID"] == "  P1  "
    assert loaded.rows[0].normalized_header_values["patient_id"] == "P1"
    assert loaded.rows[0].normalized_header_values["label"] == "Tumor A"
    assert (
        loaded.model_dump_json()
        == load_manifest(path, Partition.train, "train_manifest").model_dump_json()
    )


def test_quoted_comma_and_embedded_newline(tmp_path: Path) -> None:
    path = write_text(tmp_path / "quoted.csv", 'ID,Note\n1,"a,b"\n2,"line1\nline2"\n')
    loaded = load_manifest(path, Partition.train, "train_manifest")

    assert loaded.rows[0].raw_values["Note"] == "a,b"
    assert loaded.rows[1].raw_values["Note"] == "line1\nline2"
    assert loaded.rows[1].source_row_number == 1


def test_blank_duplicate_and_normalized_duplicate_headers(tmp_path: Path) -> None:
    with pytest.raises(DuplicateHeaderError, match="Blank header"):
        load_manifest(
            write_text(tmp_path / "blank_header.csv", "ID, \n1,2\n"),
            Partition.train,
            "m",
        )
    with pytest.raises(DuplicateHeaderError, match="Duplicate header"):
        load_manifest(
            write_text(tmp_path / "dup_header.csv", "ID,ID\n1,2\n"),
            Partition.train,
            "m",
        )
    with pytest.raises(NormalizedHeaderCollisionError, match="normalize"):
        load_manifest(
            write_text(tmp_path / "norm_dup.csv", "Patient-ID,Patient ID\n1,2\n"),
            Partition.train,
            "m",
        )


def test_short_rows_warn_and_extra_cells_reject(tmp_path: Path) -> None:
    short = load_manifest(
        write_text(tmp_path / "short.csv", "A,B,C\n1,2\n"), Partition.train, "m"
    )

    assert short.rows[0].raw_values["C"] is None
    assert short.rows[0].normalized_header_values["c"] is None
    assert "Row 0" in short.warnings[0]
    with pytest.raises(ManifestCsvError, match="more cells"):
        load_manifest(
            write_text(tmp_path / "extra.csv", "A,B\n1,2,3\n"), Partition.train, "m"
        )


def test_empty_manifest_after_header_rejected_and_row_numbering(tmp_path: Path) -> None:
    with pytest.raises(EmptyManifestError, match="no data"):
        load_manifest(
            write_text(tmp_path / "header_only.csv", "A,B\n"), Partition.train, "m"
        )
    loaded = load_manifest(
        write_text(tmp_path / "rows.csv", "A\n1\n2\n"), Partition.train, "m"
    )
    assert [row.source_row_number for row in loaded.rows] == [0, 1]


def test_malformed_csv_rejected(tmp_path: Path) -> None:
    with pytest.raises(ManifestCsvError, match="Malformed"):
        load_manifest(
            write_text(tmp_path / "bad.csv", 'A,B\n"unterminated,2\n'),
            Partition.train,
            "m",
        )


def test_manifest_pair_assignment_ids_path_retention_and_serialization(
    tmp_path: Path,
) -> None:
    train = basic_manifest(tmp_path / "train.csv", "ID\nT1\n")
    test = basic_manifest(tmp_path / "test.csv", "ID\nS1\n")
    config = AuditConfig(
        train_manifest=train, test_manifest=test, output_dir=tmp_path / "out"
    )
    pair = load_manifest_pair(config)

    assert pair.train.source.assigned_partition is Partition.train
    assert pair.test.source.assigned_partition is Partition.test
    assert pair.train.source.manifest_id == "train_manifest"
    assert pair.test.source.manifest_id == "test_manifest"
    assert pair.train.source.path == train
    assert pair.model_dump_json() == load_manifest_pair(config).model_dump_json()


def test_same_literal_and_absolute_alias_rejected(tmp_path: Path) -> None:
    train = basic_manifest(tmp_path / "train.csv")
    with pytest.raises(ValueError, match="must differ"):
        AuditConfig(
            train_manifest=train, test_manifest=train, output_dir=tmp_path / "out"
        )
    with pytest.raises(ValueError, match="must differ"):
        AuditConfig(
            train_manifest=train,
            test_manifest=train.resolve(),
            output_dir=tmp_path / "out",
        )


def test_symlink_alias_rejected_when_supported(tmp_path: Path) -> None:
    train = basic_manifest(tmp_path / "train.csv")
    link = tmp_path / "link.csv"
    try:
        link.symlink_to(train)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(SameManifestFileError):
        load_manifest_pair(
            AuditConfig(
                train_manifest=train, test_manifest=link, output_dir=tmp_path / "out"
            )
        )


def test_relative_and_absolute_alias_rejected_from_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    train = basic_manifest(tmp_path / "train.csv")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SameManifestFileError):
        load_manifest_pair(
            AuditConfig(
                train_manifest=Path("train.csv"),
                test_manifest=train.resolve(),
                output_dir=Path("out"),
            )
        )


def test_contract_invariants_extras_and_frozen(tmp_path: Path) -> None:
    loaded = load_manifest(
        basic_manifest(tmp_path / "manifest.csv"), Partition.train, "train_manifest"
    )

    assert loaded.source.row_count == len(loaded.rows)
    assert all(
        row.source_manifest_id == loaded.source.manifest_id for row in loaded.rows
    )
    assert all(
        row.assigned_partition is loaded.source.assigned_partition
        for row in loaded.rows
    )
    with pytest.raises(ValidationError):
        RawManifestRow(
            source_manifest_id="m",
            source_row_number=0,
            assigned_partition=Partition.train,
            raw_values={},
            normalized_header_values={},
            extra="not allowed",
        )
    with pytest.raises(ValidationError):
        loaded.source.row_count = 99  # type: ignore[misc]


def test_loaded_manifest_pair_model_validation(tmp_path: Path) -> None:
    train = load_manifest(
        basic_manifest(tmp_path / "train.csv"), Partition.train, "train_manifest"
    )
    wrong_test = load_manifest(
        basic_manifest(tmp_path / "test.csv"), Partition.train, "test_manifest"
    )
    with pytest.raises(ValidationError, match="test manifest"):
        LoadedManifestPair(train=train, test=wrong_test)
    with pytest.raises(ValidationError, match="row_count"):
        LoadedManifest(
            source=train.source.model_copy(update={"row_count": 99}),
            original_headers=train.original_headers,
            normalized_headers=train.normalized_headers,
            rows=train.rows,
            encoding_used=train.encoding_used,
            newline_style=train.newline_style,
        )
