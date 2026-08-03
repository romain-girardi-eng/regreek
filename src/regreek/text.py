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

from dataclasses import dataclass

from . import tokenize
from .decoder import DecodedWord, TableDecoder, is_greek_char
from .registry import load_tables


@dataclass
class DetectionScore:
  table_id: str
  font: str
  score: float
  mapped_ratio: float
  greek_ratio: float


@dataclass
class DecodedText:
  text: str
  table_id: str
  words: list[DecodedWord]
  unmapped_total: int
  detection: list[DetectionScore] | None = None

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
  toks = tokenize.tokens([sample], tdoc.get("separators", ""), keep=keep)
  n_in = sum(len(t) for t in toks) or 1
  mapped = 0
  greek = 0
  out_len = 0
  for tok in toks[:400]:
    w = dec.decode_word(tok)
    mapped += len(tok) - len(w.unmapped)
    for ch in w.text:
      out_len += 1
      if is_greek_char(ch):
        greek += 1
  mapped_ratio = mapped / n_in
  greek_ratio = greek / out_len if out_len else 0.0
  return DetectionScore(
    table_id=table_id(tdoc),
    font=tdoc["font"],
    score=mapped_ratio * greek_ratio,
    mapped_ratio=mapped_ratio,
    greek_ratio=greek_ratio,
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
    if not detection or detection[0].score == 0.0:
      raise ValueError(
        "could not detect a legacy Greek encoding in this text; "
        "pass encoding= explicitly (see tables_by_id())"
      )
    encoding = detection[0].table_id
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
      w = dec.decode_word(tok)
      words.append(w)
      unmapped += len(w.unmapped)
      parts.append(w.text)
    out_lines.append(" ".join(x for x in parts if x).strip())
  return DecodedText(
    text="\n".join(out_lines).strip(),
    table_id=encoding,
    words=words,
    unmapped_total=unmapped,
    detection=detection,
  )
