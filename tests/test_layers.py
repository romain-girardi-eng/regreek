"""Layer classification tests on synthetic geometry.

The fixtures reproduce the measured layout of a bilingual critical edition
(10 pt Greek body / 11 pt translation body, 8-9 pt apparatus after a wide
gap, isolated running head and page number) with dummy text, so no
copyrighted material is embedded.
"""

from __future__ import annotations

import pytest

from regreek.layers import Band, Line, classify_page  # noqa: F401


class FakeChar:
  def __init__(self, ch: str, font: str, size: float, x: float, y: float):
    self._ch, self.fontname, self.size = ch, font, size
    self.x0, self.x1 = x, x + size * 0.5
    self.y0, self.y1 = y, y + size

  def get_text(self) -> str:
    return self._ch


class FakeLine:
  def __init__(self, text: str, font: str, size: float, y: float, x0: float = 133.0,
               runs: list[tuple[str, str]] | None = None):
    """``runs``: optional [(text, font)] segments for mixed-font lines."""
    self._chars = []
    x = x0
    for seg, seg_font in (runs or [(text, font)]):
      for ch in seg:
        self._chars.append(FakeChar(ch, seg_font, size, x, y))
        x += size * 0.5
    self.x0, self.x1 = x0, x
    self.y0, self.y1 = y, y + size

  def __iter__(self):
    return iter(self._chars)


class FakeContainer:
  def __init__(self, lines):
    self._lines = lines
    self._objs = lines  # mirrors pdfminer: children live in _objs

  def __iter__(self):
    return iter(self._lines)


class FakeLayout:
  width, height = 595.0, 842.0

  def __init__(self, lines):
    self._containers = [FakeContainer(lines)]

  def __iter__(self):
    return iter(self._containers)


import regreek.layers as L  # noqa: E402

# make the fake duck-types pass isinstance checks
L.LTChar = FakeChar
L.LTTextLine = FakeLine
L.LTTextContainer = FakeContainer


def greek_page() -> FakeLayout:
  lines = [FakeLine("AUTHOR NAME", "Garamond", 9.0, 661.0, x0=262.0)]
  y = 626.0
  for _ in range(12):
    lines.append(FakeLine("kai; ejn toi'\" lovgoi\" aujtou'", "GFDJFH+Graeca", 10.0, y))
    y -= 12.0
  y -= 17.0  # wide gap before apparatus
  for _ in range(4):
    lines.append(FakeLine("3 kai; : om. codd. prop. Otto", "Garamond", 8.0, y))
    y -= 10.0
  lines.append(FakeLine("294", "TimesNewRoman", 10.0, 141.0, x0=290.0))
  return FakeLayout(lines)


def translation_page() -> FakeLayout:
  lines = [FakeLine("TITLE, 44, 4", "Garamond", 9.0, 661.0, x0=211.0)]
  y = 625.0
  for _ in range(4):
    lines.append(FakeLine(
      "Ainsi donc il faut retrancher cette esperance de vos ames et", "Garamond", 11.0, y))
    y -= 12.0
  lines.append(FakeLine("Les Justes avant la Loi", "Garamond-Italic", 11.0, y - 14.0, x0=199.0))
  y -= 40.0
  for _ in range(6):
    lines.append(FakeLine(
      "Il repondit que la resurrection des morts adviendra pour tous", "Garamond", 11.0, y))
    y -= 12.0
  y -= 19.0
  lines.append(FakeLine("a Cf. Is. 1, 16   b cf. Is. 55, 7", "Garamond", 9.0, y))
  lines.append(FakeLine("295", "TimesNewRoman", 10.0, 141.0, x0=290.0))
  return FakeLayout(lines)


def layers_of(page) -> dict[str, Band]:
  return {b.layer: b for b in page.bands}


