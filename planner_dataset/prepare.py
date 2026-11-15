from __future__ import annotations

from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .schema import validate_record
from .util import original_words, read_jsonl, sha256_file, stable_hash


def _split(group: str, seed: str) -> str:
    point = int(stable_hash({"seed": seed, "group": group})[:16], 16) / 2**64
    return "train" if point < 0.8 else "validation" if point < 0.9 else "test"


def prepare_manifest(manifest_path: str | Path, *, split_by: str = "source", seed: str = "planner-dataset-v1") -> list[dict[str, Any]]:
    if split_by not in {"source", "speaker"}:
        raise ValueError("split_by must be 'source' or 'speaker'")
    result = []
    seen = set()
    root = Path(manifest_path).parent
    manifest_hash = sha256_file(manifest_path)
    for item in read_jsonl(manifest_path):
        required = {"recording_id", "audio_path", "speaker_id", "source_recording_id", "transcript"}
        missing = required - item.keys()
        if missing:
            raise ValueError(f"manifest record missing fields: {sorted(missing)}")
        recording_id = item["recording_id"]
        if not isinstance(recording_id, str) or not recording_id or recording_id in seen:
            raise ValueError(f"recording_id must be unique non-empty string: {recording_id!r}")
        seen.add(recording_id)
        if not isinstance(item["transcript"], str) or not item["transcript"]:
            raise ValueError(f"{recording_id}: transcript must be non-empty string")
        path = Path(item["audio_path"])
        resolved = path if path.is_absolute() else root / path
        if not resolved.is_file():
            raise ValueError(f"{recording_id}: audio file does not exist: {resolved}")
        words = original_words(item["transcript"])
        if not words:
            raise ValueError(f"{recording_id}: transcript has no whitespace-delimited tokens")
        group = str(item["source_recording_id"] if split_by == "source" else item["speaker_id"])
        word_rows = [{"id": f"{recording_id}:w{i:06d}", **word} for i, word in enumerate(words, 1)]
        record = {
            "schema_version": SCHEMA_VERSION,
            "recording": {
                "id": recording_id, "audio_path": item["audio_path"], "audio_sha256": sha256_file(resolved),
                "speaker_id": item["speaker_id"], "source_recording_id": item["source_recording_id"],
                "transcript_original": item["transcript"], "source_audio_offset_s": item.get("source_audio_offset_s", 0.0),
                "split": _split(group, seed),
            },
            "words": word_rows,
            "timing": {"word_intervals": None, "phone_intervals": None},
            "spans": [], "annotations": {},
            "processing_history": [{"module": "prepare", "version": SCHEMA_VERSION, "manifest_sha256": manifest_hash,
                                    "audio_sha256": sha256_file(resolved), "split_by": split_by, "split_seed": seed,
                                    "status": "complete"}],
        }
        validate_record(record)
        result.append(record)
    return result
