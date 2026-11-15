from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import RECONCILIATION_VERSION
from .schema import validate_record
from .util import normalized_word, stable_hash

MARKERS = {"!!!!!", "<|IU_Boundary|>"}


def parse_psst(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise ValueError("raw_transcription must be a string")
    tokens = raw.split()
    generated = []
    marker_after = []
    leading_markers = []
    for position, token in enumerate(tokens):
        if token in MARKERS:
            if generated:
                marker_after.append(len(generated) - 1)
            else:
                leading_markers.append(position)
        else:
            generated.append({"text": token, "normalized": normalized_word(token), "raw_token_index": position})
    return {"generated_words": generated, "marker_after_generated_indices": marker_after,
            "leading_marker_token_indices": leading_markers, "accepted_markers": sorted(MARKERS)}


def reconcile(original: list[str], generated: list[str]) -> dict[str, Any]:
    """Global alignment with conservative ambiguity detection across all optimal paths."""
    n, m = len(original), len(generated)
    inf = 10**9
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            here = dp[i][j]
            if i < n: dp[i + 1][j] = min(dp[i + 1][j], here + 1)
            if j < m: dp[i][j + 1] = min(dp[i][j + 1], here + 1)
            if i < n and j < m: dp[i + 1][j + 1] = min(dp[i + 1][j + 1], here + (0 if original[i] == generated[j] else 2))
    back = [[inf] * (m + 1) for _ in range(n + 1)]
    back[n][m] = 0
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n and j == m: continue
            options = []
            if i < n: options.append(1 + back[i + 1][j])
            if j < m: options.append(1 + back[i][j + 1])
            if i < n and j < m: options.append((0 if original[i] == generated[j] else 2) + back[i + 1][j + 1])
            back[i][j] = min(options)
    total = dp[n][m]
    candidates = [[] for _ in original]
    for i in range(n):
        for j in range(m):
            if original[i] and original[i] == generated[j] and dp[i][j] + back[i + 1][j + 1] == total:
                candidates[i].append(j)
    mapping, status = [], []
    for possible in candidates:
        if len(possible) == 1:
            mapping.append(possible[0]); status.append("reliable")
        elif len(possible) > 1:
            mapping.append(None); status.append("ambiguous")
        else:
            mapping.append(None); status.append("unmapped")
    # A generated match cannot be safely shared by distinct original words.
    for j in range(m):
        owners = [i for i, mapped in enumerate(mapping) if mapped == j]
        if len(owners) > 1:
            for i in owners: mapping[i], status[i] = None, "ambiguous"
    return {"edit_distance": total, "original_to_generated": mapping, "word_status": status}


def annotate_record(record: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    validate_record(record)
    if output.get("recording_id") != record["recording"]["id"]:
        raise ValueError("PSST output recording_id does not match record")
    # The saved output is the CPU-stage cache boundary. A later live adapter can
    # reuse it by submitting the same versioned raw-output object unchanged.
    previous = record.get("annotations", {}).get("psst")
    if previous and previous.get("raw_output_sha256") == stable_hash(output):
        return deepcopy(record)
    raw = output.get("raw_transcription")
    parsed = parse_psst(raw)
    originals = [word["normalized"] for word in record["words"]]
    generated = [word["normalized"] for word in parsed["generated_words"]]
    alignment = reconcile(originals, generated)
    labels = []
    markers = set(parsed["marker_after_generated_indices"])
    for index in range(len(originals)):
        if index == len(originals) - 1:
            labels.append({"after_word_id": record["words"][index]["id"], "label": -100, "status": "clip_final_excluded"})
            continue
        left, right = alignment["original_to_generated"][index:index + 2]
        if alignment["word_status"][index] != "reliable" or alignment["word_status"][index + 1] != "reliable":
            labels.append({"after_word_id": record["words"][index]["id"], "label": -100, "status": "uncertain_transfer"})
        elif right != left + 1:
            labels.append({"after_word_id": record["words"][index]["id"], "label": -100, "status": "non_adjacent_generated_words"})
        else:
            labels.append({"after_word_id": record["words"][index]["id"], "label": 1 if left in markers else 0,
                           "status": "teacher_boundary" if left in markers else "teacher_nonboundary"})
    result = deepcopy(record)
    result["annotations"]["psst"] = {
        "status": "reconciled", "reconciliation_version": RECONCILIATION_VERSION,
        "raw_transcription": raw, "raw_output_sha256": stable_hash(output), "source": output.get("source", {}),
        "parsed": parsed, "alignment": alignment, "boundary_after_word": labels,
    }
    result["processing_history"].append({"module": "psst_import", "version": RECONCILIATION_VERSION,
                                         "input_sha256": stable_hash(output), "status": "complete"})
    validate_record(result)
    return result
