# FINDINGS — Legacy Greek font decoding, phase 0

Empirical survey and table derivation over a private research corpus of 601
scholarly PDFs (classics/patristics; read-only). Everything below was measured,
not assumed. Aggregated machine-readable census: `data/font_census.json`
(601 PDFs, per-PDF font list, page counts, sampled char counts).

## 1. Corpus inventory

- **601 PDFs** scanned, 0 unreadable.
- **1,489 distinct embedded font base names** (5,264 font instances after
  subset-prefix stripping).
- Legacy Greek fonts by mass (pages where the font is used):

| Font | PDFs | Pages | Status |
|---|---|---|---|
| Graeca | 2 (Bobichon Dial. vols 1-2) | 703 | **table derived + held-out validated** |
| Bwgrkl | 3 docs | ~190 | **table derived + held-out validated** |
| SPIonic (no ToUnicode) | 1 | 54 | table derived (CID-level, same-doc validation) |
| GrecMonotype + GrecAccMonotype | 2 docs | 48 | table derived (same-doc validation) |
| GraecaII | 1 | 34 | family table validated |
| Odyssea (+Bold/Italic) | 2 docs | ~70 | family table validated |
| TimesGreek | 1 doc | 20 | table derived (same-doc only) |
| SymbolGreekII | 2 docs | 17 | family table, weak validation sample |
| SirbaGRK | 1 | 68 | **no Greek content** (used as Latin body font) — nothing to derive |
| Kadmos, GrecMonotypeA, GrecAccentAutres, TimesGreekSF | – | ≤4 each | insufficient material |
| PorsonForOUP*, FFPorson (OUP books) | 4 | ~500 | **already Unicode** (subsets `+03`/`+1f` = Greek/Greek-Extended blocks) — no table needed |
| KadmosU | 2 | 504 | **already Unicode** (the U means Unicode) — no table needed |

Corrections to prior assumptions, established empirically:

- **Bobichon vol. 2 is born-digital** (Graeca on 448 pages), not scanned; the
  scanned/corrupted-OCR files are the two Munier Paradosis volumes
  (`HiddenHorzOCR` / Courier-only overlays). Vol. 2 therefore served as the
  held-out validation set for Graeca.
- `KadmosU` and the `PorsonForOUP*+03/+1f` subsets extract as real Unicode
  Greek; classifying by font name alone overcounts the legacy problem.

## 2. Method (reproducible)

1. **Extraction.** Per-page, per-line, per-font character runs
   (PyMuPDF for exploration; the shipped package uses pdfminer.six only).
   Runs in other fonts break words; hyphenated line-breaks are re-joined;
   a leading run of diacritic codes at line start is re-attached to the last
   word of the previous line (see §4, migration bug).
2. **Ground truth.** The same works exist in Unicode in the local TLG-E corpus.
   A clean-room beta-code decoder (public TLG spec) turns the author files into
   word streams.
3. **Alignment.** Both streams are reduced to base-letter "skeletons"
   (legacy letters via a beta-like prior, verified empirically: lowercase
   letter purity was 100 % on 50k aligned pairs). Skeleton 3-gram unique
   anchors + longest-increasing-subsequence + greedy extension give
   high-precision word pairs (50,026 exact pairs for Graeca).
4. **Learning.** Base letters anchor 1:1; every non-letter code accumulates
   co-occurrence counts with the combining marks of the adjacent letters.
   The counts decide meaning *and* position rule. Empirical position rule for
   every font examined: **marks attach to the nearest preceding vowel (rho for
   breathings); with no preceding carrier they attach to the following letter**
   (word-initial breathings before capitals).
5. **Fonts quoting isolated words** (no continuous text to align):
   lexicon-constrained decipherment — each unknown char is one letter-unit;
   candidate TLG words matching the known-letter template vote, weighted by
   corpus frequency; iterate to fixpoint. Remaining chars resolved by
   **attestation scoring** (decode all affected tokens under every candidate
   meaning; the winner must beat the runner-up clearly) or left unmapped.
6. **Validation.** Attestation of decoded tokens against the full TLG-E:
   accent-insensitive (`att_base`, what `tlg_search.py` measures) and
   accent-sensitive (`att_accented`, exact NFC form among 1.39 M distinct
   TLG word forms). Held-out = a document not used for derivation.

## 3. Per-font results

Metrics on ≥2-letter tokens; `coverage` = tokens fully decoded (no unmapped code).

