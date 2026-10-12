"""
parsers/universal_pdf.py — Layout-agnostic PDF parser for bank & UPI statements.

Pipeline:
  1. Security check: detect password encryption.
  2. Scanned check: detect image-only PDFs with no extractable text.
  3. Table extraction: across all pages using pdfplumber extract_tables()
     with fuzzy column header matching.
  4. Text fallback: if no table or 0 rows, parse raw text lines and blocks
     (handles Google Pay, PhonePe cards, and flexible Date/Amount/UPI regex).
"""

from __future__ import annotations

import io
import re
import logging
from decimal import Decimal
from typing import List, Dict, Any, Tuple

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
from .exceptions import (
    PasswordProtectedPdfError,
    ScannedPdfError,
    UnsupportedLayoutError,
)

logger = logging.getLogger(__name__)

# Column keywords for fuzzy header matching
_DATE_KEYWORDS = ["date", "txn date", "transaction date", "value date", "value dt", "tran date", "posting date"]
_NARR_KEYWORDS = ["narration", "description", "particulars", "remarks", "remark", "receiver", "payee", "beneficiary", "transaction details", "details"]
_DR_KEYWORDS   = ["withdrawal", "debit", "dr amount", "dr amt", "money out", "withdrawal amt", "withdrawal amt."]
_CR_KEYWORDS   = ["deposit", "credit", "cr amount", "cr amt", "money in", "deposit amt", "deposit amt."]
_AMT_KEYWORDS  = ["amount", "amt", "transaction amount", "amount (in rs.)", "amount( )", "net amount"]
_DRCR_KEYWORDS = ["dr/cr", "cr/dr", "dr / cr", "cr / dr", "type", "pay/collect", "d/c"]
_TIME_KEYWORDS = ["time", "txn time", "transaction time"]
_STAT_KEYWORDS = ["status", "txn status", "transaction status"]
_REF_KEYWORDS  = ["payment id", "reference", "ref no", "chq", "cheque", "utr", "transaction id", "txn id"]


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


