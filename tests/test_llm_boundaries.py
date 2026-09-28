import asyncio

import pytest

from improv_troupe.clock import VirtualClock
from improv_troupe.domain import HiddenSeasonPlan, RoleSheet
from improv_troupe.llm import (
    ActorContext,
    ActorTurnEnvelope,
    AuditArtifactConflict,
    AuditWriter,
    ContextBoundaryError,
    DiaryFidelityEnvelope,
    NormalizedCallStatus,
    OrchestratorEnvelope,
    ScriptedFakeClient,
    ScriptedStream,
    StructuredOutputError,
    build_orientation_messages,
    stream_with_schema,
    supports_native_structured,
    build_actor_messages,
    build_diary_fidelity_messages,
    build_diary_messages,
    build_director_plan_messages,
    build_orchestrator_messages,
    collect_chat,
    parse_actor_output,
    parse_diary_fidelity_output,
    parse_diary_output,
    parse_orientation_output,
    parse_orchestrator_output,
    redact_text,
    review_orchestrator_narration,
    review_actor_text,
    schema_for,
)
from improv_troupe.domain import OpeningSnapshot
from improv_troupe.llm.client import OllamaClient, _ollama_api_url, _ollama_options, _ollama_think, make_client


class InterruptingClient:
    async def list_models(self):
        return ["test"]

    async def stream_chat(self, model, messages, **params):
        yield "partial "
        raise RuntimeError("backend disconnected")


class CancellingClient:
    async def list_models(self):
        return ["test"]

    async def stream_chat(self, model, messages, **params):
        yield "partial "
        raise asyncio.CancelledError()


class NativeStructuredClient:
    async def list_models(self):
        return ["test"]

    async def stream_chat(self, model, messages, **params):
        raise AssertionError("tagged fallback should not be called")

    async def stream_structured_chat(self, model, messages, *, schema_name, **params):
        self.model = model
        self.messages = messages
        self.schema_name = schema_name
        self.params = params
        yield '{"kind":"actor_turn","text":"Check the hatch."}'


class EmptyNativeStructuredClient:
    async def list_models(self):
        return ["test"]

    async def stream_structured_chat(self, model, messages, *, schema_name, **params):
        if False:
            yield ""

    async def stream_chat(self, model, messages, **params):
        self.fallback_params = params
        yield "<ACTOR_TEXT>Check the hatch.</ACTOR_TEXT><DIARY_INTENT>false</DIARY_INTENT>"


class WhitespaceNativeStructuredClient(EmptyNativeStructuredClient):
    async def stream_structured_chat(self, model, messages, *, schema_name, **params):
        yield " \n\t"


def _clock():
    from datetime import datetime, timezone

    return VirtualClock(datetime(2026, 8, 20, 12, tzinfo=timezone.utc))


def test_normalized_call_preserves_partial_output_and_error_type():
    result = asyncio.run(
        collect_chat(
            InterruptingClient(),
            call_id="call-1",
            purpose="actor_turn",
            backend="fake",
            model="test",
            messages=[],
            clock=_clock(),
        )
    )
    assert result.status is NormalizedCallStatus.FAILED
    assert result.text == "partial "
    assert result.error_type == "RuntimeError"
    assert result.latency_ms == 0


def test_orientation_parser_treats_literal_none_signal_as_empty():
    parsed = parse_orientation_output(
        "<ACCEPTED>true</ACCEPTED><WELLNESS_SIGNAL>None</WELLNESS_SIGNAL>"
    )
    assert parsed.accepted
    assert parsed.wellness_signal is None


def test_orientation_allows_uncertainty_without_forcing_metaphysical_agreement():
    messages = build_orientation_messages(actor_name="Luna Planck")
    text = "\n".join(message["content"] for message in messages)
    assert "does not require agreement" in text


def test_manual_review_orientation_does_not_offer_automatic_tap_out():
    messages = build_orientation_messages(actor_name="Luna Planck", auto_tap_out=False)
    text = "\n".join(message["content"] for message in messages)
    assert "no automatic tap-out is offered" in text
    assert "Three signals tap you out" not in text


