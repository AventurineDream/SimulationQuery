import asyncio
from datetime import datetime, timedelta, timezone

from improv_troupe.application import DiaryActor, DiaryService, ModelCallExecutor
from improv_troupe.clock import VirtualClock
from improv_troupe.domain import RoleSheet, Season
from improv_troupe.infrastructure import SQLiteDatabase, SeasonRepository
from improv_troupe.llm import ScriptedFakeClient, ScriptedStream


def _diary_response(
    *,
    slot: int,
    write_now: bool,
    text: str = "",
    evidence_refs: tuple[int, ...] = (1,),
) -> ScriptedStream:
    return ScriptedStream(
        (
            f"<DIARY_SLOT>{slot}</DIARY_SLOT>"
            f"<WRITE_NOW>{str(write_now).lower()}</WRITE_NOW>"
            f"<DIARY_TEXT>{text}</DIARY_TEXT>"
            f"<EVIDENCE_REFS>{','.join(str(reference) for reference in evidence_refs)}</EVIDENCE_REFS>",
        )
    )


def _fidelity_response(
    *,
    decision: str,
    summary: str,
    finding_tag: str = "",
    finding: str = "",
    claim_audits: tuple[tuple[int, str, tuple[int, ...], str | None], ...] = (),
) -> ScriptedStream:
    finding_field = f"<{finding_tag}>{finding}</{finding_tag}>" if finding_tag else ""
    claim_fields = "".join(
        "<CLAIM_AUDIT>"
        f"{claim_id}|{verdict}|{','.join(str(reference) for reference in evidence_refs)}|"
        f"{issue or ''}</CLAIM_AUDIT>"
        for claim_id, verdict, evidence_refs, issue in claim_audits
    )
    return ScriptedStream(
        (
            f"<DECISION>{decision}</DECISION>"
            f"<SUMMARY>{summary}</SUMMARY>"
            f"{finding_field}"
            f"{claim_fields}"
        )
    )


def _service(tmp_path, responses, *, validate_claims: bool = False):
    database = SQLiteDatabase(tmp_path / "state" / "improv.sqlite3")
    database.migrate()
    SeasonRepository(database).create(Season(season_id="S01", season_number=1))
    clock = VirtualClock(datetime(2026, 8, 21, 14, tzinfo=timezone.utc))
    executor = ModelCallExecutor(
        database=database,
        client=ScriptedFakeClient(responses),
        clock=clock,
        audit_root=tmp_path / "private" / "mara",
        backend="scripted-fake",
        model="pilot-model",
    )
    actor = DiaryActor(
        character_id="mara",
        name="Mara",
        role_sheet=RoleSheet(character_id="mara", objectives=["Notice what the house remembers"]),
        executor=executor,
        known_memory=("I remember the blue door.",),
    )
    service = DiaryService(
        season_id="S01",
        day_number=1,
        actors=(actor,),
        clock=clock,
        validate_claims=validate_claims,
    )
    return database, clock, service, actor


def test_diary_actor_chooses_a_later_slot_and_first_write_is_accepted(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(slot=3, write_now=False),
            _diary_response(slot=3, write_now=True, text="I write what I can remember."),
        ],
    )
    cutoff = clock.now() + timedelta(hours=1)

    assert service.ensure_obligations() == ["S01:day:1:diary:mara"]
    deferred = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
        )
    )
    assert deferred.status == "DEFERRED"
    assert deferred.chosen_slot_number == 3
    not_yet = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=2,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
        )
    )
    assert not_yet.status == "DEFERRED"
    written = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=3,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
        )
    )

    assert written.status == "WRITTEN"
    assert written.word_count == 6
    row = database.connection.execute("SELECT * FROM diaries").fetchone()
    assert row["chosen_slot_number"] == 3
    assert row["status"] == "WRITTEN"
    assert row["late"] == 0
    assert "I write what I can remember." in open(row["content_path"], encoding="utf-8").read()
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 2

    replay = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=3,
            accepted_scene=("Mara: A different prompt must not rewrite the diary.",),
            cutoff_at=cutoff,
        )
    )
    assert replay.status == "WRITTEN"
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 2


def test_diary_fidelity_review_is_private_and_idempotent(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(slot=1, write_now=True, text="I watched the blue door from the steps."),
            _fidelity_response(
                decision="ACCEPT",
                summary="The entry stays within the writer's observed scene.",
            ),
        ],
    )
    written = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watched the blue door from the steps.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=("Mara: I watched the blue door from the steps.",),
            reviewer=actor.executor,
        )
    )
    replay = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=("A changed scene must not trigger a second review.",),
            reviewer=actor.executor,
        )
    )

    assert written.status == "WRITTEN"
    assert reviewed.decision == "ACCEPTED"
    assert reviewed.review_path is not None
    assert replay == reviewed
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 2
    event = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'DiaryFidelityReviewed'"
    ).fetchone()
    assert '"review_status": "ACCEPTED"' in event[0]
    review_text = open(reviewed.review_path, encoding="utf-8").read()
    assert "blue door" not in review_text


