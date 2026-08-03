"""Table-driven decoder: legacy keystroke stream -> polytonic Unicode Greek.

The decoding model, established empirically on real critical-edition PDFs:

- ``letters`` map a legacy char to a Greek base letter (case preserved).
- ``codes`` map a legacy char to combining marks or a literal character.
  Marks attach to the nearest *preceding* vowel (rho allowed for breathings);
  if no preceding letter can carry them, they queue for the *next* letter
  (word-initial breathings before capitals).
- ``final_letter`` codes act as a letter only at word end (Odyssea ``"``).
- ``final_punct`` codes are an accent normally, but plain punctuation at word
  end when the word is already accented or the previous char is not a vowel
  (Bwgrkl ``.`` = grave / full stop, ``,`` = acute / comma).
- ``final_apostrophe`` codes decode to an elision apostrophe at word end
  after a consonant (Bwgrkl ``v``/``V``, GrecMonotype lone-breathing glyph).

Unmapped characters are preserved verbatim and reported: this module never
invents a mapping.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

VOWELS = "αεηιουω"
_BREATHINGS = "̓̔"
_ACCENTS = "́̀͂"

GREEK_RANGES: tuple[tuple[str, str], ...] = (
  ("Ͱ", "Ͽ"),  # Greek and Coptic
  ("ἀ", "῿"),  # Greek Extended
)


def is_greek_char(ch: str) -> bool:
  return any(lo <= ch <= hi for lo, hi in GREEK_RANGES)


def _base(ch: str) -> str:
  return unicodedata.normalize("NFD", ch)[:1].lower()


@dataclass
class CharRecord:
  """Provenance of one output segment."""

  output: str
  source: str
  mapped: bool
  confidence: float


@dataclass
class DecodedWord:
  text: str
  unmapped: list[str] = field(default_factory=list)
  records: list[CharRecord] = field(default_factory=list)

  @property
  def fully_mapped(self) -> bool:
    return not self.unmapped


class TableDecoder:
  """Decode legacy-encoded tokens using one font table."""

  def __init__(self, table: dict) -> None:
    self.letters: dict[str, str] = table["letters"]
    self.codes: dict[str, dict] = table["codes"]
    self.confidence: dict[str, float] = table.get("confidence", {})

  def _conf(self, ch: str) -> float:
    return float(self.confidence.get(ch, 0.9))

  def decode_word(self, tok: str) -> DecodedWord:
    # unit: [text, marks, is_letter, sources, mapped, confidence]
    units: list[list] = []
    pending: list[str] = []
    pending_src: list[str] = []
    result = DecodedWord(text="")

    def attach(marks: list[str], src: str) -> None:
      breathing_only = all(m in _BREATHINGS for m in marks)
      target = None
      for u in reversed(units):
        if not u[2]:
          continue
        lo = _base(u[0])
        if lo in VOWELS or (breathing_only and lo == "ρ"):
          target = u
          break
      if target is not None:
        for m in marks:
          if m not in target[1]:
            target[1].append(m)
        target[3].append(src)
        target[5] = min(target[5], self._conf(src))
      else:
        pending.extend(marks)
        pending_src.append(src)

    n = len(tok)
    for i, ch in enumerate(tok):
      if ch in self.letters:
        units.append(
          [self.letters[ch], list(pending), True, [ch, *pending_src], True, self._conf(ch)]
        )
        pending, pending_src = [], []
        continue
      if ch in self.codes:
        spec = self.codes[ch]
        last = i == n - 1
        if "final_letter" in spec:
          if last:
            units.append(
              [spec["final_letter"], list(pending), True, [ch, *pending_src], True, self._conf(ch)]
            )
            pending, pending_src = [], []
          # mid-word: positioning variant glyph, no textual content
          continue
        if spec.get("final_apostrophe") and last and units and units[-1][2] \
            and _base(units[-1][0]) not in VOWELS:
          units.append(["’", [], False, [ch], True, self._conf(ch)])
          continue
        if "final_punct" in spec and last:
          prev_vowel = bool(units) and units[-1][2] and _base(units[-1][0]) in VOWELS
          accented = any(m in _ACCENTS for u in units for m in u[1])
          if not prev_vowel or accented:
            units.append([spec["final_punct"], [], False, [ch], True, self._conf(ch)])
            continue
        if "char" in spec:
          units.append([spec["char"], [], False, [ch], True, self._conf(ch)])
        else:
          attach(list(spec["marks"]), ch)
        continue
      # unmapped: preserve verbatim, flag
      units.append([ch, [], False, [ch], False, 0.0])
      result.unmapped.append(ch)

    if pending:
      # orphan marks with no letter to carry them: preserve, flag
      units.append(["".join(pending), [], False, list(pending_src), False, 0.0])
      result.unmapped.extend(pending_src)

    out_parts: list[str] = []
    for u in units:
      seg = unicodedata.normalize("NFC", u[0] + "".join(u[1]))
      out_parts.append(seg)
      result.records.append(
        CharRecord(output=seg, source="".join(u[3]), mapped=u[4], confidence=u[5])
      )
    text = unicodedata.normalize("NFC", "".join(out_parts))
    result.text = _final_sigma(text)
    return result


def _final_sigma(word: str) -> str:
  """Word-final medial sigma -> final sigma (never legitimate word-finally)."""
  stripped = word.rstrip("’·.,;·")
  if stripped.endswith("σ"):
    k = len(stripped)
    return word[: k - 1] + "ς" + word[k:]
  return word
