"""Line assembly and tokenization of legacy font streams.

Handles the two real-world line-break hazards observed in the corpus:

- hyphenated words split across lines (``fi-`` / ``losofiva"``);
- diacritic codes migrating to the next line (``aJgivw`` / ``/ ...`` —
  the iota subscript of a dative silently dropped, ἁγίῳ becoming ἁγίω).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# characters that are always word separators, in every supported encoding
_SPACE = " \\t\\n\\r\u00a0\u2000-\u200b\u202f\u205f\u3000"
_SEPARATORS = re.compile("[" + _SPACE + r"\d«»—–*&%§¶•°€#]+")

_WORD_CHAR = re.compile(r"[A-Za-z-]")


@dataclass
class Line:
  """One visual line of same-font legacy text."""

  text: str
  page: int


def repair_lines(lines: list[str], code_chars: set[str]) -> list[str]:
  """Join hyphenated line breaks and re-attach migrated leading diacritics.

  ``code_chars``: characters that are diacritic codes in the active table.
  A line starting with code chars followed by a separator (or nothing) had its
  codes orphaned by the line break; they belong to the last word of the
  previous line.
  """
  out: list[str] = []
  for raw in lines:
    # rejoin words split around an interleaved other-font insert: "fi- -losofiva"
    ln = re.sub(r"-[ ]+-", "", raw)
    # migrated diacritics: leading run of code chars then boundary
    m = re.match("^([" + re.escape("".join(sorted(code_chars))) + "]+)([" + _SPACE + "]|$)", ln) \
        if code_chars else None
    if m and out and _WORD_CHAR.search(out[-1]):
      out[-1] = out[-1].rstrip() + m.group(1)
      ln = ln[m.end(1):].lstrip()
      if not ln:
        continue
    if out and out[-1].endswith("-"):
      prev = out[-1][:-1]
      # join: hyphenated break; tolerate a repeated hyphen opening the next line
      out[-1] = prev + ln.lstrip("-")
    else:
      out.append(ln)
  return out


def tokens(lines: list[str], extra_separators: str = "",
           keep: set[str] | frozenset[str] = frozenset()) -> list[str]:
  """Split lines into legacy tokens.

  ``keep``: characters that are LETTERS or CODES in the active table and must
  therefore never act as separators — e.g. the digits of SPIonic, where ``9``
  is the rough breathing (``u9ma~j`` = ὑμᾶς). Without it, default digit
  splitting would silently delete diacritics.
  """
  base = "«»—–*&%§¶•°€#"
  digits = "" if any(c.isdigit() for c in keep) else r"\d"
  base = "".join(c for c in base if c not in keep)
  extra = "".join(c for c in extra_separators if c not in keep)
  sep = re.compile("[" + _SPACE + digits + re.escape(base + extra) + "]+")
  toks: list[str] = []
  for ln in lines:
    for t in sep.split(ln):
      t = t.strip("-")
      if t and _WORD_CHAR.search(t):
        toks.append(t)
  return toks
