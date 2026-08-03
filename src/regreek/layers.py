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
from pdfminer.layout import LAParams, LTAnno, LTChar, LTTextLine

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
  """0-based index of the page in the PDF file — a file coordinate, NOT a
  citable locus."""
  width: float
  height: float
  bands: list[Band]
  printed_page: str | None = None
  """The page number as printed on the page itself (header or footer) — the
  number a scholarly citation must use. None when the page carries none
  (front matter) or none was detected."""

  def layer_text(self, layer: str) -> str:
    return "\n".join(b.text for b in self.bands if b.layer == layer)


def _decode_line(items: list) -> str:
  """Decode a line, applying the legacy table per font run.

  ``items`` are the LTTextLine children: LTChar glyphs AND LTAnno objects —
  pdfminer represents inter-word spaces it infers from positioning as LTAnno,
  so filtering to LTChar silently deletes every such space (real defect
  observed on several publishers: «Theverb'toeat'»). Whitespace, wherever it
  comes from, is preserved verbatim; only non-space chunks are decoded.
  """
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
      parts = re.split(r"(\s+)", seg)
      out.append("".join(
        p if (not p or p.isspace()) else dec.decode_word(p).text for p in parts
      ))
    else:
      out.append(seg)
    run, run_font = [], None

  for c in items:
    if isinstance(c, LTAnno):
      run.append(c.get_text())
      continue
    font = c.fontname
    if font != run_font:
      flush()
      run_font = font
    run.append(c.get_text())
  flush()
  return unicodedata.normalize("NFC", "".join(out))


def _iter_text_lines(el):
  """Recursively yield every LTTextLine, wherever it sits.

  Some publishers put the whole page in Form XObjects: pdfminer wraps those
  in LTFigure containers, so a flat scan over top-level LTTextContainer
  objects sees nothing (observed on a real edition). Combined with
  ``LAParams(all_texts=True)`` this recovers them.
  """
  if isinstance(el, LTTextLine):
    yield el
    return
  for child in getattr(el, "_objs", []) or []:
    yield from _iter_text_lines(child)


def _make_line(items: list, y0: float, y1: float, x0: float,
               x1: float) -> Line | None:
  chars = [c for c in items if isinstance(c, LTChar)]
  if not chars:
    return None
  text = "".join(c.get_text() for c in items).strip()
  if not text:
    return None
  sizes = Counter(round(c.size, 1) for c in chars)
  fonts = Counter(c.fontname.split("+")[-1] for c in chars)
  decoded = _decode_line(items)
  greek = sum(1 for ch in decoded if is_greek_char(ch))
  letters = sum(1 for ch in decoded if ch.isalpha()) or 1
  return Line(
    text=text,
    decoded=decoded,
    y0=y0, y1=y1, x0=x0, x1=x1,
    size=sizes.most_common(1)[0][0],
    fonts=dict(fonts),
    greek_ratio=greek / letters,
  )


def _merge_group_items(frags: list[tuple]) -> list:
  """Glyph-level merge of one physical line's fragments.

  pdfminer splits a justified line into several LTTextLines — and on some
  producers the split OVERLAPS: a bold run appears both at the end of the
  left fragment and at the head of the right one, at the same coordinates
  (observed: every bold lemma of a 2010 Distiller edition doubled, with
  displaced copies corrupting neighbouring entries). Glyphs are re-sorted
  by x, overlaid duplicates (same char within half a glyph) dropped, and
  inter-word spacing re-synthesized from the geometry — a wide gap becomes
  a double space, the entry-boundary idiom downstream splitting relies on.
  """
  chars = sorted(
    (c for _, _, _, _, items, _ in frags
     for c in items if isinstance(c, LTChar)),
    key=lambda c: (c.x0, -c.y0),
  )
  merged: list = []
  for c in chars:
    dup = False
    for prev in reversed(merged[-4:]):
      if isinstance(prev, LTAnno):
        continue
      # OVERLAID means near-identical position: real copies sit within
      # ~0.05pt, while a legitimate geminate (λλ, δδ, even "11") is a full
      # advance width apart — a loose threshold once ate every double
      # letter of the book
      if c.x0 - prev.x0 > 0.15 * max(c.size, 1.0):
        break
      if prev.get_text() == c.get_text() and abs(c.y0 - prev.y0) < 1.5:
        dup = True
        break
    if dup:
      continue
    if merged:
      last_char = next(
        (p for p in reversed(merged) if isinstance(p, LTChar)), None)
      if last_char is not None:
        gap = c.x0 - last_char.x1
        size = max(last_char.size, c.size, 1.0)
        if gap > 1.2 * size:
          merged.append(LTAnno("  "))
        elif gap > 0.18 * size:
          merged.append(LTAnno(" "))
    merged.append(c)
  return merged


