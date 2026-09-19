"""Durable diary and end-of-day orchestration for the season worker."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from ..clock import Clock
from ..domain import diary_cutoff_at
from ..infrastructure import EventRepository, RecordRepository, SeasonRepository, WorkQueue
from .daily import DailyDirector, DayClosureService
from .diaries import DiaryActor, DiaryService
from .wellness import WellnessService


@dataclass
class SeasonDayCoordinator:
    """Attach one diary choice/write opportunity to each scene slot.

    The coordinator keeps day closure as durable queue work. If the process
    stops between the third run and the cutoff, the queued ``CLOSE_DAY`` item
    is recovered by the normal lease/catch-up path and the next-day direction
    is still gated on a closed day.
    """

    database: object
    clock: Clock
    scene_factory: Callable[[Mapping[str, object]], object]
    strict_rehearsal_acceptance: bool = False
    strict_diary_word_count: bool = False
    review_diary_fidelity: bool = False
    validate_diary_claims: bool = False
    sessions_per_day: int = 3
    final_day_number: int | None = None
    queue: WorkQueue = field(init=False)
    records: RecordRepository = field(init=False)
    seasons: SeasonRepository = field(init=False)
    events: EventRepository = field(init=False)

    def __post_init__(self) -> None:
        self.queue = WorkQueue(self.database)
        self.records = RecordRepository(self.database)
        self.seasons = SeasonRepository(self.database)
        self.events = EventRepository(self.database)

    async def after_scene(
        self,
        payload: Mapping[str, object],
        scene,
        scene_result,
        *,
        allow_diary_repair: bool = False,
    ) -> None:
        """Create/use the day diary obligations after one scene resolves."""
        season_id = str(payload["season_id"])
        day_number, slot_number = self._slot_metadata(payload)
        season = self.seasons.get(season_id)
        if season.opening is None:
            raise ValueError(f"season {season_id} has no opening for diary workflow")
        original_date = self._original_date(season_id, day_number)
        actors = tuple(
            DiaryActor(
                character_id=actor.character_id,
                name=actor.name,
                role_sheet=actor.role_sheet,
                executor=actor.executor,
                known_memory=actor.known_memory,
                actor_sheet=actor.actor_sheet,
            )
            for actor in scene.actors
        )
        diary_service = DiaryService(
            season_id=season_id,
            day_number=day_number,
            actors=actors,
            clock=self.clock,
            wellness=WellnessService(
                database=self.database,
                season_id=season_id,
                clock=self.clock,
                audit_root=actors[0].executor.audit.root,
                auto_tap_out=season.auto_tap_out,
            ),
            final_slot_number=self.sessions_per_day,
            strict_word_count=self.strict_diary_word_count,
            validate_claims=self.validate_diary_claims,
        )
        diary_service.ensure_obligations()
        cutoff = self._provisional_cutoff(season_id, day_number, slot_number)
        accepted_scene = tuple(scene_result.transcript.script_view(include_audit=False).splitlines())
        for actor in actors:
            diary_result = await diary_service.write_after_run(
                actor,
                current_slot_number=slot_number,
                accepted_scene=accepted_scene,
                cutoff_at=cutoff,
                allow_repair=allow_diary_repair,
            )
            if (
                self.strict_rehearsal_acceptance
                and slot_number == self.sessions_per_day
                and diary_result.status == "PRIVATE"
                and self._diary_repairable(diary_result.diary_id)
                and not allow_diary_repair
            ):
                # A strict rehearsal may make one provenance-preserving format
                # repair before day closure. This keeps the rejected artifact
                # and diagnostics, but lets a corrected diary participate in
                # the next-day direction instead of repairing continuity after
                # that direction has already been fixed.
                await diary_service.write_after_run(
                    actor,
                    current_slot_number=slot_number,
                    accepted_scene=accepted_scene,
                    cutoff_at=cutoff,
                    allow_repair=True,
                )

        if self.review_diary_fidelity:
            for actor in actors:
                await diary_service.review_fidelity(
                    actor,
                    accepted_scene=accepted_scene,
                    reviewer=scene.orchestrator,
                )

        if slot_number != self.sessions_per_day:
            return
        third_run_resolved_at = _utc(self.clock.now())
        closure = DayClosureService(
            season_id=season_id,
            day_number=day_number,
            original_date=original_date,
            active_character_ids=tuple(actor.character_id for actor in actors),
            database=self.database,
            clock=self.clock,
        )
        result = closure.close_if_ready(
            run_statuses=self._day_run_statuses(season_id, day_number),
            third_run_resolved_at=third_run_resolved_at,
            now=self.clock.now(),
        )
        if result.status == "CLOSED":
            await self._write_direction_if_needed(
                season_id=season_id,
                day_number=day_number,
                run_id=str(payload["run_id"]),
            )
            return
        self._enqueue_close_day(
            season_id=season_id,
            day_number=day_number,
            run_id=str(payload["run_id"]),
            third_run_resolved_at=third_run_resolved_at,
            available_at=result.cutoff_at,
        )

    async def close_day(self, payload: Mapping[str, object]) -> None:
        """Resolve the cutoff work item and, if closed, direct the next day."""
        season_id = str(payload["season_id"])
        day_number = int(payload["day_number"])
        season = self.seasons.get(season_id)
        closure = DayClosureService(
            season_id=season_id,
            day_number=day_number,
            original_date=self._original_date(season_id, day_number),
            active_character_ids=tuple(
                member.character_id
                for member in season.cast
                if _status_value(member.status) == "ACTIVE"
            ),
            database=self.database,
            clock=self.clock,
        )
        third_run_resolved_at = _parse_timestamp(str(payload["third_run_resolved_at"]))
        result = closure.close_if_ready(
            run_statuses=self._day_run_statuses(season_id, day_number),
            third_run_resolved_at=third_run_resolved_at,
            now=self.clock.now(),
        )
        if result.status == "CLOSED":
            await self._write_direction_if_needed(
                season_id=season_id,
                day_number=day_number,
                run_id=str(payload["run_id"]),
            )
        elif result.status == "OPEN":
            self._enqueue_close_day(
                season_id=season_id,
                day_number=day_number,
                run_id=str(payload["run_id"]),
                third_run_resolved_at=third_run_resolved_at,
                available_at=result.cutoff_at,
            )

    async def _write_direction_if_needed(
        self, *, season_id: str, day_number: int, run_id: str
    ) -> None:
        if day_number >= 7 or (
            self.final_day_number is not None and day_number >= self.final_day_number
        ):
            return
        target_day = day_number + 1
        if any(
            str(row["event_type"]) == "NextDayDirectionCreated"
            and _event_target_day(row) == target_day
            for row in self.events.list_for_aggregate(season_id)
        ):
            return
        season = self.seasons.get(season_id)
        if season.opening is None or season.private_plan is None:
            raise ValueError(f"season {season_id} is missing private direction inputs")
        scene = self.scene_factory({"season_id": season_id, "run_id": run_id})
        closed_diaries = self._closed_diary_text(
            season_id,
            day_number,
            require_fidelity_review=self.review_diary_fidelity,
        )
        accepted_canon, scene_transcript = self._day_story_context(
            season_id, day_number
        )
        await DailyDirector(
            season_id=season_id,
            source_day_number=day_number,
            opening=season.opening,
            private_plan=season.private_plan,
            orchestrator=scene.orchestrator,
            accepted_canon=accepted_canon,
            scene_transcript=scene_transcript,
            enforce_continuity=self.strict_rehearsal_acceptance,
        ).write_next_day(
            closed_diaries=closed_diaries,
            day_is_closed=True,
        )

    def _enqueue_close_day(
        self,
        *,
        season_id: str,
        day_number: int,
        run_id: str,
        third_run_resolved_at: datetime,
        available_at: datetime,
    ) -> None:
        self.queue.enqueue(
            work_id=f"work:close-day:{season_id}:{day_number}",
            natural_key=f"close-day:{season_id}:{day_number}",
            kind="CLOSE_DAY",
            payload={
                "season_id": season_id,
                "day_number": day_number,
                "run_id": run_id,
                "third_run_resolved_at": third_run_resolved_at.isoformat(),
            },
            available_at=_utc(available_at).isoformat(),
            priority=-50,
        )

    def _day_run_statuses(self, season_id: str, day_number: int) -> tuple[str, ...]:
        rows = self.database.connection.execute(
            "SELECT r.status FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND s.day_number = ? ORDER BY s.slot_number",
            (season_id, day_number),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def _diary_repairable(self, diary_id: str) -> bool:
        """Return whether strict rehearsal permits one private correction."""

        row = self.database.connection.execute(
            "SELECT event_type FROM domain_events "
            "WHERE aggregate_type = 'diary' AND aggregate_id = ? "
            "ORDER BY rowid DESC LIMIT 1",
            (diary_id,),
        ).fetchone()
        return row is not None and str(row["event_type"]) in {
            "DiaryFormatInvalid",
            "DiaryEvidenceInvalid",
            "DiaryLengthInvalid",
            "DiarySafetyInvalid",
        }

    def _slot_metadata(self, payload: Mapping[str, object]) -> tuple[int, int]:
        if payload.get("day_number") is not None and payload.get("slot_number") is not None:
            return int(payload["day_number"]), int(payload["slot_number"])
        row = self.database.connection.execute(
            "SELECT s.day_number, s.slot_number FROM runs r "
            "JOIN schedule_slots s ON s.slot_id = r.slot_id WHERE r.run_id = ?",
            (str(payload["run_id"]),),
        ).fetchone()
        if row is None:
            raise ValueError(f"no schedule metadata for run {payload['run_id']}")
        return int(row["day_number"]), int(row["slot_number"])

    def _original_date(self, season_id: str, day_number: int) -> date:
        row = self.database.connection.execute(
            "SELECT scheduled_local FROM schedule_slots "
            "WHERE season_id = ? AND day_number = ? ORDER BY slot_number LIMIT 1",
            (season_id, day_number),
        ).fetchone()
        if row is None:
            raise ValueError(f"no schedule for {season_id} day {day_number}")
        return datetime.fromisoformat(str(row[0])).date()

    def _provisional_cutoff(self, season_id: str, day_number: int, slot_number: int) -> datetime:
        if slot_number < self.sessions_per_day:
            return datetime.max.replace(tzinfo=timezone.utc)
        return diary_cutoff_at(_utc(self.clock.now()))

    def _closed_diary_text(
        self,
        season_id: str,
        day_number: int,
        *,
        require_fidelity_review: bool = False,
    ) -> tuple[str, ...]:
        values: list[str] = []
        for row in self.records.list_diaries(season_id=season_id, day_number=day_number):
            path = row["content_path"]
            if path and require_fidelity_review and not self._fidelity_allows_context(
                str(row["diary_id"])
            ):
                values.append(
                    f"{row['character_id']}: diary withheld pending causal-fidelity review"
                )
                continue
            if path:
                values.append(Path(str(path)).read_text(encoding="utf-8"))
            else:
                values.append(f"{row['character_id']}: diary unavailable ({row['status']})")
        return tuple(values)

    def _fidelity_allows_context(self, diary_id: str) -> bool:
        """Only an explicit accepted review may expose a diary to direction."""

        for row in reversed(self.events.list_for_aggregate(diary_id)):
            event_type = str(row["event_type"])
            if event_type == "DiaryFidelityReviewed":
                try:
                    payload = json.loads(str(row["payload_json"]))
                except (TypeError, ValueError):
                    return False
                return isinstance(payload, dict) and payload.get("review_status") == "ACCEPTED"
            if event_type == "DiaryFidelityReviewUnavailable":
                return False
        return False

    def _day_story_context(
        self, season_id: str, day_number: int
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Rebuild the closed day's accepted shared play from durable records."""

        names = {
            str(row["character_id"]): str(row["name"])
            for row in self.database.connection.execute(
                "SELECT character_id, name FROM cast_members WHERE season_id = ?",
                (season_id,),
            )
        }
        turn_rows = self.database.connection.execute(
            "SELECT t.rowid AS insertion_order, s.run_number, s.slot_number, "
            "t.turn_id, t.run_id, t.round_number, t.character_id, t.disposition, "
            "t.content_path, t.accepted_sequence, t.caused_by_turn_id FROM turns t "
            "JOIN runs r ON r.run_id = t.run_id "
            "JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.season_id = ? AND s.day_number = ? "
            "AND t.disposition IN "
            "('NARRATION_ACCEPT', 'ACCEPT', 'ACCEPT_AFTER_CORRECTION', "
            "'NEUTRAL_INTERRUPTION')",
            (season_id, day_number),
        ).fetchall()
        turn_rows = _ordered_accepted_day_rows(turn_rows)
        transcript: list[str] = []
        last_run: int | None = None
        for row in turn_rows:
            path = row["content_path"]
            if not path:
                raise ValueError("accepted day turn has no content artifact")
            run_number = int(row["run_number"])
            if run_number != last_run:
                transcript.append(
                    f"RUN {run_number} · DAY {day_number} · SLOT {int(row['slot_number'])}"
                )
                last_run = run_number
            content = Path(str(path)).read_text(encoding="utf-8").strip()
            character_id = str(row["character_id"])
            if str(row["disposition"]) == "NARRATION_ACCEPT":
                transcript.append(f"GAME MASTER: {content}")
            elif character_id.startswith("__interruption__:"):
                transcript.append(f"GAME MASTER INTERRUPTION: {content}")
            else:
                transcript.append(f"{names.get(character_id, character_id)}: {content}")

        canon: list[str] = []
        seen: set[str] = set()
        event_rows = self.database.connection.execute(
            "SELECT e.payload_json FROM domain_events e "
            "JOIN runs r ON r.run_id = e.aggregate_id "
            "JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE e.aggregate_type = 'run' AND e.event_type = 'OrchestratorRoundAccepted' "
            "AND r.season_id = ? AND s.day_number = ? "
            "ORDER BY s.run_number, e.created_at, e.event_id",
            (season_id, day_number),
        ).fetchall()
        for row in event_rows:
            try:
                payload = json.loads(str(row["payload_json"]))
            except (TypeError, ValueError) as exc:
                raise ValueError("day canon event has invalid JSON") from exc
            for value in payload.get("canon_updates", []):
                claim = str(value).strip()
                if claim and claim not in seen:
                    seen.add(claim)
                    canon.append(claim)
        return tuple(canon), tuple(transcript)


