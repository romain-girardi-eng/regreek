"""Decoder unit tests against empirically verified examples.

Every expected value below was verified against the TLG-E text of the source
work during table derivation (see FINDINGS.md); nothing here is invented.
"""

from __future__ import annotations

import unicodedata

import pytest

from regreek import tokenize
from regreek.decoder import TableDecoder
from regreek.registry import load_tables, table_for_font


def dec(font: str) -> TableDecoder:
  tdoc = table_for_font(font)
  assert tdoc is not None
  return TableDecoder(tdoc)


GRAECA_CASES = [
  # verified against TLG0645 (Dialogus cum Tryphone) during derivation
  ("Peripatou'ntiv", "Περιπατοῦντί"),
  ("e{wqen", "ἕωθεν"),
  ("ejn", "ἐν"),
  ("toi'\"", "τοῖς"),
  ("aujtw'/", "αὐτῷ"),
  ("oiJ", "οἱ"),
  ("fivloi", "φίλοι"),
  ("jEdidavcqhn", "Ἐδιδάχθην"),
  ("[Argei", "Ἄργει"),
  ("ou\\n", "οὖν"),
  ("kai;", "καὶ"),
  ("d!", "δ’"),
  ("Truvfwn", "Τρύφων"),
  ("yuchvn", "ψυχήν"),
  ("ejxei'pen", "ἐξεῖπεν"),
  ("cai're", "χαῖρε"),
]


@pytest.mark.parametrize(("legacy", "expected"), GRAECA_CASES)
def test_graeca(legacy: str, expected: str) -> None:
  got = dec("Graeca").decode_word(legacy)
  assert got.text == unicodedata.normalize("NFC", expected)
  assert got.fully_mapped


BWGRKL_CASES = [
  # verified against TLG0031 (NT) during derivation
  ("pi,stij", "πίστις"),
  ("qeou/", "θεοῦ"),
  ("pro.j", "πρὸς"),
  ("evleuqeri,a", "ἐλευθερία"),
  ("ca,rij", "χάρις"),
  ("kai,", "καί"),
  ("o`", "ὁ"),
  ("VIhsou/", "Ἰησοῦ"),
  ("avllV", "ἀλλ’"),
]


@pytest.mark.parametrize(("legacy", "expected"), BWGRKL_CASES)
def test_bwgrkl(legacy: str, expected: str) -> None:
  got = dec("Bwgrkl").decode_word(legacy)
  assert got.text == unicodedata.normalize("NFC", expected)


def test_bwgrkl_final_punct_context() -> None:
  # word already accented -> trailing '.' is a full stop, not a grave
  got = dec("Bwgrkl").decode_word("qeou/.")
  assert got.text == "θεοῦ."


def test_odyssea_positional_quote() -> None:
  d = dec("Odyssea")
  # mid-word " is a positioning variant, word-final " is final sigma
  assert d.decode_word('me";n').text == "μὲν"
  assert d.decode_word('toi`ı').text == "τοῖς"


def test_timesgreek_precomposed() -> None:
  d = dec("TimesGreek")
  assert d.decode_word("xáriv").text == "χάρις"
  assert d.decode_word("qnjt¬ç").text == "θνητῷ"
  assert d.decode_word("ˆIjsoÕ").text == "Ἰησοῦ"


def test_unmapped_preserved_and_flagged() -> None:
  got = dec("Graeca").decode_word("kaiØ")
  assert "Ø" in got.text
  assert got.unmapped == ["Ø"]
  assert not got.fully_mapped
  rec = [r for r in got.records if not r.mapped]
  assert rec and rec[0].confidence == 0.0


def test_output_is_nfc_greek() -> None:
  for legacy, _ in GRAECA_CASES:
    text = dec("Graeca").decode_word(legacy).text
    assert text == unicodedata.normalize("NFC", text)
    for c in text:
      if c.isalpha():
        assert "Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿", (legacy, text, c)


def test_iota_subscript_migration_regression() -> None:
  """Observed bug: 'aJgivw/' hyphen-less line break puts '/' on the next line,
  silently turning dative ἁγίῳ into ἁγίω (a genuine case change)."""
  tdoc = table_for_font("Graeca")
  assert tdoc is not None
  code_chars = {c for c, spec in tdoc["codes"].items() if "marks" in spec}
  lines = ["ejn pneuvmati aJgivw", "/ tou' qeou'"]
  repaired = tokenize.repair_lines(lines, code_chars)
  assert repaired[0].endswith("aJgivw/")
  toks = tokenize.tokens(repaired, tdoc.get("separators", ""))
  d = TableDecoder(tdoc)
  decoded = [d.decode_word(t).text for t in toks]
  assert "ἁγίῳ" in decoded


def test_hyphen_line_join() -> None:
  tdoc = table_for_font("Graeca")
  assert tdoc is not None
  lines = ["ejk panto;" + "\" filo-", "sofiva\" gevnoito"]
  repaired = tokenize.repair_lines(lines, set())
  toks = tokenize.tokens(repaired, tdoc.get("separators", ""))
  d = TableDecoder(tdoc)
  decoded = [d.decode_word(t).text for t in toks]
  assert "φιλοσοφίας" in decoded


def test_all_tables_load_and_are_wellformed() -> None:
  for tdoc in load_tables():
    assert tdoc["letters"] and tdoc["codes"]
    assert "derivation" in tdoc and "validation" in tdoc
    d = TableDecoder(tdoc)
    for ch, greek in tdoc["letters"].items():
      assert isinstance(ch, str) and isinstance(greek, str)
      out = d.decode_word(ch).text
      assert out  # decodes to something


