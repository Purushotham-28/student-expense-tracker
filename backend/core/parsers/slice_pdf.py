"""
parsers/slice_pdf.py — Parser for Slice (Credit Card / Neobank / Small Finance Bank) statements.

Slice PDF statements do not use standard PDF table grids. Instead, transactions are
rendered as formatted text lines per page:

Line structure:
  [Date: e.g. 23 Jul '26] [Details / Merchant / UPI reference] [Ref No.] [Amount: -₹X (debit) or ₹X (credit)] [Balance]
  (Followed by optional continuation lines with IFSC / VPA details)

Header / Footer identifiers:
  - "slice small finance bank"
  - "help@slice.bank.in"
  - Statement period: "01 Jul '26 - 30 Sep '26"
"""

from __future__ import annotations

import io
import re
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Tuple

import pdfplumber

from .base import (
    BaseStatementParser,
    NormRow,
    register_parser,
)

logger = logging.getLogger(__name__)


def _clean_slice_payee(details_text: str) -> Tuple[str, str, str]:
    """
    Extracts clean payee name, UPI ID, and UTR from Slice transaction details string.
    """
    # Normalize broken words from PDF text extraction
    text = details_text.strip()
    text = re.sub(r"fro\s+m\s+slice", "from slice", text, flags=re.IGNORECASE)
    text = re.sub(r"Paym\s+ent\s+from", "Payment from", text, flags=re.IGNORECASE)
    text = re.sub(r"Pay\s+to", "Pay to", text, flags=re.IGNORECASE)

    # 1. UPI transaction format:
    # e.g. UPI-Debit-620487074829-MALLETHULA SHIVARU-SBIN0020609-lucky9398@ibl-Payment from slice
    # or UPI-Debit-621378889582-DMART AVENUE SUPERMA-HDFC0MERUPI-dmartavenuesupermart.27218910@hdfcbank
    m_upi_seg = re.match(
        r"UPI-(?:Debit|Credit)-([A-Za-z0-9]+)-([^-]+?)(?:-([A-Z0-9]{4,11}))?-(.+)$",
        text,
        re.IGNORECASE,
    )
    if m_upi_seg:
        utr = m_upi_seg.group(1).strip()
        raw_payee = m_upi_seg.group(2).strip()
        trailing = m_upi_seg.group(4).strip() if m_upi_seg.group(4) else ""

        # Extract UPI ID from trailing (stop at hyphen or extra remark)
        m_vpa = re.search(r"([a-zA-Z0-9.\-_]+@[a-zA-Z0-9]+)", trailing)
        upi_id = m_vpa.group(1).strip() if m_vpa else ""

        payee = re.sub(r"\s+", " ", raw_payee).strip()
        return payee, upi_id, utr

    # Simpler UPI format fallback: "UPI-Debit-12345-Merchant Name-..."
    m_upi_simple = re.search(r"UPI-(?:Debit|Credit)-[A-Za-z0-9]+-([^-]+)", text, re.IGNORECASE)
    if m_upi_simple:
        raw_payee = m_upi_simple.group(1).strip()
        m_vpa = re.search(r"([a-zA-Z0-9.\-_]+@[a-zA-Z0-9]+)", text)
        upi_id = m_vpa.group(1).strip() if m_vpa else ""
        return raw_payee, upi_id, ""

    # 2. Add Funds / Bill payment: e.g. "620400033798-Add Funds", "621400161350-Bill payment"
    m_prefix = re.match(r"^(\d+)-([A-Za-z\s]+)", text)
    if m_prefix:
        utr = m_prefix.group(1).strip()
        payee = m_prefix.group(2).strip()
        return payee, "", utr

    # 3. Emergency fund
    if "Emergency fund" in text or "Emergency Fund" in text:
        if "Transfer from" in text:
            return "Transfer from Emergency Fund", "", ""
        return "Emergency Fund Deposit", "", ""

    # 4. Round ups (Slice micro-savings)
    if text.startswith("Round ups"):
        return "Round Ups (Slice Savings)", "", ""

    # 5. Interest credit
    if "Interest Cr" in text:
        return "Interest Credit", "", ""

    # Generic VPA extraction if present anywhere
    m_vpa = re.search(r"([a-zA-Z0-9.\-_]+@[a-zA-Z0-9]+)", text)
    upi_id = m_vpa.group(1).strip() if m_vpa else ""

    first_part = text.split("-")[0].strip()
    return first_part[:50], upi_id, ""