def _lines_of(layout) -> list[Line]:
  frags: list[tuple] = []
  for el in layout:
    for tl in _iter_text_lines(el):
      items = [c for c in tl if isinstance(c, (LTChar, LTAnno))]
      chars = [c for c in items if isinstance(c, LTChar)]
      if not chars:
        continue
      if not "".join(c.get_text() for c in items).strip():
        continue
      size = Counter(round(c.size, 1) for c in chars).most_common(1)[0][0]
      frags.append((tl.y0, tl.y1, tl.x0, tl.x1, items, size))

  frags.sort(key=lambda f: (-f[0], f[2]))

  # group fragments of one physical line: vertical overlap AND horizontal
  # adjacency (a folio at the far end of the running-head line shares its
  # y but is a separate zone, never joined)
  groups: list[list[tuple]] = []
  for f in frags:
    if groups:
      g = groups[-1]
      gy0 = min(x[0] for x in g)
      gy1 = max(x[1] for x in g)
      gx1 = max(x[3] for x in g)
      overlap = min(gy1, f[1]) - max(gy0, f[0])
      span = min(gy1 - gy0, f[1] - f[0])
      x_gap = f[2] - gx1
      if span > 0 and overlap / span > 0.5 \
         and x_gap < 3 * max(f[5], g[0][5]):
        g.append(f)
        continue
    groups.append([f])

  lines: list[Line] = []
  for g in groups:
    if len(g) == 1:
      y0, y1, x0, x1, items, _ = g[0]
      ln = _make_line(items, y0, y1, x0, x1)
    else:
      items = _merge_group_items(g)
      ln = _make_line(
        items,
        min(x[0] for x in g), max(x[1] for x in g),
        min(x[2] for x in g), max(x[3] for x in g),
      )
    if ln is not None:
      lines.append(ln)
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

  # --- page number: printed folio, in the footer or the header ---------------
  # This is the number a scholarly citation must use (the PDF index is a file
  # coordinate, not a locus). Publishers set it isolated at the foot, or as a
  # short line in the header area.
  def _take_page_number(idx: int, where: str, why: str) -> None:
    ln = work.pop(idx)
    page.printed_page = ln.text.strip()
    page.bands.append(Band(
      layer="page_number", lines=[ln], evidence=f"digits-only {where} line, {why}",
      confidence=0.95,
    ))

  if len(work) >= 2 and _DIGITS_ONLY.match(work[-1].text) \
      and (work[-2].y0 - work[-1].y0) > 1.6 * pitch:
    _take_page_number(len(work) - 1, "bottom", "isolated by >1.6x pitch")
  else:
    # header folios: a short digits-only line among the topmost lines, above
    # the body (publishers set the folio beside or under the running head)
    for idx in range(min(3, len(work) - 1)):
      ln = work[idx]
      if _DIGITS_ONLY.match(ln.text) and len(ln.text) <= 6 \
          and ln.y0 > 0.85 * layout.height:
        _take_page_number(idx, "header", "short, in the top page band")
        break

  # --- running head: top line, isolated, no sentence content -----------------
  # A running head never ENDS a sentence: a short final line of a section
  # (one line of text above the apparatus band, observed) is isolated and
  # short too, but its terminal punctuation betrays it.
  if len(work) >= 2 and (work[0].y0 - work[1].y0) > 1.6 * pitch \
      and len(work[0].text) < 70 \
      and not work[0].text.rstrip().endswith((".", ";", "·", "!", "?")):
    page.bands.insert(0, Band(
      layer="running_head", lines=[work.pop(0)],
      evidence="top line isolated by >1.6x pitch, short",
      confidence=0.9,
    ))

  if not work:
    return page

  # --- main/apparatus boundary ----------------------------------------------
  # The apparatus opens at the first big vertical gap after which the size
  # register drops below the modal size OF THE LINES ABOVE the gap and
  # stays low. The reference register must come from the candidate main
  # band, not the whole page: on an apparatus-dominant page (more band
  # lines than text lines — real in dense editions) the page-wide mode IS
  # the apparatus size and a page-wide comparison never fires.
  # Among valid candidates (big gap + durable size drop below the register
  # of the lines ABOVE the gap), the LAST one with a substantial foot wins:
  # an early heading gap must not preempt the real text/foot boundary, and
  # a one-line printer's footer below the apparatus must not claim the cut
  # and leave the whole apparatus fused into the text (both observed).
  split = None
  split_small = None
  for i in range(1, len(work)):
    gap = work[i - 1].y0 - work[i].y0
    if gap <= 1.7 * pitch:
      continue
    upper_size = Counter(ln.size for ln in work[:i]).most_common(1)[0][0]
    rest = work[i:]
    if work[i].size < upper_size - 0.5 and \
       sum(1 for ln in rest if ln.size < upper_size - 0.5) >= 0.7 * len(rest):
      if len(rest) >= 3:
        split = i
      else:
        split_small = i
  if split is None:
    split = split_small

  main, foot = (work, []) if split is None else (work[:split], work[split:])
  body_size = Counter(ln.size for ln in main).most_common(1)[0][0]

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
  # SORTED is load-bearing: pdfminer yields pages in DOCUMENT order
  # regardless of the requested order, so pairing the yield sequence with
  # an unsorted request would silently label one page's content with
  # another page's index.
  numbers = sorted(set(pages)) if pages is not None else None
  for i, layout in enumerate(extract_pages(
      str(pdf_path), page_numbers=numbers, laparams=LAParams(all_texts=True))):
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