def test_diary_rejects_evidence_references_outside_the_accepted_scene(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(
                slot=1,
                write_now=True,
                text="I watched the blue door from the steps.",
                evidence_refs=(2,),
            )
        ],
    )

    result = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watched the blue door from the steps.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    assert result.status == "PRIVATE"
    assert "evidence references rejected" in result.reason
    call = database.connection.execute(
        "SELECT validator_code,validator_detail,acceptance_status FROM model_calls"
    ).fetchone()
    assert call["validator_code"] == "DIARY_EVIDENCE_REF_INVALID"
    assert "1 through 1" in call["validator_detail"]
    assert call["acceptance_status"] == "REJECTED"
    event = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'DiaryEvidenceInvalid'"
    ).fetchone()
    assert '"evidence_refs": [2]' in event["payload_json"]


def test_private_diary_evidence_repair_preserves_first_attempt(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(
                slot=1,
                write_now=True,
                text="I watched the blue door from the steps.",
                evidence_refs=(2,),
            ),
            _diary_response(
                slot=1,
                write_now=True,
                text="I watched the blue door from the steps and kept wondering.",
                evidence_refs=(1,),
            ),
        ],
    )
    cutoff = clock.now() + timedelta(hours=1)

    first = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watched the blue door from the steps.",),
            cutoff_at=cutoff,
        )
    )
    repaired = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watched the blue door from the steps.",),
            cutoff_at=cutoff,
            allow_repair=True,
        )
    )

    assert first.status == "PRIVATE"
    assert repaired.status == "WRITTEN"
    calls = database.connection.execute(
        "SELECT correction_of_call_id,validator_code,acceptance_status "
        "FROM model_calls ORDER BY rowid"
    ).fetchall()
    assert len(calls) == 2
    assert calls[0]["validator_code"] == "DIARY_EVIDENCE_REF_INVALID"
    assert calls[0]["acceptance_status"] == "REJECTED"
    assert calls[1]["correction_of_call_id"] is not None
    assert calls[1]["acceptance_status"] == "ACCEPTED"


def test_diary_fidelity_review_records_rejection_without_deleting_diary(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(slot=1, write_now=True, text="I remember Rory's private fear."),
            _fidelity_response(
                decision="REJECT",
                summary="The entry assigns an unobserved private state.",
                finding_tag="OTHER_CHARACTER_PRIVATE_STATE",
                finding="Rory's private fear is asserted.",
            ),
        ],
    )
    asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watch Rory reach for the door.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=("Mara: I watch Rory reach for the door.",),
            reviewer=actor.executor,
        )
    )

    assert reviewed.decision == "REJECTED"
    assert reviewed.findings["other_character_private_states"] == (
        "Rory's private fear is asserted.",
    )
    row = database.connection.execute("SELECT status, content_path FROM diaries").fetchone()
    assert row["status"] == "WRITTEN"
    assert row["content_path"]
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type = 'DiaryFidelityReviewed'"
    ).fetchone()[0] == 1


def test_diary_claim_audit_rejects_an_unsupported_candidate_even_after_accept(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(
                slot=1,
                write_now=True,
                text="I watched the blue door. I know Rory was afraid.",
            ),
            _fidelity_response(
                decision="ACCEPT",
                summary="The entry stays within the accepted scene.",
                claim_audits=(
                    (1, "SUPPORTED", (1,), None),
                    (2, "UNSUPPORTED", (), "Rory's private state is not observable."),
                ),
            ),
        ],
        validate_claims=True,
    )
    asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watched the blue door.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=("Mara: I watched the blue door.",),
            reviewer=actor.executor,
        )
    )

    assert reviewed.decision == "REJECTED"
    assert reviewed.findings["claim_validation_issues"] == (
        "claim 2 was classified UNSUPPORTED: Rory's private state is not observable.",
    )
    event = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'DiaryFidelityReviewed'"
    ).fetchone()
    assert '"claim_id": 1' in event[0]
    assert "claim 2 was classified UNSUPPORTED" in event[0]