@register_parser
class SlicePdfParser(BaseStatementParser):
    name = "slice_pdf"
    display_name = "Slice Statement (PDF)"

    DATE_PATTERN = re.compile(r"^(\d{1,2}\s+[A-Za-z]{3}\s+'\d{2})\s+(.+)$")
    AMT_BAL_PATTERN = re.compile(r"(-?₹[\d,]+(?:\.\d{1,2})?)\s+(₹[\d,]+(?:\.\d{1,2})?)$")
    PERIOD_HEADER_PATTERN = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+'\d{2}\s*-\s*\d{1,2}\s+[A-Za-z]{3}\s+'\d{2}$")

    @classmethod
    def can_parse(cls, file_bytes: bytes, filename: str) -> bool:
        if not filename.lower().endswith(".pdf"):
            return False

        # Filename hint
        if "slice" in filename.lower():
            return True

        # Sniff first two pages
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                if not pdf.pages:
                    return False

                sample_text = ""
                for p in pdf.pages[:2]:
                    sample_text += (p.extract_text() or "") + "\n"

                sample_lower = sample_text.lower()
                if (
                    "slice small finance bank" in sample_lower
                    or "slice.bank.in" in sample_lower
                    or ("slice" in sample_lower and "opening balance" in sample_lower)
                ):
                    return True

                # Check line pattern match
                lines = sample_text.split("\n")
                match_count = 0
                for line in lines:
                    line_str = line.strip()
                    if cls.DATE_PATTERN.match(line_str) and cls.AMT_BAL_PATTERN.search(line_str):
                        match_count += 1
                        if match_count >= 2:
                            return True
        except Exception as e:
            logger.debug("SlicePdfParser.can_parse check failed: %s", e)
            return False

        return False

    def parse(self, file_bytes: bytes, filename: str) -> List[NormRow]:
        """
        Extract transactions from Slice PDF statement by parsing line-by-line across all pages.
        """
        rows: List[NormRow] = []
        transactions_raw = []
        current_tx = None

        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    for line in text.split("\n"):
                        line_str = line.strip()
                        if not line_str:
                            continue

                        # Skip header, balance summary, footer, and page counter lines
                        if (
                            "Need help?" in line_str
                            or "DATE DETAILS" in line_str
                            or "Opening balance" in line_str
                            or "Customer ID" in line_str
                            or "Phone " in line_str
                            or "Address " in line_str
                            or line_str.startswith("Opening date")
                            or self.PERIOD_HEADER_PATTERN.match(line_str)
                            or re.match(r"^\d+/\d+$", line_str)
                        ):
                            continue

                        # Check if line initiates a transaction (starts with Date)
                        date_match = self.DATE_PATTERN.match(line_str)
                        if date_match:
                            rest = date_match.group(2)
                            amt_match = self.AMT_BAL_PATTERN.search(rest)
                            if amt_match:
                                if current_tx:
                                    transactions_raw.append(current_tx)

                                date_str = date_match.group(1)
                                amt_str = amt_match.group(1)
                                bal_str = amt_match.group(2)
                                first_line_rest = rest[:amt_match.start()].strip()

                                # Separate details from trailing Ref No
                                m_ref = re.search(r"^(.*?)(?:\s+(\d{9,}))\s*$", first_line_rest)
                                if m_ref:
                                    desc_p = m_ref.group(1).strip()
                                    ref_no = m_ref.group(2).strip()
                                else:
                                    desc_p = first_line_rest
                                    ref_no = ""

                                current_tx = {
                                    "page": page_idx + 1,
                                    "date_str": date_str,
                                    "amt_str": amt_str,
                                    "bal_str": bal_str,
                                    "ref_no": ref_no,
                                    "desc_parts": [desc_p],
                                }
                                continue

                        # Continuation lines for multi-line transaction description
                        if (
                            current_tx
                            and not line_str.startswith("slice small finance")
                            and not re.match(r"^\d+/\d+$", line_str)
                        ):
                            current_tx["desc_parts"].append(line_str)

                if current_tx:
                    transactions_raw.append(current_tx)

        except Exception as e:
            logger.error("Failed to read Slice PDF statement: %s", e)
            return []

        # Convert raw transaction blocks into NormRow format
        for tx in transactions_raw:
            try:
                # 1. Date (e.g. "23 Jul '26")
                tx_date = datetime.strptime(tx["date_str"], "%d %b '%y").date()

                # 2. Amount and Debit flag
                clean_amt_str = tx["amt_str"].replace("₹", "").replace(",", "").strip()
                is_debit = clean_amt_str.startswith("-")
                amount = Decimal(clean_amt_str.lstrip("-"))

                # 3. Payee, UPI ID, UTR
                full_desc = "".join(tx["desc_parts"])
                payee_name, upi_id, utr = _clean_slice_payee(full_desc)

                # 4. Remark
                ref_no = tx["ref_no"] or utr
                remark_parts = [payee_name]
                if ref_no:
                    remark_parts.append(f"Ref:{ref_no}")
                remark = " | ".join(p for p in remark_parts if p)

                rows.append({
                    "date": tx_date,
                    "time": None,
                    "amount": amount,
                    "is_debit": is_debit,
                    "payee_name": payee_name,
                    "upi_id": upi_id,
                    "remark": remark,
                    "raw_text": f"{tx['date_str']} {full_desc} {tx['amt_str']} {tx['bal_str']}"[:300].strip(),
                })
            except Exception as row_err:
                logger.debug("Failed to normalize Slice transaction: %s (%s)", tx, row_err)

        logger.info("SlicePdfParser parsed %d rows from '%s'", len(rows), filename)
        return rows