def test_greek_page_layers() -> None:
  page = classify_page(greek_page(), 300)
  got = layers_of(page)
  assert set(got) == {"running_head", "greek_text", "apparatus", "page_number"}
  assert len(got["greek_text"].lines) == 12
  assert len(got["apparatus"].lines) == 4
  # apparatus must never contaminate the Greek text layer
  assert "Otto" not in got["greek_text"].text
  assert "Otto" in got["apparatus"].text
  # the Greek came out decoded
  assert "καὶ ἐν τοῖς λόγοις αὐτοῦ" in got["greek_text"].text


def test_translation_page_layers() -> None:
  page = classify_page(translation_page(), 301)
  got = layers_of(page)
  assert set(got) == {"running_head", "translation", "heading", "notes", "page_number"}
  assert "Les Justes" in got["heading"].text
  # foot band on a translation page is 'notes', not 'apparatus'
  assert "Cf. Is." in got["notes"].text


def test_evidence_travels_with_bands() -> None:
  page = classify_page(greek_page(), 300)
  for band in page.bands:
    assert band.evidence
    assert 0.0 < band.confidence <= 1.0


def test_inline_refs_extracted() -> None:
  lines = [FakeLine("AUTHOR NAME", "Garamond", 9.0, 661.0, x0=262.0)]
  y = 626.0
  for i in range(6):
    if i == 2:
      # the witness reference is typeset in the Latin font, as in real editions
      lines.append(FakeLine("", "GFDJFH+Graeca", 10.0, y, runs=[
        ("lovgo\" ", "GFDJFH+Graeca"),
        ("[fol. 94 v° : A] ", "Garamond"),
        ("kaiv", "GFDJFH+Graeca"),
      ]))
    else:
      lines.append(FakeLine("kai; oJ lovgo\" ejstivn", "GFDJFH+Graeca", 10.0, y))
    y -= 12.0
  lines.append(FakeLine("100", "TimesNewRoman", 10.0, 141.0, x0=290.0))
  page = classify_page(FakeLayout(lines), 1)
  got = layers_of(page)
  assert any("fol. 94" in r for r in got["greek_text"].inline_refs)


def test_centered_same_face_lines_stay_body() -> None:
  """F4 (red-team): short centred Greek lines in the SAME face and size as
  the body are constituted text, not headings."""
  lines = [FakeLine("AUTHOR NAME", "Garamond", 9.0, 661.0, x0=262.0)]
  y = 626.0
  for i in range(8):
    if i == 4:
      lines.append(FakeLine("kai; ta; a[lla", "GFDJFH+Graeca", 10.0, y, x0=250.0))
    else:
      lines.append(FakeLine("kai; oJ lovgo\" ejsti;n ajlhqh;" + "\"", "GFDJFH+Graeca", 10.0, y))
    y -= 12.0
  lines.append(FakeLine("294", "TimesNewRoman", 10.0, 141.0, x0=290.0))
  page = classify_page(FakeLayout(lines), 1)
  assert all(b.layer != "heading" for b in page.bands)
  greek = [b for b in page.bands if b.layer == "greek_text"]
  assert greek and len(greek[0].lines) == 8


def test_dot_leader_is_not_a_page_number() -> None:
  """F6 (red-team): a dotted leader line must not match digits-only."""
  lines = [FakeLine("AUTHOR NAME", "Garamond", 9.0, 661.0, x0=262.0)]
  y = 626.0
  for _ in range(6):
    lines.append(FakeLine("kai; oJ lovgo\" ejsti;n ajlhqhv\"", "GFDJFH+Graeca", 10.0, y))
    y -= 12.0
  lines.append(FakeLine(". . . . .", "Garamond", 10.0, 141.0, x0=200.0))
  page = classify_page(FakeLayout(lines), 1)
  assert all(b.layer != "page_number" for b in page.bands)


