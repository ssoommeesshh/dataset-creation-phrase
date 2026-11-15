"""Optional live PSST inference; imported only by the annotate-psst CLI command."""
from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from .psst import annotate_record

DEFAULT_MODEL = "NathanRoll/psst-medium-en"


class PSSTRuntimeError(RuntimeError):
    pass


class PSSTPredictor:
    """Thin, cache-friendly wrapper around the official PSST model artifacts."""
    def __init__(self, *, model_name: str = DEFAULT_MODEL, revision: str | None = None,
                 device: str = "auto", max_audio_seconds: float = 30.0,
                 max_new_tokens: int = 250) -> None:
        try:
            import librosa
            import torch
            import transformers
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
        except ImportError as exc:
            raise PSSTRuntimeError("Live PSST inference needs `pip install -e '.[psst]'`.") from exc
        if device == "auto": device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise PSSTRuntimeError("--device cuda was requested but CUDA is unavailable.")
        if device not in {"cpu", "cuda"}:
            raise PSSTRuntimeError("device must be auto, cpu, or cuda")
        self.librosa, self.torch, self.transformers = librosa, torch, transformers
        self.model_name, self.revision, self.device = model_name, revision, device
        self.max_audio_seconds, self.max_new_tokens = max_audio_seconds, max_new_tokens
        kwargs: dict[str, Any] = {"revision": revision} if revision else {}
        self.processor = AutoProcessor.from_pretrained(model_name, **kwargs)
        # Keep CPU support correct; half precision is only an optional GPU optimization.
        if device == "cuda": kwargs["torch_dtype"] = torch.float16
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(model_name, **kwargs).to(device)
        self.model.eval()
        self.resolved_revision = getattr(self.model.config, "_commit_hash", None) or revision or "unresolved"

    def output_for(self, record: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
        audio_ref = Path(record["recording"]["audio_path"])
        path = audio_ref if audio_ref.is_absolute() else base_dir / audio_ref
        if not path.is_file():
            raise PSSTRuntimeError(f"{record['recording']['id']}: audio does not exist: {path}")
        audio, sample_rate = self.librosa.load(str(path), sr=16000, mono=True)
        duration = len(audio) / sample_rate
        if duration > self.max_audio_seconds:
            raise PSSTRuntimeError(
                f"{record['recording']['id']}: {duration:.2f}s exceeds {self.max_audio_seconds}s; "
                "segment upstream and record clip offsets before PSST inference."
            )
        inputs = self.processor(audio, sampling_rate=16000, return_tensors="pt")
        features = inputs.input_features.to(self.device)
        with self.torch.inference_mode():
            ids = self.model.generate(features, max_new_tokens=self.max_new_tokens)
        raw = self.processor.batch_decode(ids, skip_special_tokens=True)[0]
        return {
            "recording_id": record["recording"]["id"], "raw_transcription": raw,
            "source": {"model": self.model_name, "revision_requested": self.revision,
                       "revision_resolved": self.resolved_revision, "device": self.device,
                       "audio_sha256": record["recording"]["audio_sha256"],
                       "generation": {"max_new_tokens": self.max_new_tokens, "max_audio_seconds": self.max_audio_seconds},
                       "runtime": {"torch": self.torch.__version__, "transformers": self.transformers.__version__,
                                   "python": platform.python_version()}},
        }


def annotate_live(records: list[dict[str, Any]], *, records_path: str | Path, model_name: str = DEFAULT_MODEL,
                  revision: str | None = None, device: str = "auto", max_audio_seconds: float = 30.0,
                  max_new_tokens: int = 250) -> list[dict[str, Any]]:
    predictor = PSSTPredictor(model_name=model_name, revision=revision, device=device,
                              max_audio_seconds=max_audio_seconds, max_new_tokens=max_new_tokens)
    root = Path(records_path).parent
    result = []
    for record in records:
        # Existing evidence with the same model/source checksum is a reusable inference cache.
        previous = record.get("annotations", {}).get("psst", {})
        source = previous.get("source", {})
        if (previous.get("status") == "reconciled" and source.get("model") == model_name and
                source.get("revision_requested") == revision and source.get("audio_sha256") == record["recording"]["audio_sha256"] and
                source.get("generation") == {"max_new_tokens": max_new_tokens, "max_audio_seconds": max_audio_seconds}):
            result.append(record)
            continue
        result.append(annotate_record(record, predictor.output_for(record, base_dir=root)))
    return result
