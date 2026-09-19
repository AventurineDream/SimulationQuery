"""Observational wellness signals, private audit, and tap-out thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..clock import Clock
from ..domain import CastMemberStatus
from ..infrastructure import EventRepository, RecordRepository, SQLiteDatabase
from ..llm.audit import AuditWriter


@dataclass(frozen=True)
class WellnessResult:
    season_id: str
    character_id: str
    signal_number: int
    tapped_out: bool
    status: str
    audit_path: str


@dataclass
class WellnessService:
    """Count explicit out-of-world signals with an optional auto-tap-out policy."""

    database: SQLiteDatabase
    season_id: str
    clock: Clock
    audit_root: str | Path
    auto_tap_out: bool = True
    records: RecordRepository = field(init=False)
    events: EventRepository = field(init=False)
    audit: AuditWriter = field(init=False)

    def __post_init__(self) -> None:
        self.records = RecordRepository(self.database)
        self.events = EventRepository(self.database)
        self.audit = AuditWriter(self.audit_root)

    def record_signal(
        self,
        *,
        character_id: str,
        context: str,
        raw_signal: str,
        intervention: str,
    ) -> WellnessResult:
        """Persist one signal before returning the threshold decision."""
        if not raw_signal.strip():
            raise ValueError("a wellness signal must contain observable text")
        cast = self.records.get_cast_member(
            season_id=self.season_id, character_id=character_id
        )
        if cast is None:
            raise ValueError(f"unknown cast member: {character_id}")
        existing = int(cast["distress_signal_count"])
        if self.auto_tap_out and existing >= 3:
            return WellnessResult(
                season_id=self.season_id,
                character_id=character_id,
                signal_number=existing,
                tapped_out=True,
                status=str(cast["status"]),
                audit_path="",
            )
        signal_number = existing + 1
        tapped_out = self.auto_tap_out and signal_number >= 3
        status = CastMemberStatus.DEPARTED.value if tapped_out else CastMemberStatus.ACTIVE.value
        artifact = self.audit.write_text(
            Path("seasons")
            / self.season_id
            / "wellness"
            / character_id
            / f"signal-{signal_number}.md",
            raw_signal,
        )
        observed_at = self.clock.now().isoformat()
        event_key = f"{self.season_id}:wellness:{character_id}:{signal_number}"
        with self.database.transaction():
            self.records.insert_wellness_event(
                event_id=event_key,
                season_id=self.season_id,
                character_id=character_id,
                context=context,
                signal_number=signal_number,
                observed_at=observed_at,
                intervention=intervention,
            )
            self.records.update_cast_wellness(
                season_id=self.season_id,
                character_id=character_id,
                status=status,
                distress_signal_count=signal_number,
            )
            self.events.append(
                event_id=event_key,
                natural_key=event_key,
                aggregate_type="cast_member",
                aggregate_id=f"{self.season_id}:{character_id}",
                event_type="WellnessSignalObserved",
                payload={
                    "context": context,
                    "signal_number": signal_number,
                    "intervention": intervention,
                    "tapped_out": tapped_out,
                    "audit_path": str(artifact.path),
                },
            )
            self.records.insert_notification(
                notification_id=f"notification:{event_key}",
                kind="WELLNESS",
                season_id=self.season_id,
                payload={
                    "character_id": character_id,
                    "signal_number": signal_number,
                    "tapped_out": tapped_out,
                },
            )
        return WellnessResult(
            season_id=self.season_id,
            character_id=character_id,
            signal_number=signal_number,
            tapped_out=tapped_out,
            status=status,
            audit_path=str(artifact.path),
        )

    def record_manual_intervention(self, *, character_id: str, note: str) -> None:
        """Record a creator control without incrementing actor distress."""
        self.events.append(
            event_id=f"{self.season_id}:manual-intervention:{character_id}:{self.clock.now().isoformat()}",
            natural_key=f"{self.season_id}:manual-intervention:{character_id}:{self.clock.now().isoformat()}",
            aggregate_type="cast_member",
            aggregate_id=f"{self.season_id}:{character_id}",
            event_type="ManualWellnessIntervention",
            payload={"character_id": character_id, "note": note},
        )


__all__ = ["WellnessResult", "WellnessService"]
