"""
parsers/generic_csv.py — Fallback parser for generic CSV bank statements.

Handles any CSV that has at least:
  - A date column
  - A description/narration column
  - At least one amount column (or separate debit/credit columns)

This catches exports from banks not yet covered by dedicated parsers
(Axis, ICICI, Kotak, Paytm, Google Pay, etc.).
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
    _extract_upi_id,
    _extract_payee,
    register_parser,
)

logger = logging.getLogger(__name__)

_DATE_COLS   = {"date", "txn date", "transaction date", "value date", "posting date",
                "trans date", "trans. date", "booking date"}
_DESC_COLS   = {"description", "narration", "particulars", "remarks", "details",
                "transaction details", "beneficiary name / remarks", "memo"}
_DR_COLS     = {"debit", "dr", "withdrawal", "withdrawal amt", "debit amount",
                "money out", "amount (dr)"}
_CR_COLS     = {"credit", "cr", "deposit", "deposit amt", "credit amount",
                "money in", "amount (cr)"}
_AMT_COLS    = {"amount", "transaction amount", "amt", "net amount"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


@register_parser
class GenericCsvParser(BaseStatementParser):
    name = "generic_csv"
    display_name = "Generic CSV Statement"

    @classmethod
    def can_parse(cls, file_bytes: bytes, filename: str) -> bool:
        """Accept any .csv file as a last-resort fallback."""
        return filename.lower().endswith(".csv")

    def parse(self, file_bytes: bytes, filename: str) -> List[NormRow]:
        rows: List[NormRow] = []
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            delimiter = ";" if text.count(";") > text.count(",") else ","
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            all_rows = list(reader)

            header_idx, col_map = self._find_header(all_rows)
            if header_idx is None:
                logger.warning("GenericCsvParser: no usable header in %s", filename)
                return rows

            for raw_row in all_rows[header_idx + 1:]:
                if not any(c.strip() for c in raw_row):
                    continue
                row = self._parse_row(raw_row, col_map)
                if row:
                    rows.append(row)
        except Exception as e:
            logger.error("GenericCsvParser error: %s", e, exc_info=True)
        return rows

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _find_header(self, all_rows):
        for idx, row in enumerate(all_rows):
            normed = [_norm(c) for c in row]
            nset   = set(normed)
            if (nset & _DATE_COLS) and (nset & _DESC_COLS or nset & _AMT_COLS):
                cm = self._map_columns(normed)
                if cm:
                    return idx, cm
        return None, None

    def _map_columns(self, header: list) -> dict:
        cm = {}
        for i, h in enumerate(header):
            if h in _DATE_COLS and "date" not in cm:
                cm["date"] = i
            elif h in _DESC_COLS and "description" not in cm:
                cm["description"] = i
            elif h in _DR_COLS and "debit" not in cm:
                cm["debit"] = i
            elif h in _CR_COLS and "credit" not in cm:
                cm["credit"] = i
            elif h in _AMT_COLS and "amount" not in cm:
                cm["amount"] = i
        return cm if "date" in cm else {}

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
        amount_str  = get("amount")

        if not date_str:
            return None
        parsed_date = _parse_date(date_str)
        if not parsed_date:
            return None

        dr_amt = _clean_amount(debit_str) if debit_str else Decimal("0")
        cr_amt = _clean_amount(credit_str) if credit_str else Decimal("0")
        net_amt = _clean_amount(amount_str) if amount_str else Decimal("0")

        if dr_amt == 0 and cr_amt == 0 and net_amt == 0:
            return None

        if dr_amt > 0 or cr_amt > 0:
            is_debit = dr_amt > 0
            amount   = dr_amt if is_debit else cr_amt
        else:
            # Single amount col — negative = debit, positive = credit
            is_debit = net_amt < 0
            amount   = abs(net_amt)

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
