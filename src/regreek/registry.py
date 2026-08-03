"""Font-name -> table registry."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from .decoder import TableDecoder

_TABLE_FILES = (
  "graeca.json",
  "graeca2.json",
  "odyssea.json",
  "symbolgreek2.json",
  "bwgrkl.json",
  "timesgreek.json",
  "grecmonotype.json",
  "spionic.json",
  "spionic_ascii.json",
)


def strip_subset_prefix(font_name: str) -> str:
  """``DBGFPI+Graeca`` -> ``Graeca``."""
  if len(font_name) > 7 and font_name[6] == "+" and font_name[:6].isupper():
    return font_name[7:]
  return font_name


@lru_cache(maxsize=1)
def load_tables() -> list[dict]:
  tables = []
  for name in _TABLE_FILES:
    with resources.files("regreek.tables").joinpath(name).open(encoding="utf-8") as f:
      tables.append(json.load(f))
  return tables


def table_for_font(font_name: str) -> dict | None:
  """Best-matching table document for an embedded font name, or None."""
  base = strip_subset_prefix(font_name)
  best: dict | None = None
  best_len = -1
  for tdoc in load_tables():
    for prefix in tdoc["match"]:
      if base.startswith(prefix) and len(prefix) > best_len:
        best, best_len = tdoc, len(prefix)
  return best


@lru_cache(maxsize=32)
def decoder_for_font(font_name: str) -> TableDecoder | None:
  tdoc = table_for_font(font_name)
  if tdoc is None:
    return None
  return TableDecoder(tdoc)


def known_legacy_font(font_name: str) -> bool:
  return table_for_font(font_name) is not None
