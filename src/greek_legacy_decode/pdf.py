"""PDF extraction layer (pdfminer.six, MIT).

Produces per-page, per-line runs of text attributed to embedded fonts, then
decodes runs set in known legacy Greek fonts. Fonts without a ToUnicode CMap
(e.g. SPIonic subsets) are read at CID level: pdfminer yields ``(cid:N)``
strings which are converted to ``chr(N)`` to match CID-level tables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTTextContainer, LTTextLine

from . import tokenize
from .decoder import DecodedWord, TableDecoder, is_greek_char
from .registry import decoder_for_font, strip_subset_prefix, table_for_font

_CID_RE = re.compile(r"\(cid:(\d+)\)")

_PUA_OFFSET = 0xE000


@dataclass
class Run:
  """Consecutive same-font characters within one visual line."""

  font: str
  text: str


@dataclass
class PageText:
  page: int
  lines: list[list[Run]] = field(default_factory=list)


def _char_text(ch: LTChar) -> str:
  t = ch.get_text()
  m = _CID_RE.fullmatch(t)
  if m:
    return chr(int(m.group(1)))
  return t


def extract_runs(pdf_path: str | Path, pages: list[int] | None = None) -> list[PageText]:
  """Extract per-line font-attributed runs from a PDF."""
  page_numbers = pages if pages is not None else None
  out: list[PageText] = []
  laparams = LAParams()
  for pno, layout in enumerate(extract_pages(str(pdf_path), page_numbers=page_numbers,
                                             laparams=laparams)):
    page = PageText(page=page_numbers[pno] if page_numbers else pno)
    for element in layout:
      if not isinstance(element, LTTextContainer):
        continue
      for line in element:
        if not isinstance(line, LTTextLine):
          continue
        runs: list[Run] = []
        for ch in line:
          if not isinstance(ch, LTChar):
            continue
          font = strip_subset_prefix(ch.fontname or "")
          text = _char_text(ch)
          if runs and runs[-1].font == font:
            runs[-1].text += text
          else:
            runs.append(Run(font=font, text=text))
        if runs:
          page.lines.append(runs)
    out.append(page)
  return out


def _companion_transform(tdoc: dict, font: str, text: str) -> str:
  """Two-font schemes (GrecMonotype + GrecAcc*): map accent-font chars to PUA."""
  companion = tdoc.get("companion")
  if not companion:
    return text
  if any(font.startswith(p) for p in companion["accent_font_prefixes"]):
    off = companion.get("pua_offset", _PUA_OFFSET)
    return "".join(chr(off + ord(c)) if not c.isspace() else c for c in text)
  return text


@dataclass
class DecodedToken:
  token: str
  word: DecodedWord
  font: str


@dataclass
class DecodedPage:
  page: int
  tokens: list[DecodedToken] = field(default_factory=list)

  @property
  def text(self) -> str:
    return " ".join(t.word.text for t in self.tokens)


def decode_page(page: PageText) -> DecodedPage:
  """Decode all legacy-font runs on a page, honestly flagging what is unmapped."""
  result = DecodedPage(page=page.page)
  # group by table: each legacy family is assembled and tokenized separately
  by_table: dict[str, tuple[dict, TableDecoder, list[str]]] = {}
  for line_runs in page.lines:
    per_family: dict[str, list[str]] = {}
    for run in line_runs:
      tdoc = table_for_font(run.font)
      if tdoc is None:
        for fam_buf in per_family.values():
          fam_buf.append(" ")
        continue
      fam = tdoc["font"]
      if fam not in by_table:
        by_table[fam] = (tdoc, TableDecoder(tdoc), [])
      buf = per_family.setdefault(fam, [])
      buf.append(_companion_transform(tdoc, run.font, run.text))
    for fam, buf in per_family.items():
      line_text = "".join(buf).strip()
      if line_text:
        by_table[fam][2].append(line_text)
  for _fam, (tdoc, dec, lines) in by_table.items():
    code_chars = {c for c, spec in tdoc["codes"].items() if "marks" in spec}
    repaired = tokenize.repair_lines(lines, code_chars)
    keep = frozenset(tdoc["letters"]) | frozenset(tdoc["codes"])
    for tok in tokenize.tokens(repaired, tdoc.get("separators", ""), keep=keep):
      result.tokens.append(DecodedToken(token=tok, word=dec.decode_word(tok), font=tdoc["font"]))
  return result


def legacy_fonts_in_pdf(pdf_path: str | Path, max_pages: int = 20) -> dict[str, int]:
  """Known legacy fonts present in the first ``max_pages`` pages, with char counts."""
  counts: dict[str, int] = {}
  for page in extract_runs(pdf_path, pages=list(range(max_pages))):
    for line in page.lines:
      for run in line:
        if decoder_for_font(run.font) is not None:
          counts[run.font] = counts.get(run.font, 0) + len(run.text)
  return counts


def validate_greek(text: str) -> tuple[int, int]:
  """(greek_letters, non_greek_letters) over alphabetic output characters."""
  greek = other = 0
  for c in text:
    if not c.isalpha():
      continue
    if is_greek_char(c):
      greek += 1
    else:
      other += 1
  return greek, other
