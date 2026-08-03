"""Decode raw legacy-encoded text (no PDF needed).

Legacy Greek survives outside PDFs — old Word documents, databases, and
1990s-2000s web pages carry the same keystroke encodings. ``decode_text``
takes a plain string; when no encoding is named, ``detect_encoding`` scores
the string against every table and picks the best fit.

Detection is deterministic and reported, never guessed silently: the score
is the mapped-character ratio after decoding, weighted by how much of the
output lands in Greek Unicode blocks. Ties or weak scores are returned to
the caller for a human decision.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from . import tokenize
from .decoder import CharRecord, DecodedWord, TableDecoder, is_greek_char
from .registry import load_tables


@dataclass
class DetectionScore:
  table_id: str
  font: str
  score: float
  mapped_ratio: float
  greek_ratio: float
  code_token_ratio: float
  """Fraction of tokens carrying at least one diacritic key code. Genuine
  legacy Greek has diacritics on most words; plain Latin prose has ~none —
  this is what stops the detector from "decoding" English into pseudo-Greek
  (red-team finding F1, 2026-08-03)."""


@dataclass
class DecodedText:
  text: str
  table_id: str
  words: list[DecodedWord]
  unmapped_total: int
  detection: list[DetectionScore] | None = None
  warning: str | None = None

  @property
  def fully_mapped(self) -> bool:
    return self.unmapped_total == 0


def table_id(tdoc: dict) -> str:
  return tdoc.get("id") or tdoc.get("family") or tdoc["font"]


def tables_by_id() -> dict[str, dict]:
  return {table_id(t): t for t in load_tables()}


def _score(tdoc: dict, sample: str) -> DetectionScore:
  dec = TableDecoder(tdoc)
  keep = frozenset(tdoc["letters"]) | frozenset(tdoc["codes"])
  mark_codes = {c for c, spec in tdoc["codes"].items() if "marks" in spec}
  toks = tokenize.tokens([sample], tdoc.get("separators", ""), keep=keep)
  n_in = sum(len(t) for t in toks) or 1
  mapped = 0
  greek = 0
  out_len = 0
  coded = 0
  for tok in toks[:400]:
    w = dec.decode_word(tok)
    mapped += len(tok) - len(w.unmapped)
    if any(c in mark_codes for c in tok):
      coded += 1
    for ch in w.text:
      out_len += 1
      if is_greek_char(ch):
        greek += 1
  mapped_ratio = mapped / n_in
  greek_ratio = greek / out_len if out_len else 0.0
  code_token_ratio = coded / len(toks) if toks else 0.0
  return DetectionScore(
    table_id=table_id(tdoc),
    font=tdoc["font"],
    score=mapped_ratio * greek_ratio * min(1.0, code_token_ratio / 0.3),
    mapped_ratio=mapped_ratio,
    greek_ratio=greek_ratio,
    code_token_ratio=code_token_ratio,
  )


def detect_encoding(text: str, sample_chars: int = 4000) -> list[DetectionScore]:
  """Rank all known encodings against ``text``, best first."""
  sample = text[:sample_chars]
  scores = [
    _score(t, sample)
    for t in load_tables()
    if not t.get("cid_table")
  ]
  scores.sort(key=lambda s: -s.score)
  return scores


def decode_text(text: str, encoding: str | None = None) -> DecodedText:
  """Decode a legacy-encoded string to polytonic Unicode Greek.

  ``encoding``: a table id (see ``tables_by_id``). When omitted, the best
  detected encoding is used and the full ranking is attached to the result
  so the caller can inspect the decision.
  """
  detection: list[DetectionScore] | None = None
  if encoding is None:
    detection = detect_encoding(text)
    best = detection[0] if detection else None
    if best is None or best.score == 0.0 or best.code_token_ratio < 0.15:
      raise ValueError(
        "input does not look like legacy-encoded Greek: no (or almost no) "
        "diacritic key codes found — plain Latin-alphabet prose would be "
        "transliterated into pseudo-Greek, which this tool refuses to do. "
        "Pass encoding= explicitly if you are certain (see tables_by_id())."
      )
    encoding = best.table_id
  tdoc = tables_by_id().get(encoding)
  if tdoc is None:
    known = ", ".join(sorted(tables_by_id()))
    raise KeyError(f"unknown encoding {encoding!r}; known: {known}")

  dec = TableDecoder(tdoc)
  keep = frozenset(tdoc["letters"]) | frozenset(tdoc["codes"])
  code_chars = {c for c, spec in tdoc["codes"].items() if "marks" in spec}
  lines = tokenize.repair_lines(text.splitlines() or [text], code_chars)
  words: list[DecodedWord] = []
  out_lines: list[str] = []
  unmapped = 0
  for line in lines:
    parts: list[str] = []
    for tok in tokenize.tokens([line], tdoc.get("separators", ""), keep=keep):
      if any(is_greek_char(c) for c in tok):
        # already-Unicode Greek: pass through verbatim (NFC), never decode —
        # and never drop (red-team finding F2, 2026-08-03)
        seg = unicodedata.normalize("NFC", tok)
        w = DecodedWord(text=seg)
        w.records.append(CharRecord(output=seg, source=tok, mapped=True, confidence=1.0))
      else:
        w = dec.decode_word(tok)
      words.append(w)
      unmapped += len(w.unmapped)
      parts.append(w.text)
    out_lines.append(" ".join(x for x in parts if x).strip())
  mark_codes = {c for c, spec in tdoc["codes"].items() if "marks" in spec}
  legacy_words = [w for w in words if w.records and not is_greek_char(w.records[0].source[:1])]
  coded = sum(
    1 for w in legacy_words if any(c in mark_codes for r in w.records for c in r.source)
  )
  warning = None
  if legacy_words and coded / len(legacy_words) < 0.05:
    warning = (
      "almost no diacritic key codes in the input: this looks like plain "
      "Latin-alphabet text, and the output is most likely a transliteration "
      "artefact, not recovered Greek"
    )
  return DecodedText(
    text="\n".join(out_lines).strip(),
    table_id=encoding,
    words=words,
    unmapped_total=unmapped,
    detection=detection,
    warning=warning,
  )