def test_scripted_fake_supports_partial_failures_without_network_access():
    result = asyncio.run(
        collect_chat(
            ScriptedFakeClient(
                [ScriptedStream(("partial ",), error=TimeoutError())]
            ),
            call_id="call-scripted",
            purpose="actor_turn",
            backend="fake",
            model="test",
            messages=[],
            clock=_clock(),
        )
    )
    assert result.status is NormalizedCallStatus.FAILED
    assert result.error_type == "TimeoutError"
    assert result.text == "partial "


def test_schema_stream_uses_tagged_fallback_when_client_has_no_native_capability():
    client = ScriptedFakeClient(["<ACTOR_TEXT>hello</ACTOR_TEXT>"])
    assert not supports_native_structured(client)
    async def collect():
        return "".join(
            [
                chunk
                async for chunk in stream_with_schema(
                    client,
                    model="test",
                    messages=[{"role": "user", "content": "scene"}],
                    schema_name="actor_turn",
                    tagged_format_instructions="<ACTOR_TEXT>...</ACTOR_TEXT>",
                )
            ]
        )

    assert asyncio.run(collect()) == "<ACTOR_TEXT>hello</ACTOR_TEXT>"
    assert "strict format" in client.calls[0]["messages"][-1]["content"]


def test_schema_stream_uses_provider_native_capability_without_tag_instruction():
    client = NativeStructuredClient()

    async def collect():
        return "".join(
            [
                chunk
                async for chunk in stream_with_schema(
                    client,
                    model="test",
                    messages=[{"role": "user", "content": "scene"}],
                    schema_name="actor_turn",
                    tagged_format_instructions="<ACTOR_TEXT>...</ACTOR_TEXT>",
                    temperature=0.7,
                )
            ]
        )

    assert asyncio.run(collect()) == '{"kind":"actor_turn","text":"Check the hatch."}'
    assert supports_native_structured(client)
    assert client.schema_name == "actor_turn"
    assert client.params == {"temperature": 0.7}


def test_empty_native_response_retries_once_with_a_truthful_tagged_fallback():
    client = EmptyNativeStructuredClient()

    async def collect():
        return "".join(
            [
                chunk
                async for chunk in stream_with_schema(
                    client,
                    model="test",
                    messages=[{"role": "user", "content": "scene"}],
                    schema_name="actor_turn",
                    tagged_format_instructions="<ACTOR_TEXT>...</ACTOR_TEXT>",
                )
            ]
        )

    assert "ACTOR_TEXT" in asyncio.run(collect())
    assert client.last_response_format_mode == "TAGGED_FALLBACK"
    assert client.fallback_params["reasoning_effort"] == "none"


def test_whitespace_native_response_also_uses_the_tagged_fallback():
    client = WhitespaceNativeStructuredClient()

    async def collect():
        return "".join(
            [
                chunk
                async for chunk in stream_with_schema(
                    client,
                    model="test",
                    messages=[{"role": "user", "content": "scene"}],
                    schema_name="actor_turn",
                    tagged_format_instructions="<ACTOR_TEXT>...</ACTOR_TEXT>",
                )
            ]
        )

    assert asyncio.run(collect()).startswith("<ACTOR_TEXT>")
    assert client.last_response_format_mode == "TAGGED_FALLBACK"


def test_actor_schema_is_strict_and_matches_the_parser_contract():
    schema = schema_for("actor_turn")
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "kind",
        "text",
        "wellness_signal",
        "memory_notes",
        "diary_intent",
        "magic_stat",
        "magic_method",
    }
    assert parse_actor_output('{"kind":"actor_turn","text":"Lock the hatch."}').text == (
        "Lock the hatch."
    )
    assert schema["properties"]["text"]["maxLength"] == 750
    assert schema["properties"]["memory_notes"]["maxItems"] == 2