| Font | Derived from | Validated on | Tokens | Coverage | att_base | att_accented |
|---|---|---|---|---|---|---|
| **Graeca** | Bobichon vol. 1 vs TLG0645 (50,026 pairs) | **held-out: vol. 2** (Dial. 75-142) | 15,142 | 99.9 % | **99.4 %** | **98.6 %** |
| **GraecaII** | Graeca family + variant `` ` ``=circumflex | La Catena delle cause (different work) | 1,100 | 99.9 % | 100 % | 99.3 % |
| **Odyssea** | family + variants (alignment vs TLG0557) | Epictetus paper | 345 | 99.7 % | 100 % | 98.8 % |
| **SymbolGreekII** | family + `~`=final sigma | OROPEZA 2007 — **23 tokens only** | 23 | 100 % | 87.0 % | 82.6 % |
| **Bwgrkl** | Paul thesis vs TLG0031+0527 (127 pairs, 98.4 % exact) | **held-out: Bagby 2015 thesis** | 155 | 98.7 % | 98.1 % | 96.8 % |
| **TimesGreek** | lexicon solve + Rm 6-7 alignment | **same document** (only one exists) | 127 | 100 % | 100 % | 100 % |
| **GrecMonotype(+Acc)** | lexicon solve + layout inference, Eliasson 2009 | same document (held-out Sharples = 6 tokens) | 1,323 | 98.5 % | 99.5 % | 98.5 % |
| **SPIonic** | CID stream vs TLG0031/0527 + attestation | same document (single SPIonic PDF) | 895 | 99.3 % | 98.1 % | 95.3 % |

Word-exact match against the aligned TLG text on the Graeca derivation set:
96.26 %; of the residual, 2.85 pts are capitalisation differences between
editions (Bobichon capitalises dialogue turns), 0.86 pts are genuine
edition/accent variants (ζῷα/ζῶα, ἄττα/ἅττα, δέ/δὲ …), 0.05 pts are decoder- or
extraction-attributable. The attestation "misses" on held-out are dominated by
real rare words and by **apparatus entries that reproduce manuscript
misspellings on purpose** (e.g. βαβλυλῶνα) — i.e. faithful decoding of
deliberately non-standard text.

The Graeca keystroke scheme, as *learned* (evidence counts in `tables/graeca.json`):
`j`=smooth, `J`=rough, `v`=acute, `;`=grave, `'`=circumflex, `/`=iota subscript,
`\`=smooth+circumflex, `|`=rough+circumflex, `[`=smooth+acute, `]`=smooth+grave,
`{`=rough+acute, `}`=rough+grave, `>`=diaeresis, `"`=final sigma, `!`=apostrophe;
letters beta-like with `x`=ξ, `c`=χ, `y`=ψ; marks follow the vowel; word-initial
marks precede capitals.

## 4. Hard cases handled

- **Diacritic order**: post-positioned after vowels in all Linguist's Software
  fonts and Bwgrkl and SPIonic; pre-positioned only word-initially (capitals).
  Multi-mark keys (`{ } [ ] \ |`) carry breathing+accent pairs; sequences on one
  vowel (`w'/` = ω+circumflex+subscript) accumulate and are canonically
  reordered by NFC.
- **Final sigma**: dedicated keys (`"`, `~`, dotless `ı`, Bwgrkl `j`,
  SPIonic `j`-slot); plain `s` at word end (typist slip) is normalised to ς.
- **Accent-vs-punctuation ambiguity (Bwgrkl)**: `,`=acute and `.`=grave are
  also real punctuation. Contextual rule: word-final `,`/`.` after an
  unaccented vowel = accent, otherwise punctuation. Irreducible residue:
  enclitic chains (εἶναί τινα) whose final acute is indistinguishable from a
  comma without syntax — counted, documented, ~1 % of Bwgrkl tokens.
- **Diacritic migration across line breaks** (observed: `aJgivw` + line-initial
  `/` silently turning ἁγίῳ into ἁγίω): line-initial orphan code runs are
  re-attached to the previous line's last word. Regression-tested.
- **Interleaved-font hyphenation** (`fi-` … `[p. 78 : B]` … `-losofiva"`):
  rejoined; regression-tested.
- **Two-font schemes** (GrecMonotype base letters + GrecAccMonotype accented
  glyphs): accent-font chars are shifted into the PUA before decoding so both
  fonts merge into one stream (`companion` block in the table).
