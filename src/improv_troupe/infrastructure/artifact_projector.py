"""Idempotent filesystem projection of committed artifact intents."""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone

from .filesystem import DataRoots


class ArtifactProjectionError(RuntimeError):
    """Raised when an immutable artifact would be overwritten or escapes roots."""


class ArtifactProjector:
    """Project outbox rows after domain state has committed."""

    def __init__(self, roots: DataRoots, outbox_repository: object):
        self.roots = roots
        self.outbox = outbox_repository

    def project_file(
        self, *, visibility: str, relative_path: str, content: str | bytes, immutable: bool = True
    ) -> str:
        """Write one artifact safely; repeating the same content is a no-op."""
        raw = content.encode("utf-8") if isinstance(content, str) else content
        target = self.roots.prepare_file_parent(visibility, relative_path)
        digest = hashlib.sha256(raw).hexdigest()
        if target.exists():
            existing = target.read_bytes()
            if hashlib.sha256(existing).hexdigest() != digest:
                if immutable:
                    raise ArtifactProjectionError(f"immutable artifact already exists: {target}")
                raise ArtifactProjectionError(f"refusing implicit artifact overwrite: {target}")
            return str(target)

        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            if os.name == "posix":
                target.chmod(0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return str(target)

    def project_pending(self) -> int:
        """Project committed outbox rows and mark each one after its fsync."""
        projected = 0
        for row in self.outbox.pending():
            content = bytes(row["content"])
            path = self.project_file(
                visibility=row["visibility"],
                relative_path=row["relative_path"],
                content=content,
                immutable=bool(row["immutable"]),
            )
            metadata = self.file_metadata(content)
            self.outbox.mark_projected(
                row["outbox_id"],
                path=path,
                sha256=str(metadata["sha256"]),
                byte_length=int(metadata["byte_length"]),
            )
            projected += 1
        return projected

    @staticmethod
    def file_metadata(content: str | bytes) -> dict[str, object]:
        raw = content.encode("utf-8") if isinstance(content, str) else content
        return {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_length": len(raw),
            "projected_at": datetime.now(timezone.utc).isoformat(),
        }
