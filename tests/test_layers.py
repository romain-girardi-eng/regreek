"""Layer classification tests on synthetic geometry.

The fixtures reproduce the measured layout of a bilingual critical edition
(10 pt Greek body / 11 pt translation body, 8-9 pt apparatus after a wide
gap, isolated running head and page number) with dummy text, so no
copyrighted material is embedded.
"""

from __future__ import annotations

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