def _event_target_day(row) -> int | None:
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, ValueError):
        return None
    value = payload.get("target_day_number")
    return int(value) if value is not None else None


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _ordered_accepted_day_rows(rows):
    """Use durable causal order per run, with an honest legacy fallback."""
    grouped: dict[str, list[object]] = {}
    for row in rows:
        grouped.setdefault(str(row["run_id"]), []).append(row)
    ordered: list[object] = []
    for run_rows in sorted(
        grouped.values(), key=lambda values: (int(values[0]["run_number"]), str(values[0]["run_id"]))
    ):
        by_id = {str(row["turn_id"]): row for row in run_rows}
        explicit = all(row["accepted_sequence"] is not None for row in run_rows)
        if explicit:
            for row in run_rows:
                if str(row["disposition"]) == "NARRATION_ACCEPT":
                    continue
                parent_id = row["caused_by_turn_id"]
                parent = by_id.get(str(parent_id)) if parent_id else None
                if (
                    parent is None
                    or str(parent["disposition"]) != "NARRATION_ACCEPT"
                    or int(parent["round_number"]) != int(row["round_number"])
                    or int(parent["accepted_sequence"]) >= int(row["accepted_sequence"])
                ):
                    explicit = False
                    break
        ordered.extend(
            sorted(
                run_rows,
                key=(
                    (lambda row: int(row["accepted_sequence"]))
                    if explicit
                    else (
                        lambda row: (
                            int(row["round_number"]),
                            0 if str(row["disposition"]) == "NARRATION_ACCEPT" else 1,
                            int(row["insertion_order"]),
                        )
                    )
                ),
            )
        )
    return ordered


__all__ = ["SeasonDayCoordinator"]
