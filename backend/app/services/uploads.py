"""
Precision AI - Attachment validation.
The client's Content-Type and file name are never trusted: the extension must be on the allow-list, the bytes
must actually be of that type (magic numbers; text must decode and contain no NUL bytes), and the stored file
gets a random name inside UPLOAD_DIR. The original name is kept only as a sanitised display label.
"""

import re
import unicodedata
from pathlib import Path
from typing import Optional

# extension -> canonical content type
ALLOWED_EXTENSIONS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".pdf": "application/pdf", ".txt": "text/plain", ".log": "text/plain",
}
STORED_EXTENSION = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp",
                    "application/pdf": ".pdf", "text/plain": ".txt"}
MAX_NAME_CHARS = 120


class UploadRejected(ValueError):
    pass


def sniff(data: bytes) -> Optional[str]:
    """Content type from the file's own bytes, or None when it is not an allowed kind of file."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return "text/plain" if _is_text(data) else None


def _is_text(data: bytes) -> bool:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):  # UTF-16 with BOM (Windows PowerShell / Event Viewer exports)
        try:
            data.decode("utf-16")
            return True
        except UnicodeDecodeError:
            return False
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def safe_filename(name: Optional[str]) -> str:
    """Display name: last path segment only, no control characters, conservative character set."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[\x00-\x1f\x7f]", "", base)
    base = re.sub(r"[^\w.\- ()]+", "_", base).strip(" ._")
    if not base:
        return "upload"
    stem, dot, ext = base.rpartition(".")
    if dot and len(base) > MAX_NAME_CHARS:
        return stem[:MAX_NAME_CHARS - len(ext) - 1] + "." + ext
    return base[:MAX_NAME_CHARS]


def validate(filename: Optional[str], data: bytes) -> tuple[str, str]:
    """Return (display name, content type) or raise UploadRejected."""
    display = safe_filename(filename)
    ext = Path(display).suffix.lower()
    expected = ALLOWED_EXTENSIONS.get(ext)
    if expected is None:
        raise UploadRejected("Only PNG, JPG, GIF, WEBP, PDF, TXT and LOG files are allowed")
    if not data:
        raise UploadRejected("The file is empty")
    actual = sniff(data)
    if actual != expected:
        raise UploadRejected(f"The file content does not match its {ext} extension")
    return display, actual


def storage_path(folder: Path, token: str, content_type: str) -> Path:
    """Random on-disk name inside `folder`; refuses anything that would resolve elsewhere."""
    root = folder.resolve()
    path = (root / f"{token}{STORED_EXTENSION[content_type]}").resolve()
    if path.parent != root:
        raise UploadRejected("Invalid storage path")
    return path


def inside(folder: Path, path: str) -> Optional[Path]:
    """Resolve a stored path, but only if it is a file inside `folder`."""
    resolved = Path(path).resolve()
    return resolved if resolved.parent == folder.resolve() and resolved.is_file() else None
