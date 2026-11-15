# PSST reconciliation and transfer rules (version 1.0)

PSST jointly transcribes and marks intonation-unit boundaries. The official repository says it emits `!!!!!`; its published Python helper replaces that token with `<|IU_Boundary|>` after decoding. This importer accepts these two exact marker forms only, as whitespace-delimited tokens. Sources: [PSST README](https://github.com/Nathan-Roll1/PSST) and [published helper](https://github.com/Nathan-Roll1/PSST/blob/main/functions.py).

1. Preserve `raw_transcription`, marker positions, source metadata, and an input hash unchanged under `annotations.psst`.
2. Tokenize generated non-marker text by whitespace and normalize it exactly as original words are normalized: Unicode case-fold plus punctuation removal.
3. Use a global monotonic edit-distance alignment. Exact normalized matches cost zero; generated-only and original-only words cost one; substitutions cost two.
4. An original/generated match is reliable only if it is an exact pair on an optimal alignment **and** is the sole possible exact partner on every optimal alignment. Repeated-word alternatives are therefore flagged `ambiguous`, not arbitrarily chosen.
5. For original junction `i -> i+1`, transfer only if it is internal, both words are reliable, and their generated indices are adjacent. A marker immediately after generated `i` gives `1`; no marker gives `0`. All other junctions receive `-100`.

The final original word has no following internal junction and is always masked. A marker after the final generated word is recorded but never converted to a terminal label. Punctuation is not a boundary signal.