def test_printed_page_is_the_citable_folio() -> None:
  """The printed folio (footer or header) is what a citation must use — the
  PDF index is a file coordinate. Both placements are captured."""
  page = classify_page(greek_page(), 300)
  assert page.printed_page == "294"
  assert page.page == 300
  # header folio: short digits line near the top, after a title line
  lines = [
    FakeLine("JOURNAL TITLE", "Garamond", 9.0, 790.0, x0=200.0),
    FakeLine("225", "Garamond", 9.0, 789.0, x0=420.0),
  ]
  y = 750.0
  for _ in range(8):
    lines.append(FakeLine(
      "Il repondit que la resurrection des morts adviendra", "Garamond", 11.0, y))
    y -= 12.0
  pg = classify_page(FakeLayout(lines), 8)
  assert pg.printed_page == "225"



def test_fragments_of_one_physical_line_rejoin_in_x_order() -> None:
  # pdfminer splits a justified line when superscripts change the box
  # height; the fragments must rejoin in x order, not y-sort order
  page = FakeLayout([
    FakeLine("πρῶτος στίχος τῆς σελίδος ὧδε κεῖται καὶ ἄλλα", "GreekF", 10.0, 700),
    FakeLine("τέλος πρώτης1 προτάσεως", "GreekF", 10.0, 686, x0=178.0),
    FakeLine("ἀρχὴ τῆς", "GreekF", 10.0, 686.4, x0=133.0),
    FakeLine("τρίτος στίχος τοῦ σώματος μετὰ τούτων τῶν λέξεων", "GreekF", 10.0, 672),
    FakeLine("τέταρτος στίχος τοῦ σώματος ἵνα τὸ σῶμα κρατῇ", "GreekF", 10.0, 658),
  ])
  lp = classify_page(page, 0)
  body = lp.layer_text("greek_text")
  assert "ἀρχὴ τῆς τέλος πρώτης1 προτάσεως" in body


def test_one_line_section_end_is_not_a_running_head() -> None:
  # a single text line above the apparatus band, isolated and short, ends
  # with sentence punctuation: it is TEXT — a running head never does
  page = FakeLayout([
    FakeLine("τοῦτο τὸ τέλος τοῦ κεφαλαίου ἐστίν2.", "GreekF", 10.0, 700),
    FakeLine("1 Τέλος A : τέλη B", "GreekApp", 8.5, 640),
    FakeLine("2 Ἐστίν A : ἔστιν B", "GreekApp", 8.5, 628),
  ])
  lp = classify_page(page, 0)
  layers = [b.layer for b in lp.bands]
  assert "running_head" not in layers
  assert "greek_text" in layers


def test_rotated_watermark_never_merges_into_lines() -> None:
  """A diagonal watermark ("DRAFT" at 45 degrees across the page) is set
  in rotated glyphs; merging them into the horizontal lines they overlap
  would splice stray capitals into real words."""
  page = translation_page()
  wm = FakeLine("D", "Garamond", 150.0, 400.0, x0=180.0)
  for c in wm:
    c.matrix = (0.71, 0.71, -0.71, 0.71, 180.0, 400.0)
  page._containers[0]._lines.insert(3, wm)
  lp = classify_page(page, 0)
  joined = " ".join(ln.text for b in lp.bands for ln in b.lines)
  assert "D " not in joined.replace("Donc", "")  # no spliced capital
  assert all(w != "D" for w in joined.split())


def test_corner_crop_marks_dropped_short_continuation_kept() -> None:
  """The "i" registration marks of LaTeX's crop package live in the page
  CORNERS (edge band horizontally AND vertically); a 2-letter apparatus
  continuation line ("Uc") shares the column's x-origin mid-page and
  must survive."""
  page = greek_page()
  lines = page._containers[0]._lines
  # corner furniture: horizontal edge band + vertical edge band
  lines.append(FakeLine("i", "Garamond", 10.0, 830.0, x0=24.0))
  lines.append(FakeLine("i", "Garamond", 10.0, 6.0, x0=24.0))
  # a short alphabetic continuation of the apparatus, column-aligned,
  # mid-page: NOT furniture even though it ends inside x<72 territory
  lines.append(FakeLine("Uc", "Garamond", 8.0, 448.0, x0=50.0))
  lp = classify_page(page, 0)
  joined = " ".join(ln.text for b in lp.bands for ln in b.lines)
  assert "Uc" in joined
  assert all(w != "i" for w in joined.split())