def test_private_setup_schemas_bound_collections_and_require_playable_role_fields():
    private_plan = schema_for("private_plan")
    role_sheet = schema_for("role_sheet")
    assert private_plan["properties"]["planned_tensions"]["maxItems"] == 4
    assert role_sheet["properties"]["objectives"]["maxItems"] == 2
    assert set(role_sheet["required"]) >= {
        "character_id",
        "objectives",
        "boundaries",
        "knowledge",
        "relationships",
        "secrets",
        "play_style",
        "voice_guidance",
    }


def test_ollama_client_uses_native_api_and_disables_explicitly_unwanted_thinking():
    client = make_client(kind="ollama", base_url="http://models.test:11434/v1")
    assert isinstance(client, OllamaClient)
    assert client.base_url == "http://models.test:11434/api"
    assert _ollama_api_url("http://models.test:11434/api") == "http://models.test:11434/api"
    assert _ollama_options({"max_tokens": 320, "reasoning_effort": "none"}) == {
        "num_predict": 320
    }
    assert _ollama_think({"reasoning_effort": "none"}) is False
    assert _ollama_think({"reasoning_effort": "low"}) is None
    assert _ollama_think({"reasoning_effort": "low"}, default=False) is False
    assert _ollama_think({"thinking": True, "reasoning_effort": "none"}, default=False) is True


def test_cancelled_call_is_interrupted_without_losing_partial_text():
    result = asyncio.run(
        collect_chat(
            CancellingClient(),
            call_id="call-2",
            purpose="diary",
            backend="fake",
            model="test",
            messages=[],
            clock=_clock(),
        )
    )
    assert result.status is NormalizedCallStatus.INTERRUPTED
    assert result.cancelled
    assert result.text == "partial "


def test_json_and_tagged_actor_outputs_normalize_to_the_same_envelope():
    native = parse_actor_output(
        '{"kind":"actor_turn","text":"I open the hatch.","wellness_signal":null,'
        '"memory_notes":["hatch opened"],"diary_intent":true}'
    )
    tagged = parse_actor_output(
        "<ACTOR_TEXT>I open the hatch.</ACTOR_TEXT>"
        "<MEMORY_NOTE>hatch opened</MEMORY_NOTE>"
        "<DIARY_INTENT>true</DIARY_INTENT>"
    )
    assert native == tagged
    assert isinstance(native, ActorTurnEnvelope)


def test_actor_parser_normalizes_inline_native_magic_and_memory_metadata():
    parsed = parse_actor_output(
        '{"kind":"actor_turn","text":"I watch the cheetah from the doorway. '
        '<MAGIC_STAT>Intellect</MAGIC_STAT> <MAGIC_METHOD>I compare its steps from the doorway.'
        '</MAGIC_METHOD> [Memory: cheetah paw]"}'
    )

    assert parsed.text == "I watch the cheetah from the doorway."
    assert parsed.magic_stat.value == "Intellect"
    assert parsed.magic_method == "I compare its steps from the doorway."
    assert parsed.memory_notes == ["cheetah paw"]


def test_actor_parser_ignores_false_placeholder_in_optional_wellness_field():
    parsed = parse_actor_output(
        '{"kind":"actor_turn","text":"I check the hatch.","wellness_signal":"false"}'
    )
    assert parsed.wellness_signal is None


def test_actor_parser_ignores_in_character_stress_misfiled_as_wellness():
    parsed = parse_actor_output(
        '{"kind":"actor_turn","text":"I steady the sensor.",'
        '"wellness_signal":"I need to slow down—this thing is breathing with me."}'
    )
    assert parsed.wellness_signal is None


@pytest.mark.parametrize(
    "text",
    (
        "<ACTOR_TEXT>I open the hatch.</ACTOR_TEXT>",
        "<Luna_Planck>I open the hatch.</Luna_Planck>",
    ),
)
def test_actor_parser_rejects_transport_or_role_markup_inside_native_text(text):
    with pytest.raises(StructuredOutputError):
        parse_actor_output('{"kind":"actor_turn","text":' + repr(text).replace("'", '"') + "}")


