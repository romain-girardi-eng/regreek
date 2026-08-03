"""regreek: legacy (pre-Unicode) Greek font decoding for PDFs.

Tables were derived clean-room by aligning real critical-edition PDFs with the
same texts in the TLG-E corpus; every mapping carries provenance and measured
attestation. Unmapped codes are preserved and flagged, never guessed.
"""

from .decoder import CharRecord, DecodedWord, TableDecoder, is_greek_char
from .pdf import DecodedPage, decode_page, extract_runs, legacy_fonts_in_pdf
from .registry import decoder_for_font, known_legacy_font, table_for_font
from .text import DecodedText, DetectionScore, decode_text, detect_encoding, tables_by_id

__version__ = "0.1.0"

__all__ = [
  "CharRecord",
  "DecodedPage",
  "DecodedWord",
  "TableDecoder",
  "DecodedText",
  "DetectionScore",
  "decode_page",
  "decode_text",
  "detect_encoding",
  "tables_by_id",
  "decoder_for_font",
  "extract_runs",
  "is_greek_char",
  "known_legacy_font",
  "legacy_fonts_in_pdf",
  "table_for_font",
  "__version__",
]
