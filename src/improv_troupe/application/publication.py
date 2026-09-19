"""Season-qualified review and immutable public diary projection."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..clock import Clock, SystemClock
from ..domain import Publication, PublicationStatus, SeasonStatus, transition_season
from ..infrastructure import DataRoots, EventRepository, RecordRepository, SeasonRepository


class PublicationError(RuntimeError):
    """Raised when a season cannot safely enter or complete publication."""


_PENDING_MODEL_CALLS = frozenset(
    {"PENDING", "STREAMING", "VALIDATING", "WAITING_FOR_MODEL", "MANUAL_REVIEW"}
)
_REVIEW_DECISIONS = frozenset({"PENDING", "CLEARED", "PRIVATE"})
_PUBLIC_DIARY_STATUSES = frozenset({"WRITTEN", "LATE"})


@dataclass(frozen=True)
class PublicationResult:
    publication_id: str
    version: int
    status: str
    eligible_diary_ids: tuple[str, ...] = ()
    output_path: str | None = None
    manifest_sha256: str | None = None


@dataclass
class PublicationService:
    """Construct a public allowlist from explicit creator review decisions."""

    database: object
    roots: DataRoots
    clock: Clock = field(default_factory=SystemClock)
    seasons: SeasonRepository = field(init=False)
    records: RecordRepository = field(init=False)
    events: EventRepository = field(init=False)

    def __post_init__(self) -> None:
        self.roots.prepare()
        self.seasons = SeasonRepository(self.database)
        self.records = RecordRepository(self.database)
        self.events = EventRepository(self.database)

    def begin_review(
        self,
        *,
        season_id: str,
        wellness_confirmed: bool,
        privacy_reviewed: bool,
        consent_confirmed: bool,
        diary_decisions: dict[str, str] | None = None,
    ) -> PublicationResult:
        """Create one review version and record every diary's initial decision."""
        season = self.seasons.get(season_id)
        if season.status not in {
            SeasonStatus.SEASON_COMPLETE,
            SeasonStatus.PRIVATE_COMPLETE,
            SeasonStatus.AWAITING_PUBLISH_REVIEW,
        }:
            raise PublicationError("publication review requires a completed season")
        decisions = diary_decisions or {}
        if any(decision not in _REVIEW_DECISIONS - {"PENDING"} for decision in decisions.values()):
            raise PublicationError("diary decision must be CLEARED or PRIVATE")
        diary_rows = self.records.list_diaries(season_id=season_id)
        known_ids = {str(row["diary_id"]) for row in diary_rows}
        unknown = sorted(set(decisions) - known_ids)
        if unknown:
            raise PublicationError("review names unknown diary IDs: " + ", ".join(unknown))
        if season.status in {SeasonStatus.SEASON_COMPLETE, SeasonStatus.PRIVATE_COMPLETE}:
            awaiting = transition_season(season, SeasonStatus.AWAITING_PUBLISH_REVIEW)
            self.seasons.update(awaiting, expected_version=season.version)
        version = int(
            self.database.connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM publications WHERE season_id = ?",
                (season_id,),
            ).fetchone()[0]
        )
        publication_id = f"{season_id}:publication:v{version:03d}"
        self.records.insert_publication(
            Publication(
                publication_id=publication_id,
                season_id=season_id,
                version=version,
                status=PublicationStatus.REVIEW_REQUIRED,
            )
        )
        self.records.insert_publication_check(
            publication_id=publication_id,
            wellness_confirmed=wellness_confirmed,
            privacy_reviewed=privacy_reviewed,
            consent_confirmed=consent_confirmed,
        )
        for row in diary_rows:
            diary_id = str(row["diary_id"])
            if str(row["status"]) in _PUBLIC_DIARY_STATUSES:
                decision = decisions.get(diary_id, "PENDING")
                reason = "creator review required"
            else:
                decision = "PRIVATE"
                reason = f"not public diary status: {row['status']}"
            self._save_review(
                publication_id=publication_id,
                diary_id=diary_id,
                decision=decision,
                reason=reason,
            )
        return self._evaluate(publication_id)

    def review_diary(
        self,
        *,
        publication_id: str,
        diary_id: str,
        decision: str,
        reason: str | None = None,
    ) -> PublicationResult:
        """Revise one review decision while preserving an immutable edit event."""
        if decision not in _REVIEW_DECISIONS - {"PENDING"}:
            raise PublicationError("diary decision must be CLEARED or PRIVATE")
        publication = self.records.get_publication(publication_id)
        if publication is None:
            raise PublicationError(f"unknown publication: {publication_id}")
        if str(publication["status"]) == PublicationStatus.PUBLISHED.value:
            raise PublicationError("published review decisions are immutable")
        diary = self.database.connection.execute(
            "SELECT diary_id FROM diaries WHERE diary_id = ? AND season_id = ?",
            (diary_id, publication["season_id"]),
        ).fetchone()
        if diary is None:
            raise PublicationError(f"diary does not belong to publication: {diary_id}")
        self._save_review(
            publication_id=publication_id,
            diary_id=diary_id,
            decision=decision,
            reason=reason or "creator review revision",
        )
        return self._evaluate(publication_id)

    def publish(self, *, publication_id: str) -> PublicationResult:
        """Stage and atomically create a new immutable public version."""
        publication = self.records.get_publication(publication_id)
        if publication is None:
            raise PublicationError(f"unknown publication: {publication_id}")
        if str(publication["status"]) == PublicationStatus.PUBLISHED.value:
            return self._result_from_row(publication)
        evaluated = self._evaluate(publication_id)
        if evaluated.status != PublicationStatus.CLEARED.value:
            raise PublicationError("publication review is incomplete")
        checks = self.records.get_publication_check(publication_id)
        if checks is None or not all(
            bool(checks[name])
            for name in ("wellness_confirmed", "privacy_reviewed", "consent_confirmed")
        ):
            raise PublicationError("wellness, privacy, and consent confirmations are required")
        season_id = str(publication["season_id"])
        pending_calls = self.database.connection.execute(
            "SELECT COUNT(*) FROM model_calls WHERE status IN (?, ?, ?, ?, ?) AND ("
            "run_id IN (SELECT run_id FROM runs WHERE season_id = ?) "
            "OR purpose LIKE ? OR purpose LIKE ? OR purpose LIKE ?)",
            (
                "PENDING",
                "STREAMING",
                "VALIDATING",
                "WAITING_FOR_MODEL",
                "MANUAL_REVIEW",
                season_id,
                f"diary:{season_id}:%",
                f"next-day-direction:{season_id}:%",
                f"orientation:{season_id}:%",
            ),
        ).fetchone()[0]
        if int(pending_calls) != 0:
            raise PublicationError("publication has pending model calls")
        season = self.seasons.get(str(publication["season_id"]))
        if season.status is not SeasonStatus.AWAITING_PUBLISH_REVIEW:
            raise PublicationError("season must be awaiting publish review")
        reviews = self.records.list_publication_diary_reviews(publication_id)
        eligible = [str(row["diary_id"]) for row in reviews if str(row["decision"]) == "CLEARED"]
        target = self.roots.path(
            "public",
            f"seasons/{publication['season_id']}/v{int(publication['version']):03d}",
        )
        if target.exists():
            raise PublicationError(f"immutable publication target already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        manifest_bytes, staged = self._stage_public_tree(
            publication=publication,
            eligible_diary_ids=eligible,
            target=target,
        )
        os.replace(staged, target)
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        self.records.update_publication(
            publication_id=publication_id,
            status=PublicationStatus.PUBLISHED.value,
            eligible_diary_ids=eligible,
            output_path=str(target),
            manifest_sha256=manifest_hash,
        )
        published = transition_season(season, SeasonStatus.PUBLISHED)
        self.seasons.update(published, expected_version=season.version)
        self.events.append(
            event_id=f"publication:{publication_id}:published",
            natural_key=f"publication:{publication_id}:published",
            aggregate_type="publication",
            aggregate_id=publication_id,
            event_type="PublicationPublished",
            payload={
                "version": int(publication["version"]),
                "eligible_diary_ids": eligible,
                "manifest_sha256": manifest_hash,
            },
        )
        return PublicationResult(
            publication_id=publication_id,
            version=int(publication["version"]),
            status=PublicationStatus.PUBLISHED.value,
            eligible_diary_ids=tuple(eligible),
            output_path=str(target),
            manifest_sha256=manifest_hash,
        )

    def _save_review(
        self,
        *,
        publication_id: str,
        diary_id: str,
        decision: str,
        reason: str | None,
    ) -> None:
        if decision not in _REVIEW_DECISIONS:
            raise PublicationError(f"unknown diary review decision: {decision}")
        self.records.upsert_publication_diary_review(
            publication_id=publication_id,
            diary_id=diary_id,
            decision=decision,
            reason=reason,
        )
        event_id = f"publication-review:{uuid4().hex}"
        self.events.append(
            event_id=event_id,
            natural_key=event_id,
            aggregate_type="publication",
            aggregate_id=publication_id,
            event_type="PublicationDiaryReviewed",
            payload={"diary_id": diary_id, "decision": decision, "reason": reason},
        )

    def _evaluate(self, publication_id: str) -> PublicationResult:
        publication = self.records.get_publication(publication_id)
        if publication is None:
            raise PublicationError(f"unknown publication: {publication_id}")
        checks = self.records.get_publication_check(publication_id)
        reviews = self.records.list_publication_diary_reviews(publication_id)
        pending = [row for row in reviews if str(row["decision"]) == "PENDING"]
        checks_ready = checks is not None and all(
            bool(checks[name])
            for name in ("wellness_confirmed", "privacy_reviewed", "consent_confirmed")
        )
        status = (
            PublicationStatus.CLEARED.value
            if checks_ready and not pending
            else PublicationStatus.REVIEW_REQUIRED.value
        )
        eligible = [str(row["diary_id"]) for row in reviews if str(row["decision"]) == "CLEARED"]
        if str(publication["status"]) != PublicationStatus.PUBLISHED.value:
            self.records.update_publication(
                publication_id=publication_id,
                status=status,
                eligible_diary_ids=eligible,
            )
        return PublicationResult(
            publication_id=publication_id,
            version=int(publication["version"]),
            status=status,
            eligible_diary_ids=tuple(eligible),
        )

    def _stage_public_tree(self, *, publication, eligible_diary_ids: list[str], target: Path):
        staging = Path(tempfile.mkdtemp(prefix=f".v{int(publication['version']):03d}-", dir=target.parent))
        manifest: dict[str, object] = {
            "season_id": str(publication["season_id"]),
            "publication_version": int(publication["version"]),
            "diaries": [],
        }
        try:
            for diary_id in eligible_diary_ids:
                row = self.records.get_diary_by_id(diary_id)
                if row is None or not row["content_path"]:
                    raise PublicationError(f"cleared diary has no content: {diary_id}")
                source = Path(str(row["content_path"])).expanduser().resolve(strict=True)
                try:
                    source.relative_to(self.roots.private)
                except ValueError as exc:
                    raise PublicationError(f"diary source is outside private root: {diary_id}") from exc
                content = source.read_bytes()
                relative = Path("diaries") / f"day-{int(row['day_number']):02d}" / f"{row['character_id']}.md"
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(0o644)
                manifest["diaries"].append(
                    {
                        "diary_id": diary_id,
                        "day_number": int(row["day_number"]),
                        "character_id": str(row["character_id"]),
                        "path": str(relative),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
            manifest_path = staging / "manifest.json"
            manifest_path.write_bytes(manifest_bytes)
            manifest_path.chmod(0o644)
            for directory in sorted((path for path in staging.rglob("*") if path.is_dir()), reverse=True):
                directory.chmod(0o755)
            staging.chmod(0o755)
            return manifest_bytes, staging
        except Exception:
            _remove_tree(staging)
            raise

    def _result_from_row(self, row) -> PublicationResult:
        eligible = tuple(json.loads(row["eligible_diary_ids_json"]))
        return PublicationResult(
            publication_id=str(row["publication_id"]),
            version=int(row["version"]),
            status=str(row["status"]),
            eligible_diary_ids=eligible,
            output_path=row["output_path"],
            manifest_sha256=row["manifest_sha256"],
        )


def _remove_tree(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


__all__ = ["PublicationError", "PublicationResult", "PublicationService"]