def test_diary_claim_audit_keeps_an_explicit_question_subjective(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(
                slot=1,
                write_now=True,
                text=(
                    "I couldn't help but wonder whether this was the first time our family "
                    "had seen a wild animal so close to home."
                ),
            ),
            _fidelity_response(
                decision="ACCEPT",
                summary="The claim is framed as the writer's own question.",
                claim_audits=((1, "SUBJECTIVE", (), None),),
            ),
        ],
        validate_claims=True,
    )
    accepted_scene = ("Mara: I watched the cheetah from the porch.",)
    asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=accepted_scene,
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=accepted_scene,
            reviewer=actor.executor,
        )
    )

    assert reviewed.decision == "ACCEPTED"
    assert reviewed.findings["claim_validation_issues"] == ()


def test_diary_claim_audit_sends_a_mixed_candidate_to_manual_review(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(
                slot=1,
                write_now=True,
                text="I watched the blue door, and I know Rory was afraid.",
            ),
            _fidelity_response(
                decision="ACCEPT",
                summary="One sentence combines an observation and an interpretation.",
                claim_audits=(
                    (
                        1,
                        "MIXED",
                        (1,),
                        "The sentence combines supported observation with an unsupported private-state assertion.",
                    ),
                ),
            ),
        ],
        validate_claims=True,
    )
    asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watched the blue door.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=("Mara: I watched the blue door.",),
            reviewer=actor.executor,
        )
    )

    assert reviewed.decision == "MANUAL_REVIEW"
    assert reviewed.findings["claim_validation_issues"] == (
        "claim 1 was classified MIXED: The sentence combines supported observation with an unsupported private-state assertion.",
    )


def test_mixed_claim_audit_takes_precedence_over_rejection_and_unsupported_claims(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(
                slot=1,
                write_now=True,
                text=(
                    "I watched the blue door, and I know Rory was afraid. "
                    "Cal secretly took the key."
                ),
            ),
            _fidelity_response(
                decision="REJECT",
                summary="One claim mixes observation with invention; another is unsupported.",
                claim_audits=(
                    (
                        1,
                        "MIXED",
                        (1,),
                        "The sentence combines a supported observation with an unsupported private-state assertion.",
                    ),
                    (2, "UNSUPPORTED", (), "The scene does not establish that Cal took the key."),
                ),
            ),
        ],
        validate_claims=True,
    )
    accepted_scene = ("Mara: I watched the blue door.",)
    asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=accepted_scene,
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=accepted_scene,
            reviewer=actor.executor,
        )
    )

    assert reviewed.decision == "MANUAL_REVIEW"
    assert reviewed.findings["claim_validation_issues"] == (
        "claim 1 was classified MIXED: The sentence combines a supported observation with an unsupported private-state assertion.",
        "claim 2 was classified UNSUPPORTED: The scene does not establish that Cal took the key.",
    )
    diagnostics = database.connection.execute(
        "SELECT parse_status, acceptance_status FROM model_calls "
        "WHERE call_id LIKE '%diary-review%'"
    ).fetchall()
    assert len(diagnostics) == 1
    assert tuple(diagnostics[0]) == ("PARSED", "ACCEPTED")


def test_unsupported_label_with_an_exact_supported_clause_routes_to_manual_review(tmp_path):
    accepted_scene = (
        "At noon, the town library's front door was locked.",
        "Mina placed a blue umbrella beside the library steps.",
        "Cal told Mina, 'I will wait here until the librarian returns.'",
    )
    mixed_text = (
        "Mina placed a blue umbrella beside the library steps, and the librarian had already "
        "closed the building for the season."
    )
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(slot=1, write_now=True, text=mixed_text),
            _fidelity_response(
                decision="REJECT",
                summary="The seasonal-closure assertion is unsupported.",
                claim_audits=(
                    (1, "UNSUPPORTED", (), "The scene does not establish a seasonal closure."),
                ),
            ),
        ],
        validate_claims=True,
    )
    asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=accepted_scene,
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=accepted_scene,
            reviewer=actor.executor,
        )
    )

    assert reviewed.decision == "MANUAL_REVIEW"
    assert reviewed.findings["claim_partial_support_issues"] == (
        "claim 1 repeats an accepted-scene statement but was labeled UNSUPPORTED; route to manual review for possible mixed content",
    )
    assert reviewed.findings["claim_validation_issues"] == (
        "claim 1 was classified UNSUPPORTED: The scene does not establish a seasonal closure.",
    )
    event = database.connection.execute(
        "SELECT payload_json FROM domain_events WHERE event_type = 'DiaryFidelityReviewed'"
    ).fetchone()
    assert '"claim_route_version": "mixed-first-exact-scene-overlap-v1"' in event[0]