def test_internal_apparatus_hole_is_not_the_boundary() -> None:
  """A double apparatus glued to the page foot leaves a huge vertical
  hole BETWEEN its tiers (small type on both sides). The text/foot
  boundary is the register drop, even when its gap is far smaller than
  the internal hole (observed: 1.0x pitch boundary vs 7x pitch hole)."""
  lines = []
  y = 700.0
  for _ in range(8):
    lines.append(FakeLine("corpus textus latinorum verborum hic stat", "Garamond", 10.0, y))
    y -= 13.0
  # fontium tier opens right below, ~1x pitch, sharp register drop
  y -= 0.5
  for _ in range(3):
    lines.append(FakeLine("156-157 Actus Apostolorum 5:39 rem tenet", "Garamond", 8.0, y))
    y -= 10.5
  # the variant tier sits at the page foot, a huge hole away
  y -= 90.0
  for _ in range(4):
    lines.append(FakeLine("156 tempore] ipse R SV 157 tamen] cum V", "Garamond", 8.0, y))
    y -= 10.5
  lp = classify_page(FakeLayout(lines), 0)
  foot = " ".join(ln.text for b in lp.bands
                  if b.layer in ("apparatus", "notes") for ln in b.lines)
  assert "Actus Apostolorum" in foot   # fontium tier IS in the foot
  assert "tempore" in foot             # variant tier too
  body = " ".join(ln.text for b in lp.bands
                  if b.layer in ("greek_text", "translation") for ln in b.lines)
  assert "Actus Apostolorum" not in body


def test_one_line_title_does_not_claim_the_whole_page_as_foot() -> None:
  """A 1-line 11pt title over a 10pt body must not make the body look
  'dropped': the boundary is the widest TRUE register edge, so the body
  stays in the main band and only the small-type foot splits off
  (observed: a catena page filed whole as 'notes')."""
  lines = [FakeLine("Catena in Ps. 2, 31", "Garamond", 11.0, 700.0, x0=210.0)]
  y = 676.0
  for _ in range(10):
    lines.append(FakeLine("corpus textus verborum satis longum hic stat bene", "Garamond", 10.0, y))
    y -= 12.0
  y -= 45.0
  for _ in range(5):
    lines.append(FakeLine("2 lectio] varia P : om. V 3 alia] om. B", "Garamond", 8.0, y))
    y -= 10.0
  lp = classify_page(FakeLayout(lines), 0)
  body = " ".join(ln.text for b in lp.bands
                  if b.layer in ("greek_text", "translation") for ln in b.lines)
  assert "corpus textus" in body
  foot = " ".join(ln.text for b in lp.bands
                  if b.layer in ("apparatus", "notes") for ln in b.lines)
  assert "lectio] varia" in foot
  assert "corpus textus" not in foot