@register_parser
class UniversalPdfParser(BaseStatementParser):
    name = "universal_pdf"
    display_name = "Universal PDF Statement"

    @classmethod
    def can_parse(cls, file_bytes: bytes, filename: str) -> bool:
        return filename.lower().endswith(".pdf")

    def parse(self, file_bytes: bytes, filename: str) -> List[NormRow]:
        # 1. Security & extractable text check
        pdf = self._open_pdf(file_bytes)
        try:
            total_text = ""
            for p in pdf.pages:
                total_text += (p.extract_text() or "") + "\n"

            # Check if scanned / image-only (less than 30 alphanumeric characters)
            alphanumeric = re.findall(r"[A-Za-z0-9]", total_text)
            if len(alphanumeric) < 30:
                raise ScannedPdfError(
                    "this looks like a scanned PDF — OCR isn't supported yet, please upload a digital statement or CSV"
                )

            # 2. Stage A — Table extraction across every page
            rows = self._extract_from_tables(pdf)
            if rows:
                logger.info("UniversalPdfParser: extracted %d rows via table extraction", len(rows))
                return rows

            # 3. Stage B — Text-based fallback (GPay blocks, PhonePe blocks, line regex)
            rows = self._extract_from_text(total_text)
            if rows:
                logger.info("UniversalPdfParser: extracted %d rows via text block parsing", len(rows))
                return rows

            # 4. If neither produced rows, raise specific layout error
            raise UnsupportedLayoutError(
                f"unsupported statement layout — inspected {len(pdf.pages)} page(s) "
                f"but could not find a recognized transaction table or UPI transaction format"
            )
        finally:
            pdf.close()

    # ── Security Check ────────────────────────────────────────────────────────

    def _open_pdf(self, file_bytes: bytes) -> pdfplumber.PDF:
        try:
            # Check pypdf for encryption first if available
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                if reader.is_encrypted:
                    try:
                        reader.pages[0]
                    except Exception:
                        raise PasswordProtectedPdfError(
                            "password-protected PDF — please remove the password before uploading"
                        )
            except (PasswordProtectedPdfError, ScannedPdfError):
                raise
            except Exception:
                pass

            pdf = pdfplumber.open(io.BytesIO(file_bytes))
            if not pdf.pages:
                raise UnsupportedLayoutError("PDF statement contains no pages.")
            return pdf
        except (PasswordProtectedPdfError, ScannedPdfError, UnsupportedLayoutError):
            raise
        except Exception as e:
            err_msg = str(e).lower()
            if "password" in err_msg or "encrypt" in err_msg:
                raise PasswordProtectedPdfError(
                    "password-protected PDF — please remove the password before uploading"
                )
            raise UnsupportedLayoutError(f"could not open PDF: {e}")

    # ── Stage A: Table Extraction ─────────────────────────────────────────────

    def _extract_from_tables(self, pdf: pdfplumber.PDF) -> List[NormRow]:
        all_rows: List[NormRow] = []

        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                if not table or len(table) < 2:
                    continue

                header_idx, col_map = self._detect_table_header(table)
                if header_idx is None or not col_map:
                    continue

                for raw_row in table[header_idx + 1:]:
                    if not any(c and str(c).strip() for c in raw_row):
                        continue
                    parsed = self._parse_table_row(raw_row, col_map)
                    if parsed:
                        all_rows.append(parsed)

        return all_rows

    def _detect_table_header(self, table: list) -> Tuple[int | None, Dict[str, int] | None]:
        for idx in range(min(5, len(table))):
            row = table[idx]
            if not row:
                continue
            normed = [_norm(c) for c in row]

            col_map = {}
            for col_i, h in enumerate(normed):
                if not h:
                    continue
                if "date" not in col_map and any(kw in h for kw in _DATE_KEYWORDS):
                    col_map["date"] = col_i
                elif "debit" not in col_map and any(kw in h for kw in _DR_KEYWORDS):
                    col_map["debit"] = col_i
                elif "credit" not in col_map and any(kw in h for kw in _CR_KEYWORDS):
                    col_map["credit"] = col_i
                elif "amount" not in col_map and any(kw in h for kw in _AMT_KEYWORDS):
                    col_map["amount"] = col_i
                elif "drcr" not in col_map and any(kw == h or kw in h for kw in _DRCR_KEYWORDS):
                    col_map["drcr"] = col_i
                elif "status" not in col_map and any(kw in h for kw in _STAT_KEYWORDS):
                    col_map["status"] = col_i
                elif "time" not in col_map and any(kw in h for kw in _TIME_KEYWORDS):
                    col_map["time"] = col_i
                elif "ref" not in col_map and any(kw in h for kw in _REF_KEYWORDS):
                    col_map["ref"] = col_i
                elif "receiver" not in col_map and "receiver" in h:
                    col_map["receiver"] = col_i
                elif "sender" not in col_map and "sender" in h:
                    col_map["sender"] = col_i
                elif "narration" not in col_map and any(kw in h for kw in _NARR_KEYWORDS):
                    col_map["narration"] = col_i

            # Valid table requires at least a date and either (amount or debit or credit)
            has_date = "date" in col_map
            has_amt  = "amount" in col_map or "debit" in col_map or "credit" in col_map
            if has_date and has_amt:
                return idx, col_map

        return None, None

    def _parse_table_row(self, raw_row: list, col_map: Dict[str, int]) -> NormRow | None:
        def get_val(key: str) -> str:
            idx = col_map.get(key)
            if idx is None or idx >= len(raw_row):
                return ""
            return str(raw_row[idx] or "").strip()

        # Check status (skip failed transactions)
        stat = get_val("status").upper()
        if stat and any(f in stat for f in ["FAIL", "DECLINED", "REJECT"]):
            return None

        # Parse date
        date_str = get_val("date")
        parsed_date = _parse_date(date_str)
        if not parsed_date:
            return None

        # Parse time
        time_str = get_val("time")
        parsed_time = _parse_time(time_str) if time_str else None

        # Parse amount and debit/credit
        is_debit = True
        amount = Decimal("0")

        if "debit" in col_map or "credit" in col_map:
            dr_str = get_val("debit")
            cr_str = get_val("credit")
            dr_amt = _clean_amount(dr_str)
            cr_amt = _clean_amount(cr_str)
            if dr_amt > 0:
                amount = dr_amt
                is_debit = True
            elif cr_amt > 0:
                amount = cr_amt
                is_debit = False
            elif "amount" in col_map:
                amount = _clean_amount(get_val("amount"))
        else:
            amt_str = get_val("amount")
            amount = _clean_amount(amt_str)
            amt_lower = amt_str.lower()
            if "(dr)" in amt_lower or " dr" in amt_lower:
                is_debit = True
            elif "(cr)" in amt_lower or " cr" in amt_lower:
                is_debit = False
            elif "drcr" in col_map:
                drcr_val = get_val("drcr").upper()
                is_debit = not ("CR" in drcr_val or "CREDIT" in drcr_val or "COLLECT" in drcr_val)

        if amount <= 0:
            return None

        # Narration / Payee extraction
        receiver = get_val("receiver")
        sender = get_val("sender")
        narration = get_val("narration")
        ref_id = get_val("ref")

        if receiver or sender:
            # UPI statement with sender/receiver columns
            desc_text = f"{receiver} {sender}".strip()
            payee = _extract_payee(receiver if is_debit else sender)
        elif narration:
            desc_text = narration
            payee = _extract_payee(narration)
        else:
            desc_text = " | ".join(str(c or "") for c in raw_row)
            payee = _extract_payee(desc_text)

        upi_id = _extract_upi_id(desc_text) or (ref_id if "@" in ref_id else "")
        raw_text = " | ".join(str(c or "") for c in raw_row)

        return {
            "date":       parsed_date,
            "time":       parsed_time,
            "amount":     amount,
            "is_debit":   is_debit,
            "payee_name": payee or "Unknown Payee",
            "upi_id":     upi_id,
            "remark":     desc_text[:512],
            "raw_text":   raw_text[:1000],
        }

    # ── Stage B: Text Extraction (Google Pay, PhonePe, Line Regex) ───────────

    def _extract_from_text(self, text: str) -> List[NormRow]:
        rows: List[NormRow] = []

        # B.1: Google Pay text format
        gpay_pattern = re.compile(
            r"(?P<date>\d{1,2}\s*[A-Za-z]+,?\s*\d{4})\s+"
            r"(?P<action>Paid\s*to|Received\s*from)\s*"
            r"(?P<payee>[^\u20b9\n\r]+?)\s*"
            r"[\u20b9Rs\.]*\s*(?P<amount>\d+(?:,\d+)*(?:\.\d+)?)\s*\n"
            r"(?:\s*(?P<time>\d{1,2}:\d{2}\s*(?:AM|PM))\s*)?"
            r"(?:UPI\s*Transaction\s*ID\s*:\s*(?P<upi_txn>\d+))?",
            re.IGNORECASE,
        )
        for m in gpay_pattern.finditer(text):
            d = m.groupdict()
            parsed_date = _parse_date(d.get("date", ""))
            if not parsed_date:
                continue
            amt = _clean_amount(d.get("amount", "0"))
            if amt <= 0:
                continue
            action = (d.get("action") or "").lower()
            is_debit = "paid" in action
            payee_raw = (d.get("payee") or "").strip()
            payee = re.sub(r"^(?:to|from)\s*", "", payee_raw, flags=re.IGNORECASE).strip()
            time_str = d.get("time") or ""
            parsed_time = _parse_time(time_str) if time_str else None

            rows.append({
                "date":       parsed_date,
                "time":       parsed_time,
                "amount":     amt,
                "is_debit":   is_debit,
                "payee_name": payee or "Unknown Payee",
                "upi_id":     d.get("upi_txn") or "",
                "remark":     f"{d.get('action', '')} {payee}",
                "raw_text":   m.group(0)[:1000],
            })

        if rows:
            return rows

        # B.2: PhonePe text card format
        phonepe_pattern = re.compile(
            r"(?P<date>[A-Za-z]{3}\s+\d{1,2},\s*\d{4})\s+"
            r"(?P<action>Paid\s+to|Received\s+from)\s+"
            r"(?P<payee>[^\n]+?)\s+"
            r"(?P<type>DEBIT|CREDIT)\s+"
            r"[₹Rs\.]*\s*(?P<amount>[\d,]+(?:\.\d+)?)\s*\n"
            r"(?:\s*(?P<time>\d{1,2}:\d{2}\s*(?:AM|PM))\s*)?"
            r"(?:Transaction\s+ID\s+(?P<txn_id>\S+))?",
            re.IGNORECASE,
        )
        for m in phonepe_pattern.finditer(text):
            d = m.groupdict()
            parsed_date = _parse_date(d.get("date", ""))
            if not parsed_date:
                continue
            amt = _clean_amount(d.get("amount", "0"))
            if amt <= 0:
                continue
            is_debit = (d.get("type", "").upper() == "DEBIT")
            time_str = d.get("time") or ""
            parsed_time = _parse_time(time_str) if time_str else None

            rows.append({
                "date":       parsed_date,
                "time":       parsed_time,
                "amount":     amt,
                "is_debit":   is_debit,
                "payee_name": (d.get("payee") or "").strip() or "Unknown Payee",
                "upi_id":     d.get("txn_id") or "",
                "remark":     f"{d.get('action', '')} {d.get('payee', '')}",
                "raw_text":   m.group(0)[:1000],
            })

        if rows:
            return rows

        # B.3: Flexible line-by-line fallback
        # Looks for lines having a date + amount (with optional Dr/Cr or Rs/₹) + narration
        line_pattern = re.compile(
            r"(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{2,4})"
            r".*?"
            r"(?:(?P<currency>[₹$]|Rs\.?)\s*)?(?P<amount>[0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?)"
            r"(?:\s*(?P<drcr>\(?(?:Dr|Cr|DR|CR)\)?))?",
            re.IGNORECASE,
        )

        for line in text.splitlines():
            line = line.strip()
            if len(line) < 10:
                continue
            m = line_pattern.search(line)
            if not m:
                continue
            parsed_date = _parse_date(m.group("date"))
            if not parsed_date:
                continue
            amt = _clean_amount(m.group("amount"))
            if amt <= 0:
                continue
            drcr = (m.group("drcr") or "").upper()
            is_debit = not ("CR" in drcr)

            upi_id = _extract_upi_id(line)
            payee = _extract_payee(line)

            rows.append({
                "date":       parsed_date,
                "time":       None,
                "amount":     amt,
                "is_debit":   is_debit,
                "payee_name": payee or "Unknown Payee",
                "upi_id":     upi_id,
                "remark":     line[:512],
                "raw_text":   line[:1000],
            })

        return rows
