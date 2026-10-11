"""
parsers/phonepe_pdf.py — Parser for PhonePe UPI PDF transaction statements.

PhonePe PDF statements are system-generated transaction summaries with
visual card blocks rather than tabular grid lines.

Format structure per transaction:
  [Date: e.g. Jul 22, 2026] [Paid to / Received from ...] [DEBIT / CREDIT] [₹Amount]
  [Time: e.g. 05:50 AM] Transaction ID [T26...]
  UTR No. [12-digit number]
  Paid by / Credited to [Account reference]
"""

from __future__ import annotations

import io
import re
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List

import pdfplumber

from .base import (
    BaseStatementParser,
    NormRow,
    _extract_upi_id,
    register_parser,
)

logger = logging.getLogger(__name__)


@register_parser
class PhonePePdfParser(BaseStatementParser):
    name = "phonepe_pdf"
    display_name = "PhonePe UPI PDF Statement"

    @classmethod
    def can_parse(cls, file_bytes: bytes, filename: str) -> bool:
        if not filename.lower().endswith(".pdf"):
            return False

        # Check filename hint
        fn_lower = filename.lower()
        if "phonepe" in fn_lower:
            return True

        # Quick text scan for PhonePe identifiers
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                if not pdf.pages:
                    return False
                first_text = (pdf.pages[0].extract_text() or "").lower()
                return (
                    "phonepe" in first_text
                    or "support.phonepe.com" in first_text
                    or ("transaction statement for" in first_text and "utr no." in first_text)
                )
        except Exception as e:
            logger.debug("PhonePe can_parse check failed: %s", e)
            return False

    def parse(self, file_bytes: bytes, filename: str) -> List[NormRow]:
        """
        Extract transactions from PhonePe PDF statement.
        """
        rows: List[NormRow] = []

        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        except Exception as e:
            logger.error("Failed to read PDF with pdfplumber: %s", e)
            return []

        # PhonePe transactions begin with Date e.g. "Jul 22, 2026" or "May 14, 2026"
        blocks = re.split(r"\n(?=[A-Za-z]{3}\s+\d{1,2},\s+\d{4})", full_text)

        for block in blocks:
            if "Transaction ID" not in block:
                continue

            try:
                # 1. Date
                m_date = re.search(r"([A-Za-z]{3}\s+\d{1,2},\s+\d{4})", block)
                if not m_date:
                    continue
                try:
                    tx_date = datetime.strptime(m_date.group(1), "%b %d, %Y").date()
                except ValueError:
                    continue

                # 2. Time
                m_time = re.search(r"(\d{1,2}:\d{2}\s+(?:AM|PM))", block, re.IGNORECASE)
                tx_time = None
                if m_time:
                    try:
                        tx_time = datetime.strptime(m_time.group(1).upper(), "%I:%M %p").time()
                    except ValueError:
                        pass

                # 3. Type (Debit vs Credit)
                is_debit = True
                if re.search(r"\bCREDIT\b", block, re.IGNORECASE):
                    is_debit = False
                elif re.search(r"\bDEBIT\b", block, re.IGNORECASE):
                    is_debit = True
                elif "received from" in block.lower():
                    is_debit = False

                # 4. Amount
                amt_str = "0"
                m_amt = re.search(r"(?:DEBIT|CREDIT)\s*[₹?Rs.]*\s*([\d,]+(?:\.\d+)?)", block, re.IGNORECASE)
                if m_amt:
                    amt_str = m_amt.group(1).replace(",", "")
                else:
                    m_amt_alt = re.search(r"[₹?]\s*([\d,]+(?:\.\d+)?)", block)
                    if m_amt_alt:
                        amt_str = m_amt_alt.group(1).replace(",", "")

                try:
                    amount = Decimal(amt_str)
                except InvalidOperation:
                    amount = Decimal("0")

                # 5. Payee Name & Remark
                lines = [line.strip() for line in block.split("\n") if line.strip()]
                first_line = lines[0] if lines else ""
                payee_name = "PhonePe Transaction"

                m_payee = re.search(
                    r"(?:Paid to|Received from|Transfer to|Payment to|Refund from)\s+(.*?)(?:\s+(?:DEBIT|CREDIT)|$)",
                    first_line,
                    re.IGNORECASE,
                )
                if m_payee and m_payee.group(1).strip():
                    payee_name = m_payee.group(1).strip()
                elif len(lines) > 1:
                    line2 = lines[1]
                    cleaned_line2 = re.sub(
                        r"^\d{1,2}:\d{2}\s+(?:AM|PM)\s*", "", line2, flags=re.IGNORECASE
                    ).strip()
                    if (
                        cleaned_line2
                        and not cleaned_line2.startswith("Transaction ID")
                        and not cleaned_line2.startswith("UTR")
                    ):
                        payee_name = cleaned_line2

                # 6. UPI ID if present
                upi_id = _extract_upi_id(block) or ""

                # 7. Transaction ID / UTR for remark
                m_txid = re.search(r"Transaction ID\s+([A-Za-z0-9]+)", block)
                tx_id = m_txid.group(1) if m_txid else ""

                m_utr = re.search(r"UTR No\.\s+(\d+)", block)
                utr = m_utr.group(1) if m_utr else ""

                remark_parts = []
                if payee_name:
                    remark_parts.append(payee_name)
                if utr:
                    remark_parts.append(f"UTR:{utr}")
                if tx_id:
                    remark_parts.append(f"TxID:{tx_id}")
                remark = " | ".join(remark_parts)

                rows.append({
                    "date": tx_date,
                    "time": tx_time,
                    "amount": amount,
                    "is_debit": is_debit,
                    "payee_name": payee_name,
                    "upi_id": upi_id,
                    "remark": remark,
                    "raw_text": block[:300].strip(),
                })

            except Exception as row_err:
                logger.debug("Failed to parse PhonePe block: %s (%s)", block[:100], row_err)

        logger.info("PhonePePdfParser parsed %d rows from '%s'", len(rows), filename)
        return rows
