"""Project-specific exception types for SlideLineage."""


class SlideLineageError(Exception):
    """Base exception for SlideLineage errors."""


class ConfigurationError(SlideLineageError):
    """Raised when user configuration cannot be validated or selected."""


class UnknownPolicyProfileError(ConfigurationError):
    """Raised when a requested SplitPolicy profile is not registered."""


class ManifestError(SlideLineageError):
    """Raised when a manifest cannot be safely loaded."""


class ManifestNotFoundError(ManifestError):
    """Raised when a manifest path does not exist."""


class ManifestUnreadableError(ManifestError):
    """Raised when a manifest path is not a readable regular file."""


class ManifestEncodingError(ManifestError):
    """Raised when manifest bytes cannot be decoded with supported encodings."""


class ManifestCsvError(ManifestError):
    """Raised when manifest CSV structure is malformed or unsafe."""


class EmptyManifestError(ManifestCsvError):
    """Raised when a manifest has no usable CSV records."""


class DuplicateHeaderError(ManifestCsvError):
    """Raised when original headers are blank or duplicated."""


class NormalizedHeaderCollisionError(ManifestCsvError):
    """Raised when distinct original headers normalize to the same key."""


class SameManifestFileError(ManifestError):
    """Raised when train and test manifests refer to the same file."""
