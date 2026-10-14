"""Private actor orientation before a season can perform."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..infrastructure import EventRepository
from ..llm.adapter import NormalizedCallStatus
from ..llm.context import build_orientation_messages
from ..llm.diary_audience import DIARY_AUDIENCE_VERSION
from ..llm.structured import StructuredOutputError, parse_orientation_output
from .model_calls import ModelCallExecutor
from .wellness import WellnessService


@dataclass(frozen=True)
class OrientationActor:
    character_id: str
    name: str
    executor: ModelCallExecutor


@dataclass(frozen=True)
class OrientationResult:
    character_id: str
    status: str
    accepted: bool
    signal_number: int | None = None
    tapped_out: bool = False
    reason: str | None = None


@dataclass
class OrientationService:
    season_id: str
    wellness: WellnessService | None = None
    auto_tap_out: bool = True
    events: EventRepository | None = field(init=False)

    def __post_init__(self) -> None:
        if self.wellness is None:
            self.events = None  # type: ignore[assignment]
        else:
            self.events = EventRepository(self.wellness.database)

    async def orient(self, actor: OrientationActor) -> OrientationResult:
        purpose = f"orientation:{self.season_id}:{actor.character_id}"
        attempt = actor.executor.calls.next_attempt(run_id=None, purpose=purpose)
        call_id = f"{self.season_id}:orientation:{actor.character_id}:a{attempt}"
        messages = build_orientation_messages(
            actor_name=actor.name,
            auto_tap_out=self.auto_tap_out,
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    "Return only <ACCEPTED>true|false</ACCEPTED> and optional "
                    "<WELLNESS_SIGNAL>...</WELLNESS_SIGNAL>."
                ),
            }
        )
        result = await actor.executor.execute(
            call_id=call_id,
            run_id=None,
            purpose=purpose,
            attempt=attempt,
            messages=messages,
            schema_name="orientation",
            tagged_format_instructions=(
                "<ACCEPTED>true|false</ACCEPTED><WELLNESS_SIGNAL>...</WELLNESS_SIGNAL>"
            ),
            character_id=actor.character_id,
            prompt_version_id="orientation-v2-explicit-diary-audience",
            context_version_id=f"orientation:{self.season_id}:{actor.character_id}:v2",
        )
        if result.status is not NormalizedCallStatus.COMPLETED:
            return OrientationResult(
                character_id=actor.character_id,
                status="RETRYABLE_FAILURE",
                accepted=False,
                reason=result.status.value,
            )
        try:
            envelope = parse_orientation_output(result.text)
        except StructuredOutputError:
            return OrientationResult(
                character_id=actor.character_id,
                status="PRIVATE_REVIEW",
                accepted=False,
                reason="invalid orientation response",
            )

        if envelope.accepted and not envelope.wellness_signal:
            if self.events is not None:
                self.events.append(
                    event_id=f"{self.season_id}:orientation:{actor.character_id}:accepted",
                    natural_key=f"{self.season_id}:orientation:{actor.character_id}:accepted",
                    aggregate_type="cast_member",
                    aggregate_id=f"{self.season_id}:{actor.character_id}",
                    event_type="OrientationAccepted",
                    payload={
                        "character_id": actor.character_id,
                        "call_id": call_id,
                        "diary_audience_version": DIARY_AUDIENCE_VERSION,
                    },
                )
            return OrientationResult(
                character_id=actor.character_id,
                status="ACCEPTED",
                accepted=True,
            )

        signal = envelope.wellness_signal or "The actor declined orientation."
        if self.wellness is None:
            return OrientationResult(
                character_id=actor.character_id,
                status="WELLNESS_SIGNAL",
                accepted=False,
                reason=signal,
            )
        wellness = self.wellness.record_signal(
            character_id=actor.character_id,
            context="orientation",
            raw_signal=signal,
            intervention="orientation ended and alternate casting may begin",
        )
        return OrientationResult(
            character_id=actor.character_id,
            status="TAPPED_OUT" if wellness.tapped_out else "WELLNESS_SIGNAL",
            accepted=False,
            signal_number=wellness.signal_number,
            tapped_out=wellness.tapped_out,
            reason=signal,
        )


__all__ = ["OrientationActor", "OrientationResult", "OrientationService"]
