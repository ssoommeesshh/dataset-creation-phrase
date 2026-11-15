# Planner dataset creation — CPU foundation

This project creates a versioned, append-only annotation record for audio/transcript pairs. It currently implements preparation, validation, import/reconciliation of **saved** PSST output, a boundary-only export, and summaries. It does **not** download or run PSST, perform forced alignment, modify audio, train a model, or create other prosody annotations.

## Core guarantees

- Original transcripts and original-word IDs are immutable after `prepare`.
- Original words use whitespace-delimited orthographic tokens (`\S+`); their text and exact character offsets are retained. Matching uses a separate case-folded Unicode normalization that drops punctuation.
- PSST output is raw evidence under `annotations.psst`; no other namespace is modified by the importer.
- Boundary junction labels use `1` (teacher-positive), `0` (teacher-negative), and `-100` (unknown/masked). They are automatic teacher labels, never human gold labels.
- A non-terminal internal junction is `0` only when both adjacent original words have a unique, monotonic exact normalized correspondence to adjacent generated PSST words and PSST did not mark the junction. Insertions, deletions, substitutions, ambiguous repeated-word mappings, no lexical words, and clip-final positions are `-100`.
- No punctuation or terminal policy creates a PSST boundary. PSST markers at the end are preserved in raw evidence and excluded from transfer.

## Saved PSST input format

The importer consumes one JSON object per line:

```json
{"recording_id":"demo:clip-1", "raw_transcription":"Hello !!!!! world", "source":{"model":"NathanRoll/psst-medium-en", "revision":"saved-output"}}
```

The official PSST README documents `!!!!!` as its emitted boundary token. Its published helper also serializes it as `<|IU_Boundary|>` after decoding. Both exact, whitespace-delimited forms are accepted; no other marker spelling is guessed. See `docs/reconciliation.md` for the transfer algorithm and links to the official source. Fixtures are explicitly synthetic.

## CPU fixture workflow

```powershell
cd esa-implementation/test2
python fixtures/make_synthetic_audio.py
python -m planner_dataset prepare fixtures/manifest.jsonl fixtures/records.prepared.jsonl
python -m planner_dataset validate fixtures/records.prepared.jsonl
python -m planner_dataset import-psst fixtures/records.prepared.jsonl fixtures/psst.synthetic.jsonl fixtures/records.psst.jsonl
python -m planner_dataset export-boundaries fixtures/records.psst.jsonl fixtures/boundaries.jsonl
python -m planner_dataset summarize fixtures/records.psst.jsonl
python -m unittest discover -s tests -v
```

`fixtures/make_synthetic_audio.py` creates the tiny valid WAV used by the manifest. It is synthetic silence and is only a CPU workflow fixture, not a PSST experiment.

## Commands

```text
python -m planner_dataset prepare MANIFEST.jsonl RECORDS.jsonl [--split-by source|speaker] [--seed SEED]
python -m planner_dataset validate RECORDS.jsonl
python -m planner_dataset import-psst RECORDS.jsonl PSST_OUTPUT.jsonl ANNOTATED.jsonl
python -m planner_dataset export-boundaries ANNOTATED.jsonl EXAMPLES.jsonl
python -m planner_dataset summarize ANNOTATED.jsonl
```

Every prepared record stores source manifest and audio SHA-256 values, schema/reconciliation versions, split settings, and processing provenance. This enables a later inference adapter to cache and resume safely without changing the record format.

## Remaining work

Real PSST inference has not been implemented or tested. A future optional adapter should cache the exact model revision, generation settings, model artifact hash, and input audio hash, then write the saved-output format above. Forced alignment alone may populate the shared `timing` layer; later modules may read it but must not create competing timestamp copies.