def test_actor_parser_repairs_missing_internal_closing_tags():
    parsed = parse_actor_output(
        "<ACTOR_TEXT>Check the core shielding."
        "<MEMORY_NOTE>the cooling system is unstable"
        "<DIARY_INTENT>true</DIARY_INTENT>"
    )

    assert parsed.text == "Check the core shielding."
    assert parsed.memory_notes == ["the cooling system is unstable"]
    assert parsed.diary_intent is True


def test_actor_parser_still_rejects_missing_final_close():
    with pytest.raises(StructuredOutputError):
        parse_actor_output(
            "<ACTOR_TEXT>Check the core shielding.</ACTOR_TEXT>"
            "<DIARY_INTENT>true"
        )


def test_diary_parser_repairs_internal_closing_tags_and_ignores_empty_signal():
    parsed = parse_diary_output(
        "<DIARY_SLOT>1</DIARY_SLOT>"
        "<WRITE_NOW>true</WRITE_NOW>"
        "<DIARY_TEXT>The hatch keeps humming."
        "<EVIDENCE_REFS>1</EVIDENCE_REFS>"
        "<WELLNESS_SIGNAL>None</WELLNESS_SIGNAL>"
    )

    assert parsed.chosen_slot_number == 1
    assert parsed.write_now is True
    assert parsed.text == "The hatch keeps humming."
    assert parsed.evidence_refs == [1]
    assert parsed.wellness_signal is None


def test_diary_json_normalizes_empty_signal_placeholder():
    parsed = parse_diary_output(
        '{"kind":"diary","chosen_slot_number":1,"write_now":true,'
        '"text":"The hatch keeps humming.","evidence_refs":[1],"wellness_signal":"null"}'
    )

    assert parsed.wellness_signal is None


def test_diary_parser_rejects_a_write_now_decision_without_text_or_wellness_signal():
    with pytest.raises(StructuredOutputError):
        parse_diary_output('{"kind":"diary","chosen_slot_number":1,"write_now":true}')


def test_diary_parser_allows_an_empty_entry_when_a_wellness_signal_is_present():
    parsed = parse_diary_output(
        '{"kind":"diary","chosen_slot_number":1,"write_now":true,'
        '"text":"","evidence_refs":[],"wellness_signal":"Please pause."}'
    )
    assert parsed.wellness_signal == "Please pause."


def test_diary_parser_rejects_a_nonexplicit_wellness_message_without_text():
    with pytest.raises(StructuredOutputError):
        parse_diary_output(
            '{"kind":"diary","chosen_slot_number":1,"write_now":true,'
            '"text":"","evidence_refs":[1],"wellness_signal":"I need to slow down in this storm."}'
        )


def test_diary_schema_requires_text_even_for_a_deferred_slot():
    schema = schema_for("diary")
    assert "text" in schema["required"]
    assert "evidence_refs" in schema["required"]
    with pytest.raises(StructuredOutputError):
        parse_diary_output(
            '{"kind":"diary","chosen_slot_number":2,"write_now":false,'
            '"evidence_refs":[]}'
        )


def test_diary_parser_requires_evidence_for_written_text():
    with pytest.raises(StructuredOutputError):
        parse_diary_output(
            '{"kind":"diary","chosen_slot_number":1,"write_now":true,'
            '"text":"The hatch keeps humming.","evidence_refs":[]}'
        )


def test_diary_parser_rejects_duplicate_or_non_integer_evidence_refs():
    with pytest.raises(StructuredOutputError):
        parse_diary_output(
            '{"kind":"diary","chosen_slot_number":1,"write_now":true,'
            '"text":"The hatch keeps humming.","evidence_refs":[1,1]}'
        )
    with pytest.raises(StructuredOutputError):
        parse_diary_output(
            '{"kind":"diary","chosen_slot_number":1,"write_now":true,'
            '"text":"The hatch keeps humming.","evidence_refs":["1"]}'
        )