- **No-ToUnicode fonts** (SPIonic subsets): decoded at CID level.

## 5. What is NOT covered, and why

- **SymbolGreekII**: only 23 validation tokens in the corpus; its "misses" are
  dictionary lemma citations. Treat the table as family-inherited, thinly
  verified.
- **TimesGreek**: exactly one 10-page document exists; there is **no held-out
  validation**. 15 rare chars rest on single-verse alignment evidence
  (documented per char in the table). Provisional.
- **GrecMonotype**: a handful of glyphs remain unmapped (e.g. `U+E0C8`-area
  subscript variants, 1-3 occurrences each); 5 glyphs were completed from the
  font's systematic vowel-block layout (X0=acute … X7=rough+acute), each
  attestation-compatible but not independently provable — flagged in
  `layout_inferences`.
- **SPIonic**: the table is CID-level and verified for the single SPIonic PDF
  in the corpus; other SPIonic subsets may order glyphs differently.
- **SirbaGRK**: no Greek in the corpus document (English 1877 reprint) —
  nothing derivable.
- **Kadmos, TimesGreekSF, GrecMonotypeA, GrecAccentAutres, Odyssea-Bold**:
  ≤ a few chars each in the whole corpus.
- **Hebraica** (Bobichon vol. 2): out of scope (Hebrew).
- **Bwgrkl rare codes**: derived from 127 aligned pairs; codes never observed
  (e.g. diaeresis combos) are absent and will surface as flagged unmapped
  chars, not silent errors.
- The **`tlg_search.py` oracle is accent-insensitive**; accent-level claims
  rest on the accent-sensitive lexicon (1.39 M forms) built from TLG-E with a
  clean-room beta-code decoder, and on exact word alignment. Accent attestation
  slightly *understates* accuracy: correctly decoded rare forms and apparatus
  misspellings count as misses.

## 6. Reproduction

Scratch pipeline in `scratch/` (exploration; PyMuPDF used there only):
`inventory.py` → `extract_legacy.py` → `align_learn.py` / `derive_font.py`
(alignment + co-occurrence learning) → `solve_precomposed.py` /
`solve_by_attestation.py` (isolated-word fonts) → `validate2.py` /
`build_lexicon*.py` (TLG lexicons). The shipped package (`src/`) depends only
on pdfminer.six (MIT).

## 7. Independent audit (2026-08-03, post-delivery)

An adversarial audit re-measured everything from scratch, with its own page
sampling and its own single-pass TLG attestation, on both Bobichon volumes.

**Claims confirmed.** Vol. 1 (derivation source): 99.51 % of token types
attested (94.93 % in Justin TLG0645 himself), 99.76 % occurrence-weighted,
zero non-Greek character leakage. Vol. 2 (held-out): 99.15 % types /
99.46 % weighted — consistent with the reported 99.4 %. The residual
unattested tokens are apparatus readings faithfully reproduced from
manuscripts (φυλάσσσετε, κικυῶνος = the qiqayon of Jon 4:6 in Dial. 107) or
rare-but-plausible forms (ἀνασπαρθῇ, δωδεκαφύλου).

**One real defect found and fixed: `?` declared a separator in the Graeca
table.** The tokenizer split `JHsai?ou` into `JHsai`+`ou` *before* decoding,
silently deleting the mark — Ἡσαΐου surfaced as «Ἡσαι ου». This escaped both
oracles (the 2-letter fragment fell under the token-length floor; the base
attestation is accent-insensitive) and, worse, bypassed the decoder's
unmapped-flagging contract. Evidence harvest over both volumes: 33
occurrences, 9 word types (Ἡσαΐας/Ἡσαΐου/Ἡσαΐᾳ, Δαυΐδ, πρωΐ, Νινευΐ(ται)),
100 % consistent with `?` = combining diaeresis + acute; zero word-final
occurrences. Fixed as an evidenced code; regression-tested.

`_` was likewise investigated: every sampled context is a clause-final
interrogative (Πῶς γάρ _ / Τί οὖν _) — it is the Greek question mark
(the `;` key being taken by the grave accent). Documented; still dropped
with other punctuation in word-level output.

**Policy change across all tables**: a mid-word evidence sweep was run for
every declared separator character of every table. Only Graeca's `?` had
mid-word occurrences; `.`/`,`/`(`/`)` mid-word hits are genuine punctuation
typeset without spaces (κ.τ.λ., «σου.Μετὰ»), where splitting is correct.
`?` and `_` were nevertheless removed from the separators of *all* text-key
tables that lack punctuation evidence for them: an unknown code must surface
as unmapped+flagged, never vanish in tokenization. This closes the class of
bug, not just the instance.