def test_diaeresis_acute_code_not_separator() -> None:
  """Regression (audit 2026-08-03): '?' was declared a separator in the Graeca
  table, silently splitting JHsai?ou -> JHsai + ou and deleting the mark, so
  Ἡσαΐου came out as two mutilated tokens. '?' is the diaeresis+acute code."""
  tdoc = table_for_font("Graeca")
  assert tdoc is not None
  assert "?" not in tdoc.get("separators", "")
  toks = tokenize.tokens(["dia; JHsai?ou khrucqe;n"], tdoc.get("separators", ""))
  assert "JHsai?ou" in toks
  d = TableDecoder(tdoc)
  decoded = {d.decode_word(t).text for t in toks}
  assert "Ἡσαΐου" in decoded
  # the whole harvest set decodes to the attested forms
  for legacy, expected in [
    ("JHsai?a\"", "Ἡσαΐας"), ("Daui?d", "Δαυΐδ"), ("prwi?", "πρωΐ"),
    ("Nineui?tai\"", "Νινευΐταις"),
  ]:
    assert d.decode_word(legacy).text == expected


def test_unknown_codes_flagged_never_swallowed() -> None:
  """'?' and '_' must never be separators in any table without punctuation
  evidence: an unknown code must surface as unmapped+flagged, not vanish."""
  for tdoc in load_tables():
    if tdoc["font"] == "SPIonic":  # CID-level table, control-byte separators
      continue
    seps = tdoc.get("separators", "")
    assert "_" not in seps or "punctuation_notes" in tdoc
    if "?" in tdoc["codes"] or "?" in tdoc["letters"]:
      continue  # evidenced mapping exists
    assert "?" not in seps
    d = TableDecoder(tdoc)
    w = d.decode_word("ab?cd")
    assert "?" in w.unmapped and "?" in w.text


def test_spionic_ascii_chart() -> None:
  """SPIonic (public-domain chart, Beta-Code-style: marks follow the vowel)."""
  from regreek.text import decode_text

  cases = [
    ("i3na mh\\ pare/lqh| u9ma~j o9 peirasmo/j", "ἵνα μὴ παρέλθῃ ὑμᾶς ὁ πειρασμός"),
    ("ou0k e0n u9posta/sei ou0si/aj geno/menoj", "οὐκ ἐν ὑποστάσει οὐσίας γενόμενος"),
    ("skeu~oj ou]n mesto\\n", "σκεῦος οὖν μεστὸν"),
    ("qeo/j e0stin", "θεός ἐστιν"),
  ]
  for legacy, expected in cases:
    assert decode_text(legacy, encoding="spionic-ascii").text == expected


def test_spionic_digits_are_codes_not_separators() -> None:
  """Regression: default digit-splitting must not eat SPIonic breathings
  (9 = rough breathing: u9ma~j = ὑμᾶς, not υ + μᾶς)."""
  from regreek.text import decode_text

  r = decode_text("u9ma~j", encoding="spionic-ascii")
  assert r.text == "ὑμᾶς"
  assert r.fully_mapped


def test_autodetection_discriminates_encodings() -> None:
  from regreek.text import decode_text

  spionic = decode_text("i3na mh\\ pare/lqh| u9ma~j o9 peirasmo/j")
  assert spionic.table_id == "spionic-ascii"
  graeca = decode_text("dia; JHsai?ou khrucqe;n ejn pneuvmati aJgivw/")
  assert graeca.table_id == "graeca"
  assert graeca.text == "διὰ Ἡσαΐου κηρυχθὲν ἐν πνεύματι ἁγίῳ"


def test_unique_table_ids() -> None:
  from regreek.text import tables_by_id

  ids = tables_by_id()
  assert len(ids) == len(load_tables())


# --- red-team regressions (2026-08-03) ---------------------------------------


def test_plain_latin_prose_refused() -> None:
  """F1: auto-detection must refuse to transliterate plain Latin-alphabet
  prose into pseudo-Greek."""
  import pytest as _pytest

  from regreek.text import decode_text

  for prose in (
    "hello world this is plain english",
    "le texte français ordinaire ne doit pas devenir du grec",
    "lorem ipsum dolor sit amet consectetur",
  ):
    with _pytest.raises(ValueError):
      decode_text(prose)


def test_explicit_encoding_on_latin_prose_warns() -> None:
  from regreek.text import decode_text

  r = decode_text("hello world plain text here", encoding="graeca")
  assert r.warning is not None


def test_real_legacy_greek_still_detected() -> None:
  from regreek.text import decode_text

  r = decode_text("i3na mh\\ pare/lqh| u9ma~j o9 peirasmo/j")
  assert r.table_id == "spionic-ascii"
  assert r.warning is None
  r2 = decode_text("dia; JHsai?ou khrucqe;n ejn pneuvmati aJgivw/")
  assert r2.table_id == "graeca"


def test_unicode_greek_tokens_pass_through() -> None:
  """F2: already-Unicode Greek must survive tokenization and decoding."""
  from regreek.text import decode_text

  r = decode_text("kai; ἤδη λόγος tou'to", encoding="graeca")
  assert r.text == "καὶ ἤδη λόγος τοῦτο"
  assert r.fully_mapped
  r2 = decode_text("λόγος σοφίας", encoding="graeca")
  assert r2.text == "λόγος σοφίας"


def test_midword_positional_variant_has_provenance() -> None:
  """F3: a mid-word final_letter variant glyph must appear in the records."""
  got = dec("Odyssea").decode_word('lo"go"')
  assert got.text == "λογος"
  assert "".join(r.source for r in got.records) == 'lo"go"'
