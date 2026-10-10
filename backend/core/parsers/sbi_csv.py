"""
parsers/sbi_csv.py — Parser for SBI (State Bank of India) CSV account statements.

SBI CSV statements typically look like:
  Txn Date,Value Date,Description,Ref No./Cheque No.,Debit,Credit,Balance

Some SBI exports use semicolons as delimiters and have a few header rows
before the actual column header.  This parser is resilient to that.
"""

from __future__ import annotations

import io
import csv
import re
import logging
from decimal import Decimal
from typing import List

from .base import (
    BaseStatementParser,
    NormRow,
    _clean_amount,
    _parse_date,
    _parse_time,
    _extract_upi_id,
    _extract_payee,
    register_parser,
)

logger = logging.getLogger(__name__)

_SBI_DATE_COLS  = {"txn date", "date", "transaction date", "value date"}
_SBI_DESC_COLS  = {"description", "narration", "particulars", "remarks", "details"}
_SBI_DR_COLS    = {"debit", "dr", "withdrawal", "withdrawal amt", "debit amount"}
_SBI_CR_COLS    = {"credit", "cr", "deposit", "deposit amt", "credit amount"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


@register_parser
class SbiCsvParser(BaseStatementParser):
    name = "sbi_csv"
    display_name = "SBI Bank CSV Statement"

    @classmethod
    def can_parse(cls, file_bytes: bytes, filename: str) -> bool:
        if not filename.lower().endswith(".csv"):
            return False
        # Look for SBI in the first ~400 bytes
        snippet = file_bytes[:400].decode("utf-8", errors="ignore").lower()
        return "sbi" in snippet or "state bank" in snippet or cls._has_sbi_columns(file_bytes)

    @classmethod
    def _has_sbi_columns(cls, file_bytes: bytes) -> bool:
        """Return True if the CSV has at least one recognised SBI header combination."""
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            reader = csv.reader(io.StringIO(text))
            for _ in range(10):       # scan up to 10 rows for a header
                row = next(reader, None)
                if row is None:
                    break
                normed = {_norm(c) for c in row}
                if normed & _SBI_DATE_COLS and normed & _SBI_DESC_COLS:
                    return True
        except Exception:
            pass
        return False

    def parse(self, file_bytes: bytes, filename: str) -> List[NormRow]:
        rows: List[NormRow] = []
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            # Auto-detect delimiter (comma or semicolon)
            delimiter = ";" if text.count(";") > text.count(",") else ","
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            all_rows = list(reader)

            # Find the header row (first row whose cells match our col sets)
            header_idx, col_map = self._find_header(all_rows)
            if header_idx is None:
                logger.warning("SbiCsvParser: no header row found in %s", filename)
                return rows

            for raw_row in all_rows[header_idx + 1:]:
                if not any(c.strip() for c in raw_row):
                    continue
                row = self._parse_row(raw_row, col_map)
                if row:
                    rows.append(row)
        except Exception as e:
            logger.error("SbiCsvParser error: %s", e, exc_info=True)
        return rows

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _find_header(self, all_rows):
        for idx, row in enumerate(all_rows):
            normed = [_norm(c) for c in row]
            normed_set = set(normed)
            if normed_set & _SBI_DATE_COLS and normed_set & _SBI_DESC_COLS:
                col_map = self._map_columns(normed)
                if col_map:
                    return idx, col_map
        return None, None

    def _map_columns(self, header: list) -> dict:
        cm = {}
        for i, h in enumerate(header):
            if h in _SBI_DATE_COLS and "date" not in cm:
                cm["date"] = i
            elif h in _SBI_DESC_COLS and "description" not in cm:
                cm["description"] = i
            elif h in _SBI_DR_COLS and "debit" not in cm:
                cm["debit"] = i
            elif h in _SBI_CR_COLS and "credit" not in cm:
                cm["credit"] = i
        return cm if "date" in cm and "description" in cm else {}

    def _parse_row(self, raw_row: list, col_map: dict) -> NormRow | None:
        def get(key):
            idx = col_map.get(key)
            if idx is None or idx >= len(raw_row):
                return ""
            return str(raw_row[idx] or "").strip()

        date_str    = get("date")
        description = get("description")
        debit_str   = get("debit")
        credit_str  = get("credit")

        if not date_str:
            return None

        parsed_date = _parse_date(date_str)
        if not parsed_date:
            return None

        dr_amt = _clean_amount(debit_str) if debit_str else Decimal("0")
        cr_amt = _clean_amount(credit_str) if credit_str else Decimal("0")

        if dr_amt == 0 and cr_amt == 0:
            return None

        is_debit = dr_amt > 0
        amount   = dr_amt if is_debit else cr_amt
        raw_text = ",".join(raw_row)

        return {
            "date":       parsed_date,
            "time":       None,
            "amount":     amount,
            "is_debit":   is_debit,
            "payee_name": _extract_payee(description),
            "upi_id":     _extract_upi_id(description),
            "remark":     description[:512],
            "raw_text":   raw_text[:1000],
        }
