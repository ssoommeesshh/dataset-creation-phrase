from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

WORD_RE = re.compile(r"\S+", re.UNICODE)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalized_word(value: str) -> str:
    """Case-fold text and remove punctuation for matching; never alter stored text."""
    return "".join(char for char in value.casefold() if char.isalnum() or char == "_")


def original_words(transcript: str) -> list[dict[str, Any]]:
    return [
        {"text": match.group(), "start_char": match.start(), "end_char": match.end(),
         "normalized": normalized_word(match.group())}
        for match in WORD_RE.finditer(transcript)
    ]


def read_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: JSONL item must be an object")
        yield value


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
