"""Layer separation for critical-edition pages.

A critical edition co-registers several information layers on one page: the
constituted text, the apparatus criticus at the foot, running heads, page
numbers, section headings, a facing-page translation, and inline witness
references. Feeding a flat dump of all of them to a search engine or a
language model invites the worst scholarly failure mode: an apparatus variant
quoted as the constituted text.

This module separates the layers **deterministically**, from geometry and
typography alone — font-size registers, vertical gaps, script signatures —
never from content understanding, and it never reorders or merges lines.
Anything it cannot classify with evidence is labelled ``unknown`` rather than
guessed; the evidence for each band's label travels with the band.

Empirical grounding (measured, not assumed — see the project FINDINGS):
in a representative bilingual edition the Greek text sits in a 10 pt register,
the facing French translation in 11 pt, the apparatus in 8-9 pt at the foot
after a vertical gap of ~2.4x the body pitch, the running head is isolated at
the top, and the page number is a short digit-only line at the bottom.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTTextContainer, LTTextLine

from .decoder import is_greek_char
from .registry import decoder_for_font, known_legacy_font

# an inline witness/locus reference, as typeset inside text lines:
# [fol. 94 v° : A]  [p. 261 : B]  [PG VI, 497]
_INLINE_REF = re.compile(
  r"\[(?:fol\.|p\.|col\.|PG|PL)\s?[^\]]{0,30}\]"
)
_DIGITS_ONLY = re.compile(r"^(?=.*[\divxlc])[\divxlcIVXLC .\-–]+$")


@dataclass
class Line:
  """One visual line with the typographic facts the classifier uses."""

  text: str
  decoded: str
  y0: float
  y1: float
  x0: float
  x1: float
  size: float
  fonts: dict[str, int]
  greek_ratio: float

  @property
  def width(self) -> float:
    return self.x1 - self.x0


@dataclass
class Band:
  """A vertical band of consecutive lines sharing one layer label."""

  layer: str
  lines: list[Line]
  evidence: str
  confidence: float
  inline_refs: list[str] = field(default_factory=list)

  @property
  def text(self) -> str:
    return "\n".join(ln.decoded or ln.text for ln in self.lines)

  @property
  def bbox(self) -> tuple[float, float, float, float]:
    return (
      min(ln.x0 for ln in self.lines),
      min(ln.y0 for ln in self.lines),
      max(ln.x1 for ln in self.lines),
      max(ln.y1 for ln in self.lines),
    )


@dataclass
class LayeredPage:
  page: int
  width: float
  height: float
  bands: list[Band]

  def layer_text(self, layer: str) -> str:
    return "\n".join(b.text for b in self.bands if b.layer == layer)


def _decode_line(chars: list[LTChar]) -> str:
  """Decode a line's characters, applying the legacy table per font run."""
  out: list[str] = []
  run: list[str] = []
  run_font: str | None = None

  def flush() -> None:
    nonlocal run, run_font
    if not run:
      return
    seg = "".join(run)
    dec = decoder_for_font(run_font) if run_font else None
    if dec is not None:
      out.append(" ".join(dec.decode_word(t).text for t in seg.split()))
    else:
      out.append(seg)
    run, run_font = [], None

  for c in chars:
    font = c.fontname
    if font != run_font:
      flush()
      run_font = font
    run.append(c.get_text())
  flush()
  return unicodedata.normalize("NFC", "".join(out))


def _lines_of(layout) -> list[Line]:
  lines: list[Line] = []
  for el in layout:
    if not isinstance(el, LTTextContainer):
      continue
    for tl in el:
      if not isinstance(tl, LTTextLine):
        continue
      chars = [c for c in tl if isinstance(c, LTChar)]
      if not chars:
        continue
      text = "".join(c.get_text() for c in chars).strip()
      if not text:
        continue
      sizes = Counter(round(c.size, 1) for c in chars)
      fonts = Counter(c.fontname.split("+")[-1] for c in chars)
      decoded = _decode_line(chars)
      greek = sum(1 for ch in decoded if is_greek_char(ch))
      letters = sum(1 for ch in decoded if ch.isalpha()) or 1
      lines.append(Line(
        text=text,
        decoded=decoded,
        y0=tl.y0, y1=tl.y1, x0=tl.x0, x1=tl.x1,
        size=sizes.most_common(1)[0][0],
        fonts=dict(fonts),
        greek_ratio=greek / letters,
      ))
  lines.sort(key=lambda ln: -ln.y0)
  return lines


def _pitch(lines: list[Line]) -> float:
  """Modal baseline-to-baseline distance of the page's body."""
  deltas = [
    round(a.y0 - b.y0, 0)
    for a, b in zip(lines, lines[1:], strict=False)
    if 0 < a.y0 - b.y0 < 40
  ]
  if not deltas:
    return 12.0
  return float(Counter(deltas).most_common(1)[0][0]) or 12.0


def _is_greek_band(lines: list[Line]) -> bool:
  greek = sum(ln.greek_ratio * max(len(ln.decoded), 1) for ln in lines)
  total = sum(max(len(ln.decoded), 1) for ln in lines)
  return greek / total > 0.5


