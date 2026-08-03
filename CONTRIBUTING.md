# Contributing

## The most valuable contribution: a font sample

The pipeline scales with data, not code. To add or strengthen a font table we
need a **born-digital** document (PDF, RTF, DOC, or plain text) typeset in the
target font, ideally of a work that also exists in a public reference corpus
(Perseus, First1KGreek) so the derivation can be aligned and the result
honestly validated. A few hundred words are often enough.

Open an issue with:
- the font name (as reported by `regreek FILE.pdf --list-fonts`,
  or the name of the font your document uses);
- what work the text is (author, title, edition if known);
- the file, or a link to it if it is publicly available.

## Ground rules

1. **Zero fabrication.** A table entry needs evidence: aligned corpus pairs,
   or public/permissive documentation of the encoding. If a keystroke's value
   cannot be evidenced, it stays unmapped — the decoder will preserve and
   flag it, which is the correct behaviour.
2. **License hygiene.** This project is MIT. Do not read, copy, or transcribe
   tables from GPL-licensed converters (GreekTranscoder, seanredmond's
   converters, Antioch). Public-domain encoding charts and MIT/Apache
   material are fine, with attribution in the table's `derivation` field.
3. **Validation is held-out.** Accuracy is only ever claimed on text that was
   not used to derive the table, and the measured number goes in the table
   file's `validation` field — including when it is weak.
4. **Every table change needs a test.** Real examples with verified expected
   output, in `tests/test_decoder.py`.

## Development

```console
pip install -e ".[dev]"
pytest -q
ruff check src/ tests/
```

Code style: PEP 8, 2-space indentation, full type annotations, no `Any`
without a reason.
