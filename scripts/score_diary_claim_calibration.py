#!/usr/bin/env python3
"""Score a completed private diary-claim calibration packet."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


MODEL_LABELS = {"SUPPORTED", "SUBJECTIVE", "UNSUPPORTED", "MIXED"}
HUMAN_LABELS = {"SUPPORTED", "SUBJECTIVE", "UNSUPPORTED", "AMBIGUOUS"}


def _jsonl_read(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise RuntimeError(f"Invalid JSON on line {line_number} of {path}: {exc}") from exc
        if not isinstance(record, dict):
            raise RuntimeError(f"JSONL record on line {line_number} is not an object: {path}")
        records.append(record)
    return records


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _score(packet_dir: Path) -> dict[str, Any]:
    label_path = packet_dir / "claims-for-labeling.jsonl"
    model_path = packet_dir / "model-annotations.jsonl"
    if not label_path.is_file() or not model_path.is_file():
        raise RuntimeError(f"packet is missing required JSONL files: {packet_dir}")

    labels = _jsonl_read(label_path)
    models = _jsonl_read(model_path)
    label_by_id = {str(record.get("item_id")): record for record in labels}
    model_by_id = {str(record.get("item_id")): record for record in models}
    if len(label_by_id) != len(labels) or len(model_by_id) != len(models):
        raise RuntimeError("packet contains duplicate item_id values")
    if set(label_by_id) != set(model_by_id):
        raise RuntimeError("label and model files do not contain the same item_id values")

    missing = 0
    invalid = 0
    human_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    eligible = 0
    exact = 0
    unsupported_tp = 0
    unsupported_fp = 0
    unsupported_fn = 0

    for item_id, label_record in label_by_id.items():
        human_label = label_record.get("human_label")
        model_label = model_by_id[item_id].get("model_verdict")
        if not isinstance(model_label, str) or model_label not in MODEL_LABELS:
            raise RuntimeError(f"invalid model verdict for {item_id}: {model_label!r}")
        model_counts[str(model_label)] += 1
        if human_label is None or human_label == "":
            missing += 1
            continue
        if not isinstance(human_label, str) or human_label not in HUMAN_LABELS:
            invalid += 1
            continue
        human_counts[str(human_label)] += 1
        if human_label == "AMBIGUOUS":
            continue
        eligible += 1
        confusion[str(human_label)][str(model_label)] += 1
        if human_label == model_label:
            exact += 1
        if human_label == "UNSUPPORTED" and model_label == "UNSUPPORTED":
            unsupported_tp += 1
        elif human_label != "UNSUPPORTED" and model_label == "UNSUPPORTED":
            unsupported_fp += 1
        elif human_label == "UNSUPPORTED" and model_label != "UNSUPPORTED":
            unsupported_fn += 1

    precision = _rate(unsupported_tp, unsupported_tp + unsupported_fp)
    recall = _rate(unsupported_tp, unsupported_tp + unsupported_fn)
    f1 = (
        round(2 * precision * recall / (precision + recall), 6)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    status = "COMPLETE" if not missing and not invalid else "PENDING_HUMAN_LABELS"
    return {
        "status": status,
        "packet_dir": str(packet_dir),
        "claim_count": len(labels),
        "human_labeled_count": sum(human_counts.values()),
        "human_unlabeled_count": missing,
        "human_invalid_count": invalid,
        "human_ambiguous_count": human_counts.get("AMBIGUOUS", 0),
        "human_label_counts": dict(sorted(human_counts.items())),
        "model_verdict_counts": dict(sorted(model_counts.items())),
        "eligible_non_ambiguous_count": eligible,
        "exact_agreement_count": exact,
        "exact_agreement_rate": _rate(exact, eligible),
        "unsupported_confusion": {
            "true_positive": unsupported_tp,
            "false_positive": unsupported_fp,
            "false_negative": unsupported_fn,
        },
        "unsupported_precision": precision,
        "unsupported_recall": recall,
        "unsupported_f1": f1,
        "confusion_matrix_human_rows_model_columns": {
            human: dict(sorted(row.items())) for human, row in sorted(confusion.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    packet_dir = args.packet_dir.expanduser().resolve()
    try:
        result = _score(packet_dir)
    except RuntimeError as exc:
        parser.error(str(exc))

    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
