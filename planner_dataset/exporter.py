from __future__ import annotations

from typing import Any


def export_boundaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples = []
    for record in records:
        psst = record.get("annotations", {}).get("psst")
        if not psst or psst.get("status") != "reconciled":
            continue
        for item in psst["boundary_after_word"]:
            word_id = item["after_word_id"]
            word = next(word for word in record["words"] if word["id"] == word_id)
            examples.append({"recording_id": record["recording"]["id"], "split": record["recording"]["split"],
                             "word_id": word_id, "word": word["text"], "label": item["label"],
                             "label_status": item["status"], "label_source": "psst_teacher"})
    return examples


def summarize(records: list[dict[str, Any]]) -> dict[str, int]:
    total = positives = negatives = masked = failures = 0
    for record in records:
        psst = record.get("annotations", {}).get("psst")
        if not psst:
            continue
        if psst.get("status") != "reconciled":
            failures += 1; continue
        for label in psst["boundary_after_word"]:
            total += 1
            if label["label"] == 1: positives += 1
            elif label["label"] == 0: negatives += 1
            else: masked += 1
    return {"junctions": total, "teacher_positives": positives, "teacher_negatives": negatives,
            "masked": masked, "failures": failures}
