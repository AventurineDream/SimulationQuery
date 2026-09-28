#!/usr/bin/env python3
"""Build a private, model-blind diary-claim calibration packet.

The source rehearsal database and model-call artifacts are private evidence. The
generated packet deliberately separates the human-labeling file from the model
annotations so the first pass can be completed without anchoring on the model's
judgments.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL_VERDICTS = {"SUPPORTED", "SUBJECTIVE", "UNSUPPORTED", "MIXED"}
HUMAN_LABELS = {"SUPPORTED", "SUBJECTIVE", "UNSUPPORTED", "AMBIGUOUS"}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not read JSON artifact {path}: {exc}") from exc


def _jsonl_write(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _latest_review_event(connection: sqlite3.Connection, diary_id: str) -> dict[str, Any] | None:
    rows = connection.execute(
        "SELECT payload_json FROM domain_events "
        "WHERE aggregate_id = ? AND event_type = 'DiaryFidelityReviewed' "
        "ORDER BY created_at DESC, event_id DESC LIMIT 1",
        (diary_id,),
    ).fetchall()
    if not rows:
        return None
    try:
        payload = json.loads(str(rows[0]["payload_json"]))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _model_call(connection: sqlite3.Connection, call_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT prompt_path FROM model_calls WHERE call_id = ? LIMIT 1",
        (call_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _accepted_scene_evidence(prompt_path: Path) -> list[dict[str, Any]]:
    messages = _read_json(prompt_path)
    if not isinstance(messages, list):
        raise RuntimeError(f"Reviewer prompt is not a message list: {prompt_path}")
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            continue
        try:
            context = json.loads(str(message["content"]))
        except ValueError:
            continue
        if not isinstance(context, dict):
            continue
        evidence = context.get("accepted_scene_evidence")
        if not isinstance(evidence, list):
            continue
        normalized: list[dict[str, Any]] = []
        for item in evidence:
            if not isinstance(item, dict):
                raise RuntimeError(f"Malformed accepted-scene evidence in {prompt_path}")
            normalized.append(
                {
                    "evidence_id": int(item["evidence_id"]),
                    "text": str(item["text"]),
                }
            )
        return normalized
    raise RuntimeError(f"No accepted-scene evidence found in reviewer prompt: {prompt_path}")


def _review_path(review_event: dict[str, Any]) -> Path:
    raw_path = review_event.get("review_path")
    if not raw_path:
        raise RuntimeError("Diary review event does not contain review_path")
    path = Path(str(raw_path))
    if not path.is_file():
        raise RuntimeError(f"Diary review artifact is missing: {path}")
    return path


def _records(data_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    database_path = data_root / "state" / "improv.sqlite3"
    if not database_path.is_file():
        raise RuntimeError(f"Rehearsal database is missing: {database_path}")

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        diary_rows = connection.execute(
            "SELECT diary_id, character_id, day_number, status, word_count "
            "FROM diaries WHERE status = 'WRITTEN' ORDER BY character_id, diary_id"
        ).fetchall()
        labeling_records: list[dict[str, Any]] = []
        model_records: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []

        for diary_row in diary_rows:
            diary_id = str(diary_row["diary_id"])
            character_id = str(diary_row["character_id"])
            review_event = _latest_review_event(connection, diary_id)
            if review_event is None:
                skipped.append({"diary_id": diary_id, "reason": "no completed diary review"})
                continue

            review_path = _review_path(review_event)
            review = _read_json(review_path)
            if not isinstance(review, dict):
                raise RuntimeError(f"Diary review is not an object: {review_path}")
            candidates = review.get("claim_candidates")
            audits = review.get("claim_audits")
            if not isinstance(candidates, list) or not all(isinstance(item, str) for item in candidates):
                raise RuntimeError(f"Diary review has no valid claim_candidates: {review_path}")
            if not isinstance(audits, list):
                raise RuntimeError(f"Diary review has no valid claim_audits: {review_path}")

            call_id = str(review_event.get("call_id", ""))
            call = _model_call(connection, call_id)
            if call is None or not call.get("prompt_path"):
                raise RuntimeError(f"Reviewer model call is missing for {diary_id}")
            evidence = _accepted_scene_evidence(Path(str(call["prompt_path"])))
            evidence_ids = {int(item["evidence_id"]) for item in evidence}

            audit_by_id: dict[int, dict[str, Any]] = {}
            for audit in audits:
                if not isinstance(audit, dict):
                    raise RuntimeError(f"Malformed claim audit in {review_path}")
                claim_id = int(audit["claim_id"])
                if claim_id in audit_by_id:
                    raise RuntimeError(f"Duplicate claim audit {claim_id} in {review_path}")
                verdict = str(audit.get("verdict", ""))
                if verdict not in MODEL_VERDICTS:
                    raise RuntimeError(f"Unknown model verdict {verdict!r} in {review_path}")
                refs = [int(ref) for ref in audit.get("evidence_refs", [])]
                if not set(refs).issubset(evidence_ids):
                    raise RuntimeError(f"Model evidence reference outside accepted scene in {review_path}")
                audit_by_id[claim_id] = {
                    "verdict": verdict,
                    "evidence_refs": refs,
                    "issue": audit.get("issue"),
                }

            expected_ids = set(range(1, len(candidates) + 1))
            if set(audit_by_id) != expected_ids:
                raise RuntimeError(f"Claim audit IDs do not match candidates in {review_path}")

            writer_refs = [int(ref) for ref in review.get("writer_evidence_refs", [])]
            if not set(writer_refs).issubset(evidence_ids):
                raise RuntimeError(f"Writer evidence reference outside accepted scene in {review_path}")

            for claim_id, claim_text in enumerate(candidates, start=1):
                item_id = f"{character_id}-{claim_id:03d}"
                audit = audit_by_id[claim_id]
                labeling_records.append(
                    {
                        "item_id": item_id,
                        "source_diary_id": diary_id,
                        "character_id": character_id,
                        "day_number": int(diary_row["day_number"]),
                        "claim_id": claim_id,
                        "claim_text": claim_text,
                        "accepted_scene_evidence": evidence,
                        "writer_evidence_refs": writer_refs,
                        "human_label": None,
                        "human_evidence_refs": [],
                        "human_notes": "",
                    }
                )
                model_records.append(
                    {
                        "item_id": item_id,
                        "source_diary_id": diary_id,
                        "character_id": character_id,
                        "day_number": int(diary_row["day_number"]),
                        "claim_id": claim_id,
                        "model_verdict": audit["verdict"],
                        "model_evidence_refs": audit["evidence_refs"],
                        "model_issue": audit["issue"],
                        "review_decision": review.get("decision"),
                    }
                )

        manifest = {
            "packet_version": "diary-claim-calibration-v01",
            "source_rehearsal": data_root.name,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "diaries_considered": len(diary_rows),
            "diaries_included": sorted({record["source_diary_id"] for record in labeling_records}),
            "claim_count": len(labeling_records),
            "model_verdict_values": sorted(MODEL_VERDICTS),
            "human_label_values": sorted(HUMAN_LABELS),
            "skipped_diaries": skipped,
            "privacy": "Claim text and scene evidence are private rehearsal artifacts; keep this packet under the ignored rehearsal-data tree.",
        }
        return labeling_records, model_records, manifest
    finally:
        connection.close()


def _write_private_readme(output_dir: Path, manifest: dict[str, Any]) -> None:
    (output_dir / "README.md").write_text(
        "\n".join(
            [
                "# Private diary-claim calibration packet",
                "",
                f"Source rehearsal: `{manifest['source_rehearsal']}`",
                f"Claims: `{manifest['claim_count']}`",
                "",
                "## Labeling pass",
                "",
                "1. Open `claims-for-labeling.jsonl` without opening `model-annotations.jsonl`.",
                "2. For each record, fill `human_label` with `SUPPORTED`, `SUBJECTIVE`, `UNSUPPORTED`, or `AMBIGUOUS`.",
                "3. Add `human_evidence_refs` only for accepted-scene evidence IDs that support the label.",
                "4. Use `human_notes` for a short rationale or boundary question.",
                "5. Run the scorer after the human pass; it joins records by `item_id`.",
                "",
                "The model annotations are intentionally separate so the first pass is not anchored by the model verdict.",
                "Do not copy claim text, diary text, or scene evidence into tracked project documentation.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    data_root = args.data_root.expanduser().resolve()
    if not data_root.is_dir():
        parser.error(f"data root is not a directory: {data_root}")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else data_root / "private" / "calibration" / "claim-annotation-packet-v01"
    )
    existing = [
        output_dir / "claims-for-labeling.jsonl",
        output_dir / "model-annotations.jsonl",
        output_dir / "manifest.json",
    ]
    if any(path.exists() for path in existing) and not args.overwrite:
        parser.error(f"output already exists; pass --overwrite only to rebuild it: {output_dir}")

    labeling_records, model_records, manifest = _records(data_root)
    if not labeling_records:
        parser.error("no completed diary reviews with claim audits were found")

    output_dir.mkdir(parents=True, exist_ok=True)
    _jsonl_write(output_dir / "claims-for-labeling.jsonl", labeling_records)
    _jsonl_write(output_dir / "model-annotations.jsonl", model_records)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_private_readme(output_dir, manifest)

    print(json.dumps({"output_dir": str(output_dir), **manifest}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