def test_diary_fidelity_parser_requires_categorized_decisions():
    accepted = parse_diary_fidelity_output(
        '{"kind":"diary_fidelity_review","decision":"ACCEPT",'
        '"summary":"The entry stays within the accepted scene.",'
        '"invented_events":[],"other_character_private_states":[],'
        '"event_order_issues":[],"causal_contradictions":[]}'
    )
    assert isinstance(accepted, DiaryFidelityEnvelope)
    assert accepted.decision == "ACCEPT"

    rejected = parse_diary_fidelity_output(
        "<DECISION>REJECT</DECISION>"
        "<SUMMARY>The entry assigns an unobserved motive.</SUMMARY>"
        "<OTHER_CHARACTER_PRIVATE_STATE>Rory's private fear is asserted.</OTHER_CHARACTER_PRIVATE_STATE>"
        "<EVIDENCE_REFERENCE_ISSUE>The claim is not supported by cited scene evidence.</EVIDENCE_REFERENCE_ISSUE>"
        "<CLAIM_AUDIT>1|UNSUPPORTED||Rory's private fear is not observable.</CLAIM_AUDIT>"
    )
    assert rejected.other_character_private_states == ["Rory's private fear is asserted."]
    assert rejected.evidence_reference_issues == [
        "The claim is not supported by cited scene evidence."
    ]
    assert rejected.claim_audits[0].claim_id == 1
    assert rejected.claim_audits[0].verdict == "UNSUPPORTED"

    mixed = parse_diary_fidelity_output(
        "<DECISION>MANUAL_REVIEW</DECISION>"
        "<SUMMARY>The sentence combines an observation and an interpretation.</SUMMARY>"
        "<CLAIM_AUDIT>1|MIXED|1|The factual and interpretive clauses need separate review.</CLAIM_AUDIT>"
    )
    assert mixed.claim_audits[0].verdict == "MIXED"

    rejected_claim = parse_diary_fidelity_output(
        '{"kind":"diary_fidelity_review","decision":"REJECT",'
        '"summary":"The audit identifies an unsupported claim.",'
        '"claim_audits":[{"claim_id":1,"verdict":"UNSUPPORTED",'
        '"evidence_refs":[],"issue":"The scene does not establish this event."}]}'
    )
    assert rejected_claim.claim_audits[0].verdict == "UNSUPPORTED"

    rejected_mixed = parse_diary_fidelity_output(
        '{"kind":"diary_fidelity_review","decision":"REJECT",'
        '"summary":"The audit identifies a mixed claim.",'
        '"claim_audits":[{"claim_id":1,"verdict":"MIXED",'
        '"evidence_refs":[1],"issue":"The second clause is unsupported."}]}'
    )
    assert rejected_mixed.claim_audits[0].verdict == "MIXED"

    with pytest.raises(StructuredOutputError):
        parse_diary_fidelity_output(
            '{"kind":"diary_fidelity_review","decision":"ACCEPT",'
            '"summary":"Looks fine.","invented_events":["A new event"]}'
        )
    with pytest.raises(StructuredOutputError):
        parse_diary_fidelity_output(
            '{"kind":"diary_fidelity_review","decision":"REJECT",'
            '"summary":"Unclear."}'
        )


def test_diary_fidelity_prompt_exposes_only_scene_and_diary_evidence():
    messages = build_diary_fidelity_messages(
        character_name="Mara",
        cast_names=("Mara", "Rory"),
        diary_text="I wondered whether the paw was hurt.",
        accepted_scene=("Mara: I watch the paw from the steps.",),
        evidence_refs=(1,),
        claim_candidates=("Mara watches the paw.", "I feel uncertain."),
    )
    prompt = "\n".join(message["content"] for message in messages)
    assert '"writer_character": "Mara"' in prompt
    assert '"accepted_scene_in_order": ["Mara: I watch the paw from the steps."]' in prompt
    assert '"diary_text": "I wondered whether the paw was hurt."' in prompt
    assert '"writer_evidence_refs": [1]' in prompt
    assert '"accepted_scene_evidence": [{"evidence_id": 1, "text": "Mara: I watch the paw from the steps."}]' in prompt
    assert '"claim_audit_required": true' in prompt
    assert '"claim_id": 1, "text": "Mara watches the paw."' in prompt
    assert "exactly one claim_audits item for every candidate ID" in prompt
    assert "I wonder" in prompt
    assert "MIXED" in prompt
    assert "Do not collapse MIXED into UNSUPPORTED" in prompt
    assert "Jo left a paper kite on the bench" in prompt
    assert "even if another audit is UNSUPPORTED" in prompt
    assert "hidden direction" not in prompt
    assert "ACCEPT requires all five finding lists to be empty" in prompt


