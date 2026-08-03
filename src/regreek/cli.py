"""Command-line interface.

Usage::

  regreek <pdf> [--page N] [--json] [--list-fonts]
"""

from __future__ import annotations

import argparse
import json
import sys

from .pdf import decode_page, extract_runs, legacy_fonts_in_pdf
from .text import decode_text, tables_by_id


def main(argv: list[str] | None = None) -> int:
  ap = argparse.ArgumentParser(
    prog="regreek",
    description="Decode legacy Greek fonts in born-digital PDFs to Unicode",
  )
  ap.add_argument("pdf", nargs="?", default=None,
                  help="path to the PDF (omit with --text/--stdin)")
  ap.add_argument("--text", default=None, metavar="LEGACY",
                  help="decode a legacy-encoded string instead of a PDF")
  ap.add_argument("--stdin", action="store_true",
                  help="decode legacy-encoded text read from stdin")
  ap.add_argument("--encoding", default=None,
                  help="table id to use for --text/--stdin (default: auto-detect)")
  ap.add_argument("--list-encodings", action="store_true",
                  help="list known encodings (table ids)")
  ap.add_argument("--page", type=int, default=None, help="0-based page number (default: all)")
  ap.add_argument("--json", action="store_true", help="emit JSON with provenance records")
  ap.add_argument("--layers", action="store_true",
                  help="separate page layers (text/apparatus/translation/margins) as JSON")
  ap.add_argument("--md", action="store_true",
                  help="layer-separated structured Markdown (one section per layer)")
  ap.add_argument("--layer", default=None,
                  metavar="NAME",
                  help="print only one layer as text: greek_text|translation|"
                       "apparatus|notes|heading|running_head")
  ap.add_argument("--list-fonts", action="store_true",
                  help="list known legacy fonts found (first 20 pages)")
  args = ap.parse_args(argv)

  if args.list_encodings:
    for tid, tdoc in sorted(tables_by_id().items()):
      print(f"{tid}\t{tdoc['font']}")
    return 0

  if args.text is not None or args.stdin:
    raw = args.text if args.text is not None else sys.stdin.read()
    result = decode_text(raw, encoding=args.encoding)
    if args.json:
      print(json.dumps({
        "encoding": result.table_id,
        "text": result.text,
        "fully_mapped": result.fully_mapped,
        "unmapped_total": result.unmapped_total,
        "detection": [
          {"table_id": d.table_id, "score": round(d.score, 4)}
          for d in (result.detection or [])[:5]
        ],
      }, ensure_ascii=False))
    else:
      print(result.text)
      if result.detection:
        print(f"[encoding: {result.table_id}, auto-detected]", file=sys.stderr)
      if result.warning:
        print(f"[!] {result.warning}", file=sys.stderr)
      if not result.fully_mapped:
        print(f"[!] {result.unmapped_total} unmapped code(s) preserved and flagged",
              file=sys.stderr)
    return 0

  if args.pdf is None:
    ap.error("a PDF path is required unless --text/--stdin/--list-encodings is used")

  if args.list_fonts:
    for font, n in sorted(legacy_fonts_in_pdf(args.pdf).items(), key=lambda kv: -kv[1]):
      print(f"{font}\t{n} chars")
    return 0

  pages = [args.page] if args.page is not None else None

  if args.layers or args.layer or args.md:
    from .layers import layer_pages
    got = False
    for pg in layer_pages(args.pdf, pages=pages):
      if args.md:
        if not pg.bands:
          continue
        got = True
        print(f"## page {pg.page}\n")
        for b in pg.bands:
          refs = f"  \n*refs: {', '.join(b.inline_refs)}*" if b.inline_refs else ""
          print(f"### {b.layer}  \n<sub>confidence {b.confidence:.2f} — {b.evidence}</sub>{refs}\n")
          print(b.text + "\n")
        continue
      if args.layer:
        text = pg.layer_text(args.layer)
        if text:
          got = True
          print(text)
        continue
      got = True
      print(json.dumps({
        "page": pg.page,
        "bands": [
          {
            "layer": b.layer,
            "confidence": b.confidence,
            "evidence": b.evidence,
            "bbox": [round(v, 1) for v in b.bbox],
            "inline_refs": b.inline_refs,
            "text": b.text,
          }
          for b in pg.bands
        ],
      }, ensure_ascii=False))
    return 0 if got else 1

  any_output = False
  for page in extract_runs(args.pdf, pages=pages):
    decoded = decode_page(page)
    if not decoded.tokens:
      continue
    any_output = True
    if args.json:
      payload = {
        "page": decoded.page,
        "tokens": [
          {
            "source": t.token,
            "text": t.word.text,
            "font": t.font,
            "fully_mapped": t.word.fully_mapped,
            "unmapped": t.word.unmapped,
            "confidence": min((r.confidence for r in t.word.records), default=1.0),
          }
          for t in decoded.tokens
        ],
      }
      print(json.dumps(payload, ensure_ascii=False))
    else:
      print(f"--- page {decoded.page}")
      print(decoded.text)
      flagged = [t for t in decoded.tokens if not t.word.fully_mapped]
      if flagged:
        print(f"[!] {len(flagged)} token(s) contain unmapped codes:",
              ", ".join(repr(t.token) for t in flagged[:10]), file=sys.stderr)
  if not any_output:
    print("no known legacy Greek font content found", file=sys.stderr)
    return 1
  return 0


def run() -> int:
  """Console entry point: user errors become messages, not tracebacks."""
  try:
    return main()
  except (ValueError, KeyError) as exc:
    print(f"error: {exc}", file=sys.stderr)
    return 2
  except FileNotFoundError as exc:
    print(f"error: file not found: {exc.filename or exc}", file=sys.stderr)
    return 2
  except (UnicodeDecodeError, Exception) as exc:  # pdfminer parse errors etc.
    print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(run())