**Fidelity note.** Vol. 1 p. 300 prints πλῆρουν (raw keystrokes
`plh'roun`): the circumflex is genuinely typeset on the eta in the edition.
The decoder reproduces the page faithfully — including its typos. Correcting
them would be fabrication; flagging them is the attestation layer's job.

## 8. Phase 1 — layer separation (2026-08-03)

`regreek.layers` classifies each page into bands — `greek_text`,
`translation`, `apparatus`, `notes`, `heading`, `running_head`,
`page_number` — from geometry and typography alone: the modal body pitch,
font-size registers, vertical gaps, script signatures, centering. No content
understanding, no ML; lines are never reordered or merged, and each band
carries the evidence for its label plus a confidence.

Empirical grounding (measured on a bilingual critical edition): Greek body
10 pt; facing translation 11 pt; apparatus 8–9 pt opening after a gap of
~2.4× the body pitch; running head and page number isolated by >1.6× pitch.
The apparatus/notes label follows page context (Greek page → apparatus;
translation page → notes/apparatus fontium).

Validation over 55 systematically sampled pages of both volumes:
running head and page number detected 55/55; 459 apparatus-sigla matches
(prop./coni./codd./editor names) routed 97.8 % into the apparatus band and
**0 % into the Greek text band**. The 10 residual matches sit on two page
types outside the text+apparatus model, both known limitations:

- **front matter** (conspectus siglorum, introduction) — no 10/11 pt body
  register exists, so the page classifies as body text;
- **note-overflow pages** — translation-note continuations that fill a page
  entirely in the notes register, leaving no size boundary to detect.

Both would need cross-page state to resolve; deliberately left honest
rather than heuristically patched.

Inline witness references (`[fol. 94 v° : A]`, `[p. 144 : B]`, `[PG …]`)
are extracted per band into `inline_refs` and left in place in the text
(fidelity over cleaning).

## 9. Adversarial red-team and fixes (2026-08-03)

An independent adversarial review attacked the published v0.2.0 on six
surfaces (claims, zero-fabrication contract, layer classifier, crash
resistance, package hygiene, determinism). Its re-measurements **confirmed**
the published numbers (held-out Graeca 97.5 % on its own page sample vs
99.4 % published; sigla routing 100 % with zero greek_text leakage on a
disjoint 54-page sample; wheel byte-identical to the repo; determinism
byte-stable). It also found real defects, all fixed in v0.3.0:

- **F1 (critical)** — auto-detection happily "decoded" plain English/French
  prose into pseudo-Greek with score 1.0. Detection now requires diacritic
  key-code evidence (≥15 % of tokens); plain Latin prose is refused with an
  explicit message, and an explicit `encoding=` on such input attaches a
  warning instead of silent transliteration.
- **F2 (major)** — tokens containing already-Unicode Greek were silently
  discarded by the word filter. They now pass through verbatim (NFC), with a
  provenance record.
- **F3 (major)** — mid-word positional-variant glyphs (`final_letter` codes)
  were consumed without a provenance record. Every consumed character now
  appears in `records`.
- **F4 (major)** — short centred Greek lines in the same face and size as
  the body were misfiled as `heading`, dropping constituted text from the
  greek_text layer (observed on two real pages). A heading now must differ
  from the body typographically (font family or size), not merely be
  centred.
- **F6 (minor)** — CLI user errors surfaced as raw tracebacks; a dotted
  leader could match the digits-only page-number rule. Both fixed (clean
  stderr messages, exit 2; digits now required).
- **F7 (minor)** — token count 15,152 → 15,142 (matches the table file);
  stale reference to the pre-publication inventory file corrected.
- **F5, adjudicated false positive** — SPIonic `7` is the chart's
  non-breaking space: treating it as a word separator is correct
  tokenization, not deletion. Documented in the table file. The general
  point stands and is already policy: characters that *are* codes must
  never sit in `separators`.

What held under attack: determinism, NFC output, Greek-block guarantee,
rho-breathing rule, orphan-mark flagging, hyphen/diacritic-migration repair,
RTL/ZWJ/combining-flood inputs (preserved + flagged), 50k-char tokens
(slow but no crash), package/version/licensing hygiene.
