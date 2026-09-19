"""Private, append-only model-attempt artifact writing with secret redaction."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..infrastructure.filesystem import PathBoundaryError, safe_path


class AuditArtifactConflict(RuntimeError):
    """Raised when an immutable audit path already contains different bytes."""


@dataclass(frozen=True)
class AuditArtifact:
    path: Path
    sha256: str
    byte_length: int


def redact_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Replace explicitly supplied secret values without changing other content."""

    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


class AuditWriter:
    """Write private prompt/output evidence exactly once under one root."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            self.root.chmod(0o700)

    def write_text(
        self,
        relative_path: str | Path,
        text: str,
        *,
        secrets: tuple[str, ...] = (),
    ) -> AuditArtifact:
        content = redact_text(text, secrets).encode("utf-8")
        try:
            target = safe_path(self.root, relative_path)
        except PathBoundaryError:
            raise
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            target.parent.chmod(0o700)
        digest = hashlib.sha256(content).hexdigest()
        if target.exists():
            if target.read_bytes() != content:
                raise AuditArtifactConflict(str(target))
            return AuditArtifact(target, digest, len(content))

        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            if os.name == "posix":
                target.chmod(0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return AuditArtifact(target, digest, len(content))


__all__ = ["AuditArtifact", "AuditArtifactConflict", "AuditWriter", "redact_text"]
