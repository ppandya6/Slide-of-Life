"""Tests for pure conservative normalization helpers."""

import pytest

from slidelineage.normalization import (
    normalize_header,
    normalize_identifier_candidate,
    normalize_missing_value,
    normalize_optional_text,
)


def test_header_normalization_examples() -> None:
    assert normalize_header(" Patient ID ") == "patient_id"
    assert normalize_header("Case-Submitter/ID") == "case_submitter_id"
    assert normalize_header("Image\\Path") == "image_path"
    assert normalize_header("Tissue Source Site") == "tissue_source_site"


def test_header_nfkc_case_punctuation_and_underscore_collapse() -> None:
    assert normalize_header(" Ｐａｔｉｅｎｔ---ID!!! ") == "patient_id"


def test_header_empty_result_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_header(" --- /// ")


def test_optional_text_and_missing_values() -> None:
    assert normalize_optional_text(None) is None
    assert normalize_optional_text("  Tumor Label  ") == "Tumor Label"
    assert normalize_missing_value("") is None
    assert normalize_missing_value(" N/A ") is None
    assert normalize_missing_value("null") is None
    assert normalize_missing_value("0") == "0"
    assert normalize_missing_value("false") == "false"
    assert normalize_missing_value("unknown") == "unknown"
    assert normalize_missing_value("not available") == "not available"
    assert normalize_missing_value("nan") == "nan"


def test_identifier_candidate_is_conservative() -> None:
    assert normalize_identifier_candidate("  PAT-001 ") == "pat-001"
    assert normalize_identifier_candidate("00123") == "00123"
    assert normalize_identifier_candidate("A_B.7") == "a_b.7"
    assert normalize_identifier_candidate(" Case   7 ") == "case 7"
    assert normalize_identifier_candidate("none") is None


def test_arbitrary_labels_remain_case_preserved_under_minimal_cleaning() -> None:
    assert normalize_missing_value("  Tumor Label  ") == "Tumor Label"