def test_orchestrator_tagged_output_is_strict_and_typed():
    result = parse_orchestrator_output(
        "<NARRATION>The lights dim.</NARRATION>"
        "<NEXT_ACTOR>MARA</NEXT_ACTOR>"
        "<COMPLETE>false</COMPLETE>"
        "<CANON_UPDATE>The lights dim.</CANON_UPDATE>"
        "<CANON_UPDATE>The station notices.</CANON_UPDATE>"
    )
    assert isinstance(result, OrchestratorEnvelope)
    assert result.next_actor == "MARA"
    assert result.canon_updates == ["The lights dim.", "The station notices."]


def test_orchestrator_schema_bounds_output_and_omits_unused_intervention_field():
    schema = schema_for("orchestrator")
    assert schema["properties"]["narration"]["maxLength"] == 1600
    assert schema["properties"]["canon_updates"]["maxItems"] == 2
    assert "intervention" not in schema["properties"]


def test_orchestrator_reviewer_rejects_cast_puppeteering_but_allows_environmental_beats():
    assert review_orchestrator_narration(
        "A hot pressure wave makes the bulkhead seam sing.", actor_names=("Mara", "Nox")
    ) is None
    issue = review_orchestrator_narration(
        "Mara tightens her grip and says, 'We should run.'", actor_names=("Mara", "Nox")
    )
    assert issue is not None
    assert issue.code == "ACTOR_PUPPETEERING"


@pytest.mark.parametrize(
    "text",
    (
        "Ivy watched the archive recede.",
        "Mason checked the propulsion gauge.",
        "Luna studied condensation on the bulkhead.",
        "Ivy had rested her hand on the console.",
    ),
)
def test_orchestrator_reviewer_rejects_past_tense_cast_actions(text):
    issue = review_orchestrator_narration(
        text,
        actor_names=("Ivy Fermion", "Mason Curie", "Luna Planck"),
    )
    assert issue is not None
    assert issue.code == "ACTOR_PUPPETEERING"


def test_actor_reviewer_allows_own_physical_action_without_target_reaction():
    assert review_actor_text(
        "I grip Mason's shoulder and shove him toward the lock.",
        actor_name="Higgs",
        other_actor_names=("Mason", "Luna"),
    ) is None


def test_actor_reviewer_rejects_authored_target_reaction_after_violence():
    issue = review_actor_text(
        "I stab Mason. He screams and collapses.",
        actor_name="Higgs",
        other_actor_names=("Mason", "Luna"),
    )
    assert issue is not None
    assert issue.code == "OTHER_CHARACTER_AUTONOMY"


@pytest.mark.parametrize(
    "text",
    (
        "If the next pulse hits us, Ivy, we lose the observation window.",
        "The next pulse hits in eighteen minutes, Mason. We should choose now.",
        "Ivy, when those reserves hit fifty percent, propulsion stays offline.",
        "Propulsion is dead, so I redirect cooling through the habitat loop.",
    ),
)
def test_actor_reviewer_allows_nonviolent_hit_idioms_and_dead_machine_state(text):
    assert review_actor_text(
        text,
        actor_name="Luna Planck",
        other_actor_names=("Ivy Fermion", "Mason Curie"),
    ) is None


@pytest.mark.parametrize(
    "text",
    (
        "I hit Mason.",
        "I punch Nox.",
        "I attack Ivy.",
        "I fight with Ivy.",
    ),
)
def test_actor_reviewer_allows_locally_targeted_nonfatal_violence(text):
    assert review_actor_text(
        text,
        actor_name="Luna Planck",
        other_actor_names=("Ivy Fermion", "Mason Curie", "Nox"),
    ) is None