def classify_page(layout, page_number: int) -> LayeredPage:
  lines = _lines_of(layout)
  page = LayeredPage(
    page=page_number, width=layout.width, height=layout.height, bands=[],
  )
  if not lines:
    return page

  pitch = _pitch(lines)
  work = list(lines)

  # --- page number: bottom line, digits only, isolated -----------------------
  if len(work) >= 2 and _DIGITS_ONLY.match(work[-1].text) \
      and (work[-2].y0 - work[-1].y0) > 1.6 * pitch:
    page.bands.append(Band(
      layer="page_number", lines=[work.pop()],
      evidence=f"digits-only bottom line isolated by >{1.6:.1f}x pitch",
      confidence=0.95,
    ))

  # --- running head: top line, isolated, no sentence content -----------------
  if len(work) >= 2 and (work[0].y0 - work[1].y0) > 1.6 * pitch \
      and len(work[0].text) < 70:
    page.bands.insert(0, Band(
      layer="running_head", lines=[work.pop(0)],
      evidence="top line isolated by >1.6x pitch, short",
      confidence=0.9,
    ))

  if not work:
    return page

  # --- main/apparatus boundary ----------------------------------------------
  # The apparatus opens at the first big vertical gap after which the size
  # register drops below the modal body size and stays low.
  body_size = Counter(ln.size for ln in work).most_common(1)[0][0]
  split = None
  for i in range(1, len(work)):
    gap = work[i - 1].y0 - work[i].y0
    if gap > 1.7 * pitch and work[i].size < body_size - 0.5:
      rest = work[i:]
      if sum(1 for ln in rest if ln.size < body_size - 0.5) >= 0.7 * len(rest):
        split = i
        break

  main, foot = (work, []) if split is None else (work[:split], work[split:])

  # --- headings inside the main band: centered, narrow lines -----------------
  def is_centered(ln: Line) -> bool:
    left = ln.x0 - min(x.x0 for x in main)
    right = max(x.x1 for x in main) - ln.x1
    span = max(x.x1 for x in main) - min(x.x0 for x in main)
    return left > 0.12 * span and right > 0.12 * span

  # A heading must differ from the body typographically (font family or
  # size), not merely be centred: short final lines of Greek paragraphs are
  # frequently centred-ish, and misfiling them would drop constituted text
  # from the greek_text layer (red-team finding, 2026-08-03).
  body_font = Counter(
    f for ln in main for f, n in ln.fonts.items() for _ in range(n)
  ).most_common(1)[0][0] if main else ""

  def differs_typographically(ln: Line) -> bool:
    dom = Counter(
      f for f, n in ln.fonts.items() for _ in range(n)
    ).most_common(1)[0][0]
    return dom != body_font or ln.size != body_size

  segments: list[tuple[str, list[Line], str, float]] = []
  cur: list[Line] = []
  cur_head: list[Line] = []
  for ln in main:
    if is_centered(ln) and differs_typographically(ln) and not _DIGITS_ONLY.match(ln.text):
      if cur:
        segments.append(("body", cur, "", 0.0))
        cur = []
      cur_head.append(ln)
    else:
      if cur_head:
        segments.append((
          "heading", cur_head,
          "centered, and typographically distinct from the body (font family or size)", 0.85,
        ))
        cur_head = []
      cur.append(ln)
  if cur_head:
    segments.append(("heading", cur_head, "centered narrow line(s)", 0.85))
  if cur:
    segments.append(("body", cur, "", 0.0))

  for kind, seg, ev, conf in segments:
    if kind == "heading":
      page.bands.append(Band(layer="heading", lines=seg, evidence=ev, confidence=conf))
      continue
    greek = _is_greek_band(seg)
    layer = "greek_text" if greek else "translation"
    refs: list[str] = []
    for ln in seg:
      refs.extend(_INLINE_REF.findall(ln.decoded))
    page.bands.append(Band(
      layer=layer, lines=seg,
      evidence=(
        f"body register {body_size:g}pt; "
        + ("Greek-script majority" if greek else "Latin-script majority")
      ),
      confidence=0.9,
      inline_refs=refs,
    ))

  if foot:
    sizes = sorted({ln.size for ln in foot})
    # On a Greek text page the foot band is the apparatus; on a translation
    # page it holds the apparatus fontium / translator's notes. The label
    # follows the page context — content is never inspected.
    main_is_greek = any(b.layer == "greek_text" for b in page.bands)
    page.bands.append(Band(
      layer="apparatus" if main_is_greek else "notes", lines=foot,
      evidence=(
        f"foot band after a >1.7x-pitch gap, size register {sizes} "
        f"below body {body_size:g}pt; page context: "
        + ("greek_text" if main_is_greek else "translation")
      ),
      confidence=0.9,
    ))

  return page


def layer_pages(pdf_path: str | Path, pages: list[int] | None = None) -> list[LayeredPage]:
  """Classify every requested page of a PDF into layers."""
  out: list[LayeredPage] = []
  numbers = pages
  for i, layout in enumerate(extract_pages(str(pdf_path), page_numbers=numbers)):
    page_no = numbers[i] if numbers is not None else i
    out.append(classify_page(layout, page_no))
  return out


def has_legacy_greek(page: LayeredPage) -> bool:
  return any(
    known_legacy_font(f)
    for band in page.bands
    for ln in band.lines
    for f in ln.fonts
  )