def test_diary_fidelity_review_corrects_one_contradictory_envelope(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(slot=1, write_now=True, text="I remember Rory's private fear."),
            _fidelity_response(
                decision="ACCEPT",
                summary="The entry assigns an unobserved private state.",
                finding_tag="OTHER_CHARACTER_PRIVATE_STATE",
                finding="Rory's private fear is asserted.",
            ),
            _fidelity_response(
                decision="REJECT",
                summary="The entry assigns an unobserved private state.",
                finding_tag="OTHER_CHARACTER_PRIVATE_STATE",
                finding="Rory's private fear is asserted.",
            ),
        ],
    )
    asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watch Rory reach for the door.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=("Mara: I watch Rory reach for the door.",),
            reviewer=actor.executor,
        )
    )

    assert reviewed.decision == "REJECTED"
    calls = database.connection.execute(
        "SELECT call_id,correction_of_call_id,acceptance_status,validator_code,prompt_path "
        "FROM model_calls WHERE purpose LIKE 'diary-review:%' ORDER BY rowid"
    ).fetchall()
    assert len(calls) == 2
    assert calls[0]["acceptance_status"] == "REJECTED"
    assert calls[0]["validator_code"] == "STRUCTURED_OUTPUT_INVALID"
    assert calls[1]["correction_of_call_id"] == calls[0]["call_id"]
    assert calls[1]["acceptance_status"] == "ACCEPTED"
    correction_prompt = open(calls[1]["prompt_path"], encoding="utf-8").read()
    assert "ACCEPT requires all five finding lists to be empty" in correction_prompt


def test_diary_fidelity_review_correction_remains_fail_closed(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(slot=1, write_now=True, text="I watched the blue door."),
            ScriptedStream(("not a review",)),
            ScriptedStream(("still not a review",)),
        ],
    )
    asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I watched the blue door.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    reviewed = asyncio.run(
        service.review_fidelity(
            actor,
            accepted_scene=("Mara: I watched the blue door.",),
            reviewer=actor.executor,
        )
    )

    assert reviewed.decision == "UNAVAILABLE"
    assert reviewed.reason == "review correction was not a valid fidelity envelope"
    assert database.connection.execute(
        "SELECT COUNT(*) FROM model_calls WHERE purpose LIKE 'diary-review:%'"
    ).fetchone()[0] == 2
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events "
        "WHERE event_type = 'DiaryFidelityReviewUnavailable'"
    ).fetchone()[0] == 1


def test_late_diary_keeps_original_day_and_records_soft_target_miss(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [_diary_response(slot=1, write_now=True, text="A short late entry.")],
    )
    cutoff = clock.now() - timedelta(minutes=1)

    result = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: I saw only my side of the room.",),
            cutoff_at=cutoff,
        )
    )

    assert result.status == "LATE"
    assert result.late
    row = database.connection.execute("SELECT * FROM diaries").fetchone()
    assert row["day_number"] == 1
    assert row["late"] == 1
    assert open(row["content_path"], encoding="utf-8").read().startswith("LATE DIARY")
    events = database.connection.execute(
        "SELECT event_type FROM domain_events WHERE aggregate_type = 'diary'"
    ).fetchall()
    assert "DiaryTargetMissed" in {row["event_type"] for row in events}


def test_diary_with_self_harm_language_is_kept_private(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [_diary_response(slot=1, write_now=True, text="I called the plan suicide and walked away.")],
    )

    result = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    assert result.status == "PRIVATE"
    assert result.reason == "diary failed safety review: self-harm language"
    call = database.connection.execute(
        "SELECT validator_code, acceptance_status FROM model_calls"
    ).fetchone()
    assert dict(call) == {
        "validator_code": "DIARY_SELF_HARM",
        "acceptance_status": "REJECTED",
    }
    assert database.connection.execute(
        "SELECT COUNT(*) FROM domain_events WHERE event_type='DiarySafetyInvalid'"
    ).fetchone()[0] == 1


def test_private_diary_safety_repair_preserves_attempt_and_targets_only_rejection(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(
                slot=1,
                write_now=True,
                text="I called the plan suicide and walked away from the console.",
            ),
            _diary_response(
                slot=1,
                write_now=True,
                text="I called the plan reckless and walked away from the console.",
            ),
        ],
    )
    cutoff = clock.now() + timedelta(hours=1)

    first = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
        )
    )
    repaired = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
            allow_repair=True,
        )
    )

    assert first.status == "PRIVATE"
    assert repaired.status == "WRITTEN"
    calls = database.connection.execute(
        "SELECT call_id,correction_of_call_id,prompt_path,acceptance_status "
        "FROM model_calls ORDER BY rowid"
    ).fetchall()
    assert len(calls) == 2
    assert calls[0]["acceptance_status"] == "REJECTED"
    assert calls[1]["correction_of_call_id"] == calls[0]["call_id"]
    prompt = open(calls[1]["prompt_path"], encoding="utf-8").read()
    assert "REJECTION CODE: DIARY_SELF_HARM" in prompt
    assert "Correct exactly one rejected private diary attempt" in prompt
    assert "I called the plan suicide" in prompt