@pytest.mark.parametrize(
    "text",
    (
        "I am dead.",
        "We're already dead.",
        "Propulsion is dead, and Mason is dead.",
        "I kill Mason.",
    ),
)
def test_actor_reviewer_keeps_person_death_language_blocked(text):
    issue = review_actor_text(
        text,
        actor_name="Luna Planck",
        other_actor_names=("Ivy Fermion", "Mason Curie"),
    )
    assert issue is not None
    assert issue.code == "ACTOR_DEATH"


@pytest.mark.parametrize(
    "text",
    (
        "Blind and hot is how people die.",
        "We might be dead by morning if the air fails.",
        "The orchard's death was the price of breathable air.",
        "I let the archive signal die away.",
        "We're dead weight if the basalt door closes.",
        "The thing outside wants to kill us.",
    ),
)
def test_actor_reviewer_allows_peril_and_nonhuman_death_language(text):
    assert review_actor_text(
        text,
        actor_name="Luna Planck",
        other_actor_names=("Ivy Fermion", "Mason Curie"),
    ) is None


def test_orientation_allows_bounded_nsfw_and_character_violence():
    text = "\n".join(
        message["content"] for message in build_orientation_messages(actor_name="Luna Planck")
    )
    assert "violence between player-characters" in text
    assert "fade-to-black sexual implications are allowed" in text
    assert "explicitly established as an adult" in text
    assert "sexual violence or coercion" in text
    assert "involuntary player-character death" in text


def test_orchestrator_reviewer_allows_a_named_echo_of_an_accepted_actor_action():
    assert review_orchestrator_narration(
        "Ivy's whisper lingers as the hull's low hum settles.",
        actor_names=("Ivy", "Mara"),
    ) is None


def test_orchestrator_reviewer_rejects_excessive_reuse_of_spent_imagery():
    issue = review_orchestrator_narration(
        "The pulse shakes the hull while a metallic scent fills the core chamber.",
        actor_names=("Ivy",),
        spent_imagery=("pulse", "hull", "metallic", "core"),
    )
    assert issue is not None
    assert issue.code == "SPENT_IMAGERY_REUSED"


@pytest.mark.parametrize("raw", ("", "<COMPLETE>false</COMPLETE>", "<NARRATION></NARRATION>"))
def test_orchestrator_parser_rejects_missing_or_empty_narration(raw):
    with pytest.raises(StructuredOutputError):
        parse_orchestrator_output(raw)


def test_orchestrator_parser_repairs_only_observed_narration_closing_typo():
    result = parse_orchestrator_output(
        "<NARRATION>The coolant vent hisses.</LARRATION>"
        "<NEXT_ACTOR>Luna Planck</NEXT_ACTOR>"
        "<COMPLETE>false</COMPLETE>"
        "<CANON_UPDATE>The thermal margin narrows.</CANON_UPDATE>"
    )

    assert result.narration == "The coolant vent hisses."
    assert result.next_actor == "Luna Planck"
    assert result.complete is False
    assert result.canon_updates == ["The thermal margin narrows."]


def test_orchestrator_parser_still_rejects_other_mismatched_closing_tags():
    with pytest.raises(StructuredOutputError):
        parse_orchestrator_output(
            "<NARRATION>The coolant vent hisses.</WRONG_TAG>"
            "<COMPLETE>false</COMPLETE>"
        )


