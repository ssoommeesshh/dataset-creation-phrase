from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path

from planner_dataset.exporter import export_boundaries
from planner_dataset.prepare import prepare_manifest
from planner_dataset.psst import annotate_record, parse_psst
from planner_dataset.schema import SchemaError, validate_record
from planner_dataset.util import write_jsonl


class PipelineTests(unittest.TestCase):
    def make_record(self, transcript="Hello, world again."):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); audio = root / "a.wav"
            with wave.open(str(audio), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0\0" * 16)
            manifest = root / "manifest.jsonl"
            write_jsonl(manifest, [{"recording_id": "r", "audio_path": "a.wav", "speaker_id": "s", "source_recording_id": "src", "transcript": transcript}])
            return prepare_manifest(manifest)[0]

    def test_marker_parser_documented_forms(self):
        parsed = parse_psst("hello !!!!! world <|IU_Boundary|> again")
        self.assertEqual([x["text"] for x in parsed["generated_words"]], ["hello", "world", "again"])
        self.assertEqual(parsed["marker_after_generated_indices"], [0, 1])

    def test_exact_transfer_positive_negative_and_terminal_mask(self):
        record = self.make_record()
        out = annotate_record(record, {"recording_id": "r", "raw_transcription": "hello !!!!! world again"})
        labels = out["annotations"]["psst"]["boundary_after_word"]
        self.assertEqual([x["label"] for x in labels], [1, 0, -100])
        self.assertEqual(out["words"][0]["text"], "Hello,")
        self.assertEqual(out["recording"]["transcript_original"], "Hello, world again.")

    def test_insert_delete_and_substitution_mask(self):
        record = self.make_record("one two three")
        for raw in ("one extra two three", "one three", "one other three"):
            labels = annotate_record(record, {"recording_id": "r", "raw_transcription": raw})["annotations"]["psst"]["boundary_after_word"]
            self.assertIn(-100, [x["label"] for x in labels[:-1]], raw)

    def test_ambiguous_repeated_word_mapping_masks(self):
        record = self.make_record("go go now")
        labels = annotate_record(record, {"recording_id": "r", "raw_transcription": "go go go now"})["annotations"]["psst"]["boundary_after_word"]
        self.assertEqual(labels[0]["label"], -100)

    def test_punctuation_case_normalization_and_terminal_marker_not_invented(self):
        record = self.make_record("Can't STOP.")
        out = annotate_record(record, {"recording_id": "r", "raw_transcription": "can't stop !!!!!"})
        labels = out["annotations"]["psst"]["boundary_after_word"]
        self.assertEqual([x["label"] for x in labels], [0, -100])
        self.assertEqual(out["annotations"]["psst"]["parsed"]["marker_after_generated_indices"], [1])

    def test_stable_ids_and_source_grouped_splits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("a.wav", "b.wav"):
                with wave.open(str(root / name), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0\0")
            manifest = root / "m.jsonl"
            rows = [{"recording_id": "a", "audio_path": "a.wav", "speaker_id": "sp", "source_recording_id": "same", "transcript": "one two"},
                    {"recording_id": "b", "audio_path": "b.wav", "speaker_id": "other", "source_recording_id": "same", "transcript": "three four"}]
            write_jsonl(manifest, rows)
            first, second = prepare_manifest(manifest)
            self.assertEqual(first["recording"]["split"], second["recording"]["split"])
            self.assertEqual(first["words"][0]["id"], "a:w000001")
            self.assertEqual(prepare_manifest(manifest)[0]["words"], first["words"])

    def test_schema_and_namespace_independence_and_export(self):
        record = self.make_record("one two")
        record["annotations"]["future_module"] = {"status": "available"}
        annotated = annotate_record(record, {"recording_id": "r", "raw_transcription": "one !!!!! two"})
        self.assertEqual(annotated["annotations"]["future_module"], {"status": "available"})
        examples = export_boundaries([annotated])
        self.assertEqual([(e["word_id"], e["label"]) for e in examples], [("r:w000001", 1), ("r:w000002", -100)])
        broken = json.loads(json.dumps(annotated)); broken["words"][0]["id"] = "bad"
        with self.assertRaises(SchemaError): validate_record(broken)

    def test_same_saved_output_is_idempotent_cache_reuse(self):
        record = self.make_record("one two")
        output = {"recording_id": "r", "raw_transcription": "one two", "source": {"revision": "fixture-v1"}}
        first = annotate_record(record, output)
        second = annotate_record(first, output)
        self.assertEqual(first, second)

    def test_live_adapter_reuses_matching_cached_annotation(self):
        # Exercise live-adapter cache logic without importing model dependencies.
        import planner_dataset.psst_inference as live
        record = self.make_record("one two")
        calls = []
        class FakePredictor:
            def __init__(self, **kwargs): self.kwargs = kwargs
            def output_for(self, item, *, base_dir):
                calls.append(item["recording"]["id"])
                return {"recording_id": "r", "raw_transcription": "one two", "source": {
                    "model": "fake", "revision_requested": None, "audio_sha256": item["recording"]["audio_sha256"],
                    "generation": {"max_new_tokens": 250, "max_audio_seconds": 30.0}}}
        original = live.PSSTPredictor; live.PSSTPredictor = FakePredictor
        try:
            first = live.annotate_live([record], records_path="records.jsonl", model_name="fake")
            second = live.annotate_live(first, records_path="records.jsonl", model_name="fake")
        finally:
            live.PSSTPredictor = original
        self.assertEqual(calls, ["r"])
        self.assertEqual(first, second)


if __name__ == "__main__": unittest.main()
