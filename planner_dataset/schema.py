from __future__ import annotations

from typing import Any

from . import SCHEMA_VERSION


class SchemaError(ValueError):
    pass


def validate_record(record: dict[str, Any]) -> None:
    required = {"schema_version", "recording", "words", "timing", "spans", "annotations", "processing_history"}
    missing = required - record.keys()
    if missing:
        raise SchemaError(f"missing root fields: {sorted(missing)}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise SchemaError(f"unsupported schema_version: {record['schema_version']!r}")
    recording = record["recording"]
    if not isinstance(recording, dict):
        raise SchemaError("recording must be an object")
    fields = {"id", "audio_path", "audio_sha256", "speaker_id", "source_recording_id", "transcript_original", "source_audio_offset_s", "split"}
    missing = fields - recording.keys()
    if missing:
        raise SchemaError(f"recording missing fields: {sorted(missing)}")
    if not isinstance(recording["transcript_original"], str) or not recording["transcript_original"]:
        raise SchemaError("recording.transcript_original must be non-empty string")
    if not isinstance(record["words"], list) or not record["words"]:
        raise SchemaError("words must be a non-empty list")
    last_end = -1
    for index, word in enumerate(record["words"]):
        if not isinstance(word, dict) or {"id", "text", "start_char", "end_char", "normalized"} - word.keys():
            raise SchemaError(f"invalid word at index {index}")
        if word["id"] != f"{recording['id']}:w{index + 1:06d}":
            raise SchemaError(f"unstable word id at index {index}")
        if not (isinstance(word["start_char"], int) and isinstance(word["end_char"], int) and word["start_char"] >= last_end and word["end_char"] > word["start_char"]):
            raise SchemaError(f"invalid offsets at word {index}")
        if recording["transcript_original"][word["start_char"]:word["end_char"]] != word["text"]:
            raise SchemaError(f"word text does not match original transcript at word {index}")
        last_end = word["end_char"]
    if record["timing"] is None or not isinstance(record["timing"], dict) or {"word_intervals", "phone_intervals"} - record["timing"].keys():
        raise SchemaError("timing must contain word_intervals and phone_intervals")
    if not isinstance(record["spans"], list) or not isinstance(record["annotations"], dict) or not isinstance(record["processing_history"], list):
        raise SchemaError("spans, annotations, and processing_history have invalid types")
