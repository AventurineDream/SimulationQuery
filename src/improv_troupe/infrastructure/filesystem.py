"""Validated filesystem roots for private state and public projections.

The workflow writes private audit material and public diary projections through
different roots.  Keeping the validation here makes it reusable by the future
service, CLI, and artifact projector without allowing path traversal or an
accidental private/public overlap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class PathBoundaryError(ValueError):
    """Raised when configured artifact roots are unsafe or ambiguous."""


# Backward-compatible name for the initial root-validation API.
PathConfigurationError = PathBoundaryError


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class DataRoots:
    """The three application roots described by the architecture spec."""

    root: Path
    state: Path
    private: Path
    public: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "DataRoots":
        base = _resolved(Path(root))
        return cls(
            root=base,
            state=base / "state",
            private=base / "private",
            public=base / "public",
        ).validate()

    def validate(self) -> "DataRoots":
        """Return these roots after rejecting overlaps and relative paths."""
        roots = {
            "state": _resolved(self.state),
            "private": _resolved(self.private),
            "public": _resolved(self.public),
        }
        for name, path in roots.items():
            if not path.is_absolute():
                raise PathConfigurationError(f"{name} root must be absolute: {path}")

        items = list(roots.items())
        for index, (left_name, left) in enumerate(items):
            for right_name, right in items[index + 1 :]:
                if _is_within(left, right) or _is_within(right, left):
                    raise PathConfigurationError(
                        f"{left_name} and {right_name} roots must not overlap"
                    )

        return DataRoots(root=_resolved(self.root), **roots)

    def prepare(self) -> "DataRoots":
        """Create roots with conservative permissions and return the validated set."""
        roots = self.validate()
        roots.state.mkdir(parents=True, exist_ok=True)
        roots.private.mkdir(parents=True, exist_ok=True)
        roots.public.mkdir(parents=True, exist_ok=True)
        # State and private artifacts contain prompts, outputs, plans, and
        # wellness records.  Public artifacts are intentionally separate.
        os.chmod(roots.state, 0o700)
        os.chmod(roots.private, 0o700)
        return roots

    def path(self, visibility: str, relative: str | Path) -> Path:
        """Return a root-contained path for one configured visibility root."""
        roots = {"state": self.state, "private": self.private, "public": self.public}
        try:
            root = roots[visibility]
        except KeyError as exc:
            raise PathBoundaryError(f"unknown artifact visibility: {visibility}") from exc
        return safe_path(root, relative)

    def prepare_file_parent(self, visibility: str, relative: str | Path) -> Path:
        """Create the parent directory for a safe artifact path."""
        target = self.path(visibility, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if visibility in {"state", "private"}:
            os.chmod(target.parent, 0o700)
        return target


def safe_path(root: str | Path, relative: str | Path) -> Path:
    """Resolve a relative artifact path while rejecting root escape."""
    root_path = _resolved(Path(root))
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise PathBoundaryError("artifact paths must be relative")
    candidate = _resolved(root_path / relative_path)
    if not _is_within(candidate, root_path):
        raise PathBoundaryError(f"artifact path escapes its root: {relative}")
    return candidate