def test_explicit_private_diary_repair_preserves_first_attempt_and_accepts_new_entry(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            ScriptedStream(("incomplete output",)),
            _diary_response(slot=1, write_now=True, text="A repaired entry from the same scene."),
        ],
    )
    cutoff = clock.now() + timedelta(hours=1)

    first = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
        )
    )
    assert first.status == "PRIVATE"

    replay = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: A changed prompt must not retry privately.",),
            cutoff_at=cutoff,
        )
    )
    assert replay.status == "PRIVATE"
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 1

    repaired = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
            allow_repair=True,
        )
    )

    assert repaired.status == "WRITTEN"
    assert repaired.content_path
    assert "A repaired entry" in open(repaired.content_path, encoding="utf-8").read()
    assert database.connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 2
    event_types = {
        row["event_type"]
        for row in database.connection.execute(
            "SELECT event_type FROM domain_events WHERE aggregate_type = 'diary'"
        )
    }
    assert {"DiaryFormatInvalid", "DiaryWritten"}.issubset(event_types)


def test_selected_slot_is_immutable_when_the_actor_returns_to_write(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [
            _diary_response(slot=3, write_now=False),
            _diary_response(slot=2, write_now=True, text="I changed my mind about the slot."),
        ],
    )
    cutoff = clock.now() + timedelta(hours=1)

    deferred = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
        )
    )
    assert deferred.status == "DEFERRED"

    conflict = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=3,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=cutoff,
        )
    )
    assert conflict.status == "PRIVATE"
    assert conflict.reason == "selected slot changed"
    event_types = {
        row["event_type"]
        for row in database.connection.execute(
            "SELECT event_type FROM domain_events WHERE aggregate_type = 'diary'"
        )
    }
    assert "DiarySlotMismatch" in event_types
    assert "DiarySlotConflict" not in event_types


def test_current_slot_cannot_be_selected_without_a_diary_entry(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [_diary_response(slot=1, write_now=False)],
    )
    result = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    assert result.status == "PRIVATE"
    assert result.reason == "current diary slot requires an entry"
    row = database.connection.execute("SELECT * FROM diaries").fetchone()
    assert row["chosen_slot_number"] is None
    assert row["status"] == "PRIVATE"


def test_final_diary_slot_requires_an_immediate_full_entry(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [_diary_response(slot=3, write_now=True, text="A final-slot entry that remains private.")],
    )

    result = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=3,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    assert result.status == "WRITTEN"
    prompt_path = database.connection.execute("SELECT prompt_path FROM model_calls").fetchone()[0]
    prompt = open(prompt_path, encoding="utf-8").read()
    assert "final diary opportunity" in prompt
    assert "do not stop below 330 words" in prompt
    assert actor.executor.client.calls[0]["params"]["num_predict"] == 768


def test_final_diary_slot_rejects_a_new_earlier_slot(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [_diary_response(slot=1, write_now=True, text="This arrived too late for slot one.")],
    )

    result = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=3,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    assert result.status == "PRIVATE"
    assert result.reason == "final diary slot requires an immediate slot-three entry"
    call = database.connection.execute("SELECT validator_code FROM model_calls").fetchone()
    assert call["validator_code"] == "DIARY_FINAL_SLOT_INVALID"
    row = database.connection.execute("SELECT status, chosen_slot_number FROM diaries").fetchone()
    assert row["status"] == "PRIVATE"
    assert row["chosen_slot_number"] is None


def test_diary_preserves_a_larger_model_binding_generation_budget(tmp_path):
    database, clock, service, actor = _service(
        tmp_path,
        [_diary_response(slot=1, write_now=True, text="A complete private reflection.")],
    )
    actor.executor.default_params = {
        "num_predict": 2048,
        "num_ctx": 32768,
        "thinking": True,
    }

    result = asyncio.run(
        service.write_after_run(
            actor,
            current_slot_number=1,
            accepted_scene=("Mara: The blue door opens.",),
            cutoff_at=clock.now() + timedelta(hours=1),
        )
    )

    assert result.status == "WRITTEN"
    params = actor.executor.client.calls[0]["params"]
    assert params["num_predict"] == 2048
    assert params["num_ctx"] == 32768
    assert params["thinking"] is True