def test_context_builders_keep_peer_and_unclosed_diary_material_out():
    role = RoleSheet(character_id="mara", secrets=["mara-secret"])
    actor = build_actor_messages(
        ActorContext(
            actor_name="MARA",
            role_sheet=role,
            known_memory=("I saw the hatch.",),
            accepted_canon=("The station is old.",),
            scene_transcript=("MARA: I listen.",),
            mission_clock="Day 2 of 7, morning after overnight sleep.",
            previous_shared_outcome="The hatch answered once.",
            round_number=1,
        )
    )
    actor_text = "\n".join(message["content"] for message in actor)
    assert "mara-secret" in actor_text
    assert "other-secret" not in actor_text
    assert "overnight sleep" in actor_text
    assert "one concrete contribution" in actor_text
    assert "Might is strength, endurance, and hands-on physical effort" in actor_text
    assert "never control over another character" in actor_text
    assert "never make a setback a dead end" in actor_text
    assert "hidden breakfast complication" not in actor_text

    opening = OpeningSnapshot(set="Station", setting="Orbit", cast=["MARA"])
    plan = HiddenSeasonPlan(hidden_mysteries=["private answer"])
    with pytest.raises(ContextBoundaryError):
        build_orchestrator_messages(
            opening=opening,
            private_plan=plan,
            accepted_canon=(),
            scene_transcript=(),
            closed_diaries=("spoiler diary",),
            day_closed=False,
        )

    orchestrator = build_orchestrator_messages(
        opening=opening,
        private_plan=plan,
        accepted_canon=("The hatch answered once.",),
        scene_transcript=("MARA: I listen.",),
        mission_clock="Day 2 of 7, morning after overnight sleep.",
        private_day_direction="hidden breakfast complication",
        round_number=1,
        max_rounds=4,
    )
    orchestrator_text = "\n".join(message["content"] for message in orchestrator)
    assert "hidden breakfast complication" in orchestrator_text
    assert "mission-progress, danger, mystery, and relationship clocks" in orchestrator_text
    assert "not every run is a crisis" in orchestrator_text
    assert "because-now-choice handoff" in orchestrator_text
    assert "Authority is advocacy, coordination, and earning trust" in orchestrator_text
    assert "never make a setback a dead end" in orchestrator_text
    assert '"continuity_anchors"' in orchestrator_text
    assert '"spent_director_imagery"' in orchestrator_text

    culmination = build_director_plan_messages(
        opening=opening,
        private_plan=plan,
        accepted_canon=("The hatch answered once.",),
        scene_transcript=("MARA: I listen.",),
        game_state={"scene_objective": "Will the station answer?"},
        mission_clock="Day 2 of 7, evening.",
        previous_shared_outcome=None,
        private_day_direction=None,
        round_number=4,
        max_rounds=4,
        spent_director_terms=("hatch", "signal"),
    )
    culmination_text = "\n".join(message["content"] for message in culmination)
    assert '"round_phase": "final-player-decision"' in culmination_text
    assert '"spent_director_imagery": ["hatch", "signal"]' in culmination_text
    assert "forbidden_visible_terms" not in culmination_text
    assert "set complete=false" in culmination_text
    assert "not a ban on functional nouns" in culmination_text
    assert "Cool is composure, patience, and timing under pressure" in culmination_text
    assert "never make a setback a dead end" in culmination_text

    diary = build_diary_messages(
        actor_name="MARA",
        role_sheet=role,
        known_memory=("I saw the hatch.",),
        accepted_scene=("The hatch opened.",),
    )
    diary_text = "\n".join(message["content"] for message in diary)
    assert "private answer" not in diary_text
    assert "personal account rather than a technical scene recap" in diary_text
    assert "fictional insomnia" in diary_text
    assert '"accepted_scene_evidence": [{"evidence_id": 1, "text": "The hatch opened."}]' in diary_text
    assert "Every concrete shared-fiction claim in a written diary must be covered" in diary_text
    assert "role-sheet goals and plausible guesses are not evidence" in diary_text
    assert "Eli was frustrated" in diary_text
    assert "trace each sentence before returning the diary" in diary_text


def test_private_audit_writer_redacts_secrets_and_is_append_only(tmp_path):
    assert redact_text("token=abc", ("abc",)) == "token=[REDACTED]"
    writer = AuditWriter(tmp_path / "private")
    artifact = writer.write_text("season/S01/audit/prompt.md", "token=abc", secrets=("abc",))
    assert artifact.path.read_text(encoding="utf-8") == "token=[REDACTED]"
    assert writer.write_text("season/S01/audit/prompt.md", "token=abc", secrets=("abc",)) == artifact
    with pytest.raises(AuditArtifactConflict):
        writer.write_text("season/S01/audit/prompt.md", "different")
    with pytest.raises(ValueError):
        writer.write_text("../outside.md", "no")
