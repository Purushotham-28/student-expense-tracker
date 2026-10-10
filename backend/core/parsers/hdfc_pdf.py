"""
parsers/hdfc_pdf.py — Parser for HDFC Bank PDF account statements.

HDFC PDF statements contain a table with columns similar to:
  Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance

This parser uses pdfplumber to extract all tables from all pages and
identifies the correct table by its header row.
"""

from __future__ import annotations

import re
import logging
from decimal import Decimal
from typing import List

import pdfplumber

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

# Column name variants (lowercase) that identify an HDFC-style table
_HDFC_DATE_COLS = {"date", "txn date", "transaction date", "value date", "value dt"}
_HDFC_NARR_COLS = {"narration", "description", "particulars", "remarks", "remark"}
_HDFC_DR_COLS   = {"withdrawal amt.", "withdrawal amt", "debit", "dr amount", "dr amt", "debit amount", "dr amt."}
_HDFC_CR_COLS   = {"deposit amt.", "deposit amt", "credit", "cr amount", "cr amt", "credit amount", "cr amt."}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


@register_parser
class HdfcPdfParser(BaseStatementParser):
    name = "hdfc_pdf"
    display_name = "HDFC Bank PDF Statement"

    @classmethod
    def can_parse(cls, file_bytes: bytes, filename: str) -> bool:
        if not filename.lower().endswith(".pdf"):
            return False
        # Quick text scan for HDFC identifiers
        try:
            with pdfplumber.open(__import__("io").BytesIO(file_bytes)) as pdf:
                first_text = (pdf.pages[0].extract_text() or "").lower() if pdf.pages else ""
                return "hdfc" in first_text or "hdfc bank" in first_text
        except Exception:
            return False

    def parse(self, file_bytes: bytes, filename: str) -> List[NormRow]:
        rows: List[NormRow] = []
        import io as _io
        try:
            with pdfplumber.open(_io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if not table or len(table) < 2:
                            continue
                        header = [_norm(c or "") for c in table[0]]
                        if not self._is_hdfc_table(header):
                            continue
                        col_map = self._map_columns(header)
                        if not col_map:
                            continue
                        for raw_row in table[1:]:
                            row = self._parse_row(raw_row, col_map, header)
                            if row:
                                rows.append(row)
        except Exception as e:
            logger.error("HdfcPdfParser error: %s", e, exc_info=True)
        return rows

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _is_hdfc_table(self, header: list) -> bool:
        has_date = any(h in _HDFC_DATE_COLS for h in header)
        has_narr = any(h in _HDFC_NARR_COLS for h in header)
        return has_date and has_narr

    def _map_columns(self, header: list) -> dict:
        cm = {}
        for i, h in enumerate(header):
            if h in _HDFC_DATE_COLS and "date" not in cm:
                cm["date"] = i
            elif h in _HDFC_NARR_COLS and "narration" not in cm:
                cm["narration"] = i
            elif h in _HDFC_DR_COLS and "debit" not in cm:
                cm["debit"] = i
            elif h in _HDFC_CR_COLS and "credit" not in cm:
                cm["credit"] = i
        return cm if "date" in cm and "narration" in cm else {}

    def _parse_row(self, raw_row: list, col_map: dict, header: list) -> NormRow | None:
        def get(key):
            idx = col_map.get(key)
            if idx is None or idx >= len(raw_row):
                return ""
            return str(raw_row[idx] or "").strip()

        date_str  = get("date")
        narration = get("narration")
        debit_str = get("debit")
        credit_str= get("credit")

        if not date_str and not narration:
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

        raw_text = " | ".join(str(c or "") for c in raw_row)

        return {
            "date":       parsed_date,
            "time":       None,
            "amount":     amount,
            "is_debit":   is_debit,
            "payee_name": _extract_payee(narration),
            "upi_id":     _extract_upi_id(narration),
            "remark":     narration[:512],
            "raw_text":   raw_text[:1000],
        }
