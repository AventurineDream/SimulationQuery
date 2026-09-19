"""MAGIC attributes and deterministic dice adjudication."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MagicAttribute(str, Enum):
    MIGHT = "Might"
    AUTHORITY = "Authority"
    GUSTO = "Gusto"
    INTELLECT = "Intellect"
    COOL = "Cool"


class MagicOutcome(str, Enum):
    CLEAN_SUCCESS = "clean_success"
    COSTLY_SUCCESS = "costly_success"
    SETBACK = "setback"


class MagicGoalStatus(str, Enum):
    ACHIEVED = "achieved"
    NOT_ACHIEVED = "not_achieved"


class MagicCostType(str, Enum):
    TIME = "time"
    POSITION = "position"
    TRUST = "trust"
    ACCESS = "access"
    RESOURCES = "resources"


class MagicScores(BaseModel):
    """Provisional 1–5 ratings, with 3 as the unmodified baseline."""

    model_config = ConfigDict(extra="forbid")

    might: int = Field(default=3, ge=1, le=5)
    authority: int = Field(default=3, ge=1, le=5)
    gusto: int = Field(default=3, ge=1, le=5)
    intellect: int = Field(default=3, ge=1, le=5)
    cool: int = Field(default=3, ge=1, le=5)

    def score_for(self, attribute: MagicAttribute) -> int:
        return int(getattr(self, attribute.value.casefold()))


class MagicRollResult(BaseModel):
    """One app-resolved 2d6 check, with enough data to audit its math."""

    model_config = ConfigDict(extra="forbid")

    attribute: MagicAttribute
    attribute_score: int = Field(ge=1, le=5)
    die_faces: tuple[Annotated[int, Field(ge=1, le=6)], Annotated[int, Field(ge=1, le=6)]]
    situational_modifier: int = Field(ge=-2, le=2)
    total: int
    outcome: MagicOutcome

    @model_validator(mode="after")
    def result_matches_the_recorded_roll(self) -> "MagicRollResult":
        expected_total = (
            sum(self.die_faces)
            + (self.attribute_score - 3)
            + self.situational_modifier
        )
        if self.total != expected_total:
            raise ValueError("MAGIC total does not match its faces and modifiers")
        expected_outcome = (
            MagicOutcome.CLEAN_SUCCESS
            if self.total >= 10
            else MagicOutcome.COSTLY_SUCCESS
            if self.total >= 7
            else MagicOutcome.SETBACK
        )
        if self.outcome is not expected_outcome:
            raise ValueError("MAGIC outcome does not match its threshold")
        return self


class MagicAdjudication(BaseModel):
    """The runtime-owned meaning of a recorded MAGIC roll.

    This model deliberately contains no director-authored prose.  The result
    tier, goal status, and goal answer are derived from the roll and the
    precommitted success criterion before a director consequence is requested.
    """

    model_config = ConfigDict(extra="forbid")

    outcome: MagicOutcome
    goal_status: MagicGoalStatus
    success_criteria: str = Field(min_length=1, max_length=180)
    goal_answer: str = Field(min_length=1, max_length=240)

    @classmethod
    def from_outcome(
        cls, *, outcome: MagicOutcome, success_criteria: str
    ) -> "MagicAdjudication":
        resolved_outcome = MagicOutcome(outcome)
        criteria = success_criteria.strip()
        if not criteria:
            raise ValueError("MAGIC adjudication requires precommitted success criteria")
        if resolved_outcome is MagicOutcome.SETBACK:
            status = MagicGoalStatus.NOT_ACHIEVED
            answer = f"Success criterion remains unestablished: {criteria}"
        else:
            status = MagicGoalStatus.ACHIEVED
            answer = criteria
        return cls(
            outcome=resolved_outcome,
            goal_status=status,
            success_criteria=criteria,
            goal_answer=answer,
        )


def adjudicate_magic_roll(
    result: MagicRollResult, *, success_criteria: str
) -> MagicAdjudication:
    """Derive the goal result from an already-validated roll, never from prose."""

    return MagicAdjudication.from_outcome(
        outcome=result.outcome,
        success_criteria=success_criteria,
    )


def resolve_magic_roll(
    *,
    attribute: MagicAttribute,
    attribute_score: int,
    die_faces: tuple[int, int],
    situational_modifier: int = 0,
) -> MagicRollResult:
    """Apply the shared MAGIC formula to already-generated die faces."""

    if not 1 <= attribute_score <= 5:
        raise ValueError("MAGIC scores must be between 1 and 5")
    if len(die_faces) != 2 or any(not 1 <= face <= 6 for face in die_faces):
        raise ValueError("a MAGIC roll requires exactly two six-sided die faces")
    if not -2 <= situational_modifier <= 2:
        raise ValueError("MAGIC situational modifier must be between -2 and 2")

    total = sum(die_faces) + (attribute_score - 3) + situational_modifier
    outcome = (
        MagicOutcome.CLEAN_SUCCESS
        if total >= 10
        else MagicOutcome.COSTLY_SUCCESS
        if total >= 7
        else MagicOutcome.SETBACK
    )
    return MagicRollResult(
        attribute=attribute,
        attribute_score=attribute_score,
        die_faces=die_faces,
        situational_modifier=situational_modifier,
        total=total,
        outcome=outcome,
    )


def magic_roll_payload(
    *,
    run_id: str,
    round_number: int,
    turn_id: str,
    character_id: str,
    character_name: str,
    challenge: str,
    action: str,
    result: MagicRollResult,
    recorded_at: str,
) -> dict[str, object]:
    """Create a self-contained immutable roll-ledger event payload."""

    payload: dict[str, object] = {
        "run_id": run_id,
        "round_number": round_number,
        "turn_id": turn_id,
        "character_id": character_id,
        "character_name": character_name,
        "challenge": challenge,
        "action": action,
        "attribute": result.attribute.value,
        "attribute_score": result.attribute_score,
        "die_faces": list(result.die_faces),
        "stat_modifier": result.attribute_score - 3,
        "situational_modifier": result.situational_modifier,
        "total": result.total,
        "outcome": result.outcome.value,
        "formula": "2d6 + (MAGIC score - 3) + situational modifier",
        "thresholds": {"clean_success": 10, "costly_success": 7},
        "recorded_at": recorded_at,
    }
    return payload


__all__ = [
    "MagicAttribute",
    "MagicAdjudication",
    "MagicCostType",
    "MagicGoalStatus",
    "MagicOutcome",
    "MagicRollResult",
    "MagicScores",
    "adjudicate_magic_roll",
    "magic_roll_payload",
    "resolve_magic_roll",
]
