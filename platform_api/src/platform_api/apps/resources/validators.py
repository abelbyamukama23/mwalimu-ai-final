"""Resource upload validation utilities."""

from __future__ import annotations

import os
import zipfile
from io import BytesIO
from typing import BinaryIO

from django.conf import settings
from django.core.exceptions import ValidationError

from .models import ResourceType


class ResourceValidationError(ValidationError):
    """Raised when an uploaded file fails resource validation."""


DEFAULT_MAX_UPLOAD_SIZE = 100 * 1024 * 1024


def _max_upload_size() -> int:
    """Return the configured maximum upload size in bytes."""
    return int(getattr(settings, "RESOURCE_MAX_UPLOAD_SIZE", DEFAULT_MAX_UPLOAD_SIZE))


_CONTENT_TYPE_MAP: dict[str, tuple[str, ...]] = {
    ResourceType.PDF: ("application/pdf",),
    ResourceType.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ResourceType.TXT: ("text/plain",),
}

_EXTENSION_MAP: dict[str, str] = {
    ".pdf": ResourceType.PDF,
    ".docx": ResourceType.DOCX,
    ".txt": ResourceType.TXT,
}


def _validate_size(size: int) -> None:
    """Ensure the uploaded file size is within the configured limit."""
    max_size = _max_upload_size()
    if size <= 0:
        raise ResourceValidationError({"file": "File size must be greater than zero."})
    if size > max_size:
        message = f"File exceeds maximum upload size of {max_size} bytes."
        raise ResourceValidationError({"file": message})


def _validate_filename(filename: str) -> str:
    """Return a safe basename and reject path traversal."""
    basename = os.path.basename(filename)
    if not basename or basename != filename:
        raise ResourceValidationError({"file": "Invalid filename."})
    return basename


def _validate_pdf_signature(content: bytes) -> None:
    """Verify the file signature of a PDF."""
    if not content.startswith(b"%PDF"):
        raise ResourceValidationError(
            {"file": "File does not appear to be a valid PDF."}
        )


def _validate_docx_signature(content: bytes) -> None:
    """Verify the file signature of a DOCX."""
    if not content.startswith(b"PK\x03\x04"):
        raise ResourceValidationError(
            {"file": "File does not appear to be a valid DOCX."}
        )
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            if "[Content_Types].xml" not in archive.namelist():
                raise ResourceValidationError(
                    {"file": "DOCX archive is missing required content types."}
                )
            content_types = archive.read("[Content_Types].xml").decode(
                "utf-8", errors="ignore"
            )
            if "wordprocessingml.document" not in content_types:
                raise ResourceValidationError(
                    {"file": "File does not appear to be a Word document."}
                )
    except zipfile.BadZipFile as exc:
        raise ResourceValidationError(
            {"file": "File does not appear to be a valid DOCX."}
        ) from exc


def _validate_txt_signature(content: bytes, declared_content_type: str) -> None:
    """Verify the file signature of a plain-text file."""
    if not declared_content_type.startswith("text/"):
        raise ResourceValidationError({"file": "Invalid content type for text file."})
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResourceValidationError(
            {"file": "File does not appear to be valid UTF-8 text."}
        ) from exc


def validate_resource_upload(
    resource_type: str,
    filename: str,
    content_type: str,
    size: int,
    content: BinaryIO,
) -> tuple[str, bytes]:
    """Validate an uploaded resource and return (safe_filename, bytes).

    Raises ``ResourceValidationError`` when validation fails.
    """
    if resource_type not in ResourceType.values:
        message = f"Unsupported resource type: {resource_type}."
        raise ResourceValidationError({"resource_type": message})

    safe_filename = _validate_filename(filename)

    name_lower = safe_filename.lower()
    expected_extension = None
    for ext, rtype in _EXTENSION_MAP.items():
        if rtype == resource_type:
            expected_extension = ext
            break
    if expected_extension and not name_lower.endswith(expected_extension):
        message = f"File extension does not match resource type {resource_type}."
        raise ResourceValidationError({"file": message})

    allowed_content_types = _CONTENT_TYPE_MAP.get(resource_type, ())
    if content_type not in allowed_content_types:
        message = f"Content type '{content_type}' is not allowed for {resource_type}."
        raise ResourceValidationError({"file": message})

    _validate_size(size)

    data = content.read()

    if resource_type == ResourceType.PDF:
        _validate_pdf_signature(data)
    elif resource_type == ResourceType.DOCX:
        _validate_docx_signature(data)
    elif resource_type == ResourceType.TXT:
        _validate_txt_signature(data, content_type)

    return safe_filename, data