@pytest.mark.xfail(
  strict=True,
  reason=(
    "a real foot at 0.84x pitch remains in main text because gap <= 0.85*pitch "
    "is an unconditional veto (audit F9)"
  ),
)
def test_gap_just_below_point_85_pitch_still_separates_foot() -> None:
  # balex p84 abstraction: a tightly set last text line and first note line
  # are distinct registers even though their baselines are only 0.84 pitch apart.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus legitimus in columna manet", "Garamond", 10.0, y))
    y -= 12.0
  y += 1.9  # last body baseline to foot baseline = 10.1pt, just below 0.85 * 12pt
  for _ in range(3):
    lines.append(FakeLine("1 lemma] varia lectio A B", "Garamond", 8.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "lemma] varia" in page.layer_text("notes")


@pytest.mark.xfail(
  strict=True,
  reason=(
    "a 1.2x-pitch foot with a 1.4pt drop misses both the soft >=1.5pt and "
    "strong >1.7x tiers (audit F9)"
  ),
)
def test_point_1_2_pitch_gap_with_point_1_4pt_drop_separates_foot() -> None:
  # balex p82 abstraction: modest whitespace and a visible but sub-1.5pt
  # register change jointly mark the notes band.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus legitimus in columna manet", "Garamond", 10.0, y))
    y -= 12.0
  y -= 2.4  # last body baseline to foot baseline = 14.4pt = 1.2 * pitch
  for _ in range(3):
    lines.append(FakeLine("1 lemma] varia lectio A B", "Garamond", 8.6, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "lemma] varia" in page.layer_text("notes")


def test_gap_just_over_point_1_7_pitch_with_clean_drop_separates_foot() -> None:
  # balex p84 abstraction: a clean 10pt-to-8pt edge just clears the strong-gap tier.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus legitimus in columna manet", "Garamond", 10.0, y))
    y -= 12.0
  y -= 8.5  # last body baseline to foot baseline = 20.5pt, just over 1.7 * pitch
  for _ in range(3):
    lines.append(FakeLine("1 lemma] varia lectio A B", "Garamond", 8.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "lemma] varia" in page.layer_text("notes")


@pytest.mark.xfail(
  strict=True,
  reason=(
    "same-size 10pt apparatus has no register drop and is classified as main text "
    "despite a wide gap (audit F9)"
  ),
)
def test_same_size_apparatus_after_wide_gap_stays_separate() -> None:
  # balex p84 abstraction: apparatus and body share a 10pt register, so geometry
  # must not depend on a font-size drop that the edition does not supply.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus legitimus in columna manet", "Garamond", 10.0, y))
    y -= 12.0
  y -= 48.0
  for _ in range(3):
    lines.append(FakeLine("1 lemma] apparatus eiusdem corporis A B", "Garamond", 10.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "apparatus eiusdem" in page.layer_text("notes")


@pytest.mark.xfail(
  strict=True,
  reason=(
    "two of three genuine foot lines are smaller, but 2/3 falls below the 0.7 "
    "durable-drop cutoff and the entire foot enters main text (audit F9)"
  ),
)
def test_two_of_three_smaller_lines_are_a_durable_foot() -> None:
  # lectio14 p5 abstraction: one display-sized line inside a three-line foot
  # must not erase the smaller register shown by the other two lines.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus legitimus in columna manet", "Garamond", 10.0, y))
    y -= 12.0
  y -= 24.0
  lines.extend([
    FakeLine("1 lemma] prima lectio A", "Garamond", 8.0, y),
    FakeLine("2 lemma] secunda lectio B", "Garamond", 8.0, y - 12.0),
    FakeLine("3 lemma] linea amplior C", "Garamond", 10.0, y - 24.0),
  ])

  page = classify_page(FakeLayout(lines), 0)
  assert "prima lectio" in page.layer_text("notes")


def test_exact_point_9_remainder_qualifies_as_full_candidate() -> None:
  # lectio14 p5 abstraction: the upper apparatus edge leaves exactly nine of
  # ten remainder lines smaller; its wider gap must retain both lower tiers.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus legitimus in columna manet", "Garamond", 10.0, y))
    y -= 12.0
  y -= 14.0  # 26pt first gap
  for _ in range(4):
    lines.append(FakeLine("fontium exact ratio linea minor A B", "Garamond", 8.0, y))
    y -= 12.0
  lines.append(FakeLine("apparatus subheading in upper register", "Garamond", 10.0, y))
  y -= 22.0
  for _ in range(5):
    lines.append(FakeLine("variant tier linea minor R V", "Garamond", 8.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "fontium exact ratio" in page.layer_text("notes")


def test_true_edge_rejects_internal_double_apparatus_hole() -> None:
  # lectio14 p5 abstraction: the line above the 4x-pitch internal hole is
  # already 8pt apparatus, not the 10pt upper register.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus legitimus in columna manet", "Garamond", 10.0, y))
    y -= 12.0
  for _ in range(3):
    lines.append(FakeLine("fontium tier begins at the true edge", "Garamond", 8.0, y))
    y -= 12.0
  y -= 36.0
  for _ in range(3):
    lines.append(FakeLine("variant tier below internal hole R V", "Garamond", 8.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "fontium tier" in page.layer_text("notes")


def test_true_edge_accepts_body_register_above_bobichon_foot() -> None:
  # Bobichon p394 abstraction: beneath a one-line 11pt title, the line directly
  # above the modest foot gap is ordinary 10pt body and validates the edge.
  lines = [FakeLine("Catena in Ps. 2, 31", "Garamond", 11.0, 700.0, x0=210.0)]
  y = 688.0
  for _ in range(3):
    lines.append(FakeLine("corpus textus sub titulo legitimus manet", "Garamond", 10.0, y))
    y -= 12.0
  y -= 2.4  # 14.4pt = soft gap; this tier requires true_edge
  for _ in range(3):
    lines.append(FakeLine("2 lectio] varia P et omissa V", "Garamond", 8.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "lectio] varia" in page.layer_text("notes")


def test_widest_gap_wins_between_two_true_edge_full_candidates() -> None:
  # Bobichon p394 abstraction: both the title/body gap and the body/foot gap
  # are full true edges, but the wider 3x-pitch body/foot gap is the cut.
  # Terminal punctuation keeps this section title from being taken as a
  # running head before the two boundary candidates are compared.
  lines = [FakeLine("Catena in Ps. 2, 31.", "Garamond", 11.0, 700.0, x0=210.0)]
  y = 678.0  # 22pt title gap
  for _ in range(3):
    lines.append(FakeLine("corpus textus sub titulo legitimus manet", "Garamond", 10.0, y))
    y -= 12.0
  y -= 24.0  # 36pt body/foot gap
  for _ in range(3):
    lines.append(FakeLine("2 lectio] varia P et omissa V", "Garamond", 8.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "corpus textus" in page.layer_text("translation")


@pytest.mark.xfail(
  strict=True,
  reason=(
    "with only three 12pt body lines the true 12pt-to-10pt edge cannot be full; "
    "the wider internal 10pt-to-8pt gap wins and strands fontium in main text "
    "(audit F10)"
  ),
)
def test_three_line_12pt_body_keeps_both_double_apparatus_tiers_in_foot() -> None:
  # lectio14 p5 audit construction: 12pt body, 10pt fontium, then 8pt variants
  # across the page's widest gap.
  lines = []
  y = 700.0
  for _ in range(3):
    lines.append(FakeLine("passage in duodecim punctis legitimum", "Garamond", 12.0, y))
    y -= 12.0
  y -= 12.0  # 24pt true body/fontium gap
  for _ in range(4):
    lines.append(FakeLine("fontium tier decem punctorum A B", "Garamond", 10.0, y))
    y -= 12.0
  y -= 24.0  # 36pt internal gap, deliberately the widest
  for _ in range(4):
    lines.append(FakeLine("variant tier octo punctorum R V", "Garamond", 8.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "fontium tier" in page.layer_text("notes")


@pytest.mark.xfail(
  strict=True,
  reason=(
    "a legitimate two-letter corner catchword is irreversibly dropped by the "
    "corner-furniture filter (audit F10)"
  ),
)
def test_two_letter_corner_catchword_survives_furniture_filter() -> None:
  # balex p82 abstraction: the compositorial catchword "Et" is real textual
  # content despite occupying the same corner geometry as crop furniture.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus ad proximam paginam ducit", "Garamond", 10.0, y))
    y -= 12.0
  lines.append(FakeLine("Et", "Garamond", 10.0, 20.0, x0=24.0))

  page = classify_page(FakeLayout(lines), 0)
  assert "Et" in " ".join(b.text for b in page.bands)


@pytest.mark.xfail(
  strict=True,
  reason=(
    "a narrow digits-only textual line in the left gutter is irreversibly dropped "
    "as a marginal counter (audit F10)"
  ),
)
def test_narrow_digits_only_text_in_left_gutter_survives_filter() -> None:
  # balex p84 abstraction: a displayed textual numeral shares the left-gutter
  # geometry of reledmac line counters but belongs to the constituted passage.
  lines = [
    FakeLine("corpus textus ante numerum legitimum", "Garamond", 10.0, 700.0),
    FakeLine("12", "Garamond", 10.0, 688.0, x0=50.0),
    FakeLine("corpus textus post numerum legitimum", "Garamond", 10.0, 676.0),
    FakeLine("corpus textus in eadem columna pergit", "Garamond", 10.0, 664.0),
  ]

  page = classify_page(FakeLayout(lines), 0)
  assert "12" in page.layer_text("translation").splitlines()


@pytest.mark.xfail(
  strict=True,
  reason=(
    "the narrow lexical opener '1 om. A' is treated as margin-markish and left "
    "in main text while its following apparatus lines split off (audit F10)"
  ),
)
def test_short_narrow_apparatus_opener_stays_with_its_foot_band() -> None:
  # lectio14 p5 abstraction: a terse first apparatus entry opens the same band
  # as the two full-width entries immediately below it.
  lines = []
  y = 700.0
  for _ in range(4):
    lines.append(FakeLine("corpus textus legitimus in columna manet", "Garamond", 10.0, y))
    y -= 12.0
  y -= 24.0
  lines.extend([
    FakeLine("1 om. A", "Garamond", 8.0, y),
    FakeLine("2 lemma] varia lectio R V", "Garamond", 8.0, y - 12.0),
    FakeLine("3 lemma] altera lectio S", "Garamond", 8.0, y - 24.0),
  ])

  page = classify_page(FakeLayout(lines), 0)
  assert "1 om. A" in page.layer_text("notes")


@pytest.mark.xfail(
  strict=True,
  reason=(
    "upper_size <= 11 makes a three-line 11pt passage a full candidate, so its "
    "wider gap swallows legitimate 10pt continuation text as notes (audit F10)"
  ),
)
def test_upper_at_most_11_escape_does_not_swallow_legitimate_continuation() -> None:
  # Bobichon p394 abstraction: three 11pt lines and their smaller 10pt continuation
  # are one passage; only the still-smaller 8pt material is the foot.
  lines = []
  y = 700.0
  for _ in range(3):
    lines.append(FakeLine("passage legitimum in undecim punctis", "Garamond", 11.0, y))
    y -= 12.0
  y -= 18.0  # 30pt passage/continuation gap, deliberately wider
  for _ in range(4):
    lines.append(FakeLine("continuatio legitima in decem punctis", "Garamond", 10.0, y))
    y -= 12.0
  y -= 12.0  # 24pt true continuation/foot gap
  for _ in range(3):
    lines.append(FakeLine("1 lemma] apparatus octo punctorum A", "Garamond", 8.0, y))
    y -= 12.0

  page = classify_page(FakeLayout(lines), 0)
  assert "continuatio legitima" in page.layer_text("translation")


def test_folio_candidate_reenters_at_end_of_line_list() -> None:
  # balex p84 abstraction: the centered folio sits physically between the two
  # lines that once became "cognitio] 3 intellectio" in the apparatus flow.
  layout = FakeLayout([
    FakeLine("cognitio] lectio R", "Garamond", 8.0, 112.0),
    FakeLine("3", "Garamond", 10.0, 106.0, x0=290.0),
    FakeLine("intellectio] omissa V", "Garamond", 8.0, 100.0),
  ])

  texts = [line.text for line in L._lines_of(layout)]
  assert texts == ["cognitio] lectio R", "intellectio] omissa V", "3"]
