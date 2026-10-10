"""
parsers/base.py — Abstract base class for all bank statement parsers.

Design:
  Each bank/format gets its own subclass.  A registry maps format-name
  strings to parser classes.  The top-level `parse_statement()` function
  auto-detects the format and delegates to the right parser.

Normalised row schema (dict):
  {
    "date":         date | None,
    "time":         time | None,
    "amount":       Decimal,        # always positive
    "is_debit":     bool,
    "payee_name":   str,
    "upi_id":       str,
    "remark":       str,
    "raw_text":     str,
  }
"""

from __future__ import annotations

import re
import io
import csv
import logging
from abc import ABC, abstractmethod
from datetime import date, time, datetime
from decimal import Decimal, InvalidOperation
from typing import IO, List, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
NormRow = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_amount(text: str) -> Decimal:
    """Strip currency symbols, commas, spaces → Decimal."""
    cleaned = re.sub(r"[₹$,\s]", "", str(text)).strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(text: str, formats=None) -> date | None:
    if formats is None:
        formats = [
            "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y",
            "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y",
            "%d %b %y", "%m/%d/%Y",
        ]
    text = str(text).strip()
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_time(text: str) -> time | None:
    text = str(text).strip()
    for fmt in ["%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"]:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _extract_upi_id(text: str) -> str:
    """Pull UPI VPA (e.g. name@bank) from a remark string."""
    m = re.search(r"[\w.\-]+@[\w.\-]+", text)
    return m.group(0) if m else ""


def _extract_payee(text: str) -> str:
    """
    Heuristic payee extraction from common UPI/NEFT remark formats.
    Examples:
      'UPI-ZOMATO-9876543210@okaxis-...'  → 'ZOMATO'
      'NEFT-HDFC0000001-JOHN DOE-...'     → 'JOHN DOE'
    """
    text = str(text).strip()
    # UPI pattern: UPI-PAYEE-...
    m = re.match(r"UPI[/-]([^/-]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # NEFT/IMPS: NEFT-BANKCODE-NAME-...
    m = re.match(r"(?:NEFT|IMPS|RTGS)[/-][^/-]+[/-]([^/-]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: first meaningful segment before any @
    parts = re.split(r"[-/@]", text)
    for p in parts:
        p = p.strip()
        if len(p) > 2 and not re.match(r"^\d+$", p):
            return p
    return text[:80]


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseStatementParser(ABC):
    """All bank parsers must implement `can_parse` and `parse`."""

    name: str = "base"           # unique format identifier
    display_name: str = "Base"   # human-readable

    @classmethod
    @abstractmethod
    def can_parse(cls, file_bytes: bytes, filename: str) -> bool:
        """
        Quick sniff: return True if this parser is confident it can handle
        the file. Checked before calling parse().
        """

    @abstractmethod
    def parse(self, file_bytes: bytes, filename: str) -> List[NormRow]:
        """Return a list of normalised row dicts."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: List[type[BaseStatementParser]] = []


def register_parser(cls: type[BaseStatementParser]):
    """Decorator — adds a parser class to the global registry."""
    _REGISTRY.append(cls)
    return cls


def get_registry() -> List[type[BaseStatementParser]]:
    return list(_REGISTRY)
