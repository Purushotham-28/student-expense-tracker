"""
parsers/generic_csv.py — Layout-agnostic CSV / Excel bank statement parser.

Features:
  - Dynamically searches first ~15 rows for header cells matching common words.
  - Maps columns via fuzzy header matching (date, narration/particulars, debit/credit/amount).
  - Handles unified amount with (Dr)/(Cr) suffix or separate debit/credit columns.
  - Raises UnsupportedLayoutError if header or transactions cannot be found.
"""

from __future__ import annotations

import io
import csv
import re
import logging
from decimal import Decimal
from typing import List, Dict, Tuple, Any

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
from .exceptions import UnsupportedLayoutError

logger = logging.getLogger(__name__)

_DATE_COLS = ["date", "txn date", "transaction date", "value date", "posting date", "trans date", "booking date", "tran date"]
_DESC_COLS = ["description", "narration", "particulars", "remarks", "remark", "details", "transaction details", "payee", "beneficiary", "memo"]
_DR_COLS   = ["debit", "dr", "withdrawal", "withdrawal amt", "debit amount", "money out", "amount (dr)", "dr amt"]
_CR_COLS   = ["credit", "cr", "deposit", "deposit amt", "credit amount", "money in", "amount (cr)", "cr amt"]
_AMT_COLS  = ["amount", "transaction amount", "amt", "net amount", "amount (in rs.)", "amount( )"]
_BAL_COLS  = ["balance", "closing balance", "bal", "available balance"]
_UPI_COLS  = ["upi", "upi id", "ref no", "reference", "chq", "cheque", "utr", "txn id", "transaction id"]


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


@register_parser
class GenericCsvParser(BaseStatementParser):
    name = "generic_csv"
    display_name = "Generic CSV Statement"

    @classmethod
    def can_parse(cls, file_bytes: bytes, filename: str) -> bool:
        fn = filename.lower()
        return fn.endswith(".csv") or fn.endswith(".tsv") or fn.endswith(".txt")

    def parse(self, file_bytes: bytes, filename: str) -> List[NormRow]:
        rows: List[NormRow] = []
        try:
            text = file_bytes.decode("utf-8-sig", errors="ignore")
            # Try comma, semicolon, tab
            delimiter = ","
            if text.count(";") > text.count(","):
                delimiter = ";"
            elif text.count("\t") > text.count(","):
                delimiter = "\t"

            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            all_rows = list(reader)

            if not all_rows:
                raise UnsupportedLayoutError("CSV file is empty.")

            header_idx, col_map = self._find_header(all_rows[:15])
            if header_idx is None or not col_map:
                raise UnsupportedLayoutError(
                    "could not find a transaction header row in the first 15 rows of the CSV file. "
                    "Ensure columns like Date, Description, and Amount/Debit/Credit are present."
                )

            for raw_row in all_rows[header_idx + 1:]:
                if not any(c.strip() for c in raw_row):
                    continue
                row = self._parse_row(raw_row, col_map)
                if row:
                    rows.append(row)

            if not rows:
                raise UnsupportedLayoutError(
                    f"found header at row {header_idx + 1}, but could not extract any valid transaction records below it"
                )

        except UnsupportedLayoutError:
            raise
        except Exception as e:
            logger.error("GenericCsvParser error: %s", e, exc_info=True)
            raise UnsupportedLayoutError(f"error parsing CSV statement: {e}")

        return rows

    def _find_header(self, candidate_rows: list) -> Tuple[int | None, Dict[str, int] | None]:
        for idx, row in enumerate(candidate_rows):
            normed = [_norm(c) for c in row]
            col_map = self._map_columns(normed)
            if col_map and "date" in col_map and ("amount" in col_map or "debit" in col_map or "credit" in col_map):
                return idx, col_map
        return None, None

    def _map_columns(self, header: list) -> Dict[str, int]:
        cm = {}
        for i, h in enumerate(header):
            if not h:
                continue
            if "date" not in cm and any(kw in h for kw in _DATE_COLS):
                cm["date"] = i
            elif "description" not in cm and any(kw in h for kw in _DESC_COLS):
                cm["description"] = i
            elif "debit" not in cm and any(kw in h for kw in _DR_COLS):
                cm["debit"] = i
            elif "credit" not in cm and any(kw in h for kw in _CR_COLS):
                cm["credit"] = i
            elif "amount" not in cm and any(kw in h for kw in _AMT_COLS):
                cm["amount"] = i
            elif "upi" not in cm and any(kw in h for kw in _UPI_COLS):
                cm["upi"] = i
        return cm

    def _parse_row(self, raw_row: list, col_map: dict) -> NormRow | None:
        def get(key: str) -> str:
            idx = col_map.get(key)
            if idx is None or idx >= len(raw_row):
                return ""
            return str(raw_row[idx] or "").strip()

        date_str    = get("date")
        description = get("description")
        debit_str   = get("debit")
        credit_str  = get("credit")
        amount_str  = get("amount")
        upi_ref     = get("upi")

        if not date_str:
            return None
        parsed_date = _parse_date(date_str)
        if not parsed_date:
            return None

        dr_amt  = _clean_amount(debit_str) if debit_str else Decimal("0")
        cr_amt  = _clean_amount(credit_str) if credit_str else Decimal("0")
        net_amt = _clean_amount(amount_str) if amount_str else Decimal("0")

        if dr_amt == 0 and cr_amt == 0 and net_amt == 0:
            return None

        if dr_amt > 0 or cr_amt > 0:
            is_debit = dr_amt > 0
            amount   = dr_amt if is_debit else cr_amt
        else:
            # Check for (Dr) / (Cr) in amount_str
            amt_lower = amount_str.lower()
            if "(dr)" in amt_lower or " dr" in amt_lower or "-" in amount_str:
                is_debit = True
            elif "(cr)" in amt_lower or " cr" in amt_lower:
                is_debit = False
            else:
                is_debit = True
            amount = abs(net_amt)

        raw_text = ",".join(str(c) for c in raw_row)
        upi_id = _extract_upi_id(description) or (upi_ref if "@" in upi_ref else "")
        payee = _extract_payee(description) if description else "Unknown Payee"

        return {
            "date":       parsed_date,
            "time":       None,
            "amount":     amount,
            "is_debit":   is_debit,
            "payee_name": payee,
            "upi_id":     upi_id,
            "remark":     description[:512],
            "raw_text":   raw_text[:1000],
        }
