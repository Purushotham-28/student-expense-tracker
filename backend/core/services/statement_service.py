"""
services/statement_service.py
Orchestrates: save file → call parser → persist Transaction rows → update Statement.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import IO

from django.contrib.auth.models import User

from ..models import Statement, Transaction
from ..parsers import parse_statement

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "csv"}
MAX_FILE_SIZE_MB = 20


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_upload(filename: str, size_bytes: int) -> str | None:
    """Return an error string or None if valid."""
    ext = _ext(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return f"Unsupported file type '.{ext}'. Please upload a PDF or CSV statement."
    if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
        return f"File too large. Maximum allowed size is {MAX_FILE_SIZE_MB} MB."
    return None


def process_uploaded_statement(
    user: User,
    file_obj: IO[bytes],
    filename: str,
) -> Statement:
    """
    Full pipeline:
      1. Create Statement record (status=processing).
      2. Read file bytes.
      3. Detect format + parse rows.
      4. Bulk-create Transaction objects.
      5. Update Statement fields (status, counts, date range).
    Returns the Statement instance.
    """
    ext = _ext(filename)

    # 1 — Create Statement in processing state
    stmt = Statement.objects.create(
        user=user,
        file=file_obj,
        original_filename=filename,
        file_type=ext,
        status=Statement.Status.PROCESSING,
    )

    try:
        # 2 — Read bytes for parsing (file already saved by Django storage)
        stmt.file.seek(0)
        file_bytes = stmt.file.read()

        # 3 — Parse
        rows, format_name = parse_statement(file_bytes, filename)

        if not rows:
            stmt.status = Statement.Status.FAILED
            stmt.error_message = (
                "No transactions could be extracted. "
                "Ensure the file is a valid bank statement."
            )
            stmt.bank_format = format_name
            stmt.save(update_fields=["status", "error_message", "bank_format"])
            return stmt

        # 4 — Bulk-create Transaction rows
        tx_objects = [
            Transaction(
                statement=stmt,
                user=user,
                date=row.get("date"),
                time=row.get("time"),
                amount=row["amount"],
                is_debit=row.get("is_debit", True),
                payee_name=row.get("payee_name", ""),
                upi_id=row.get("upi_id", ""),
                remark=row.get("remark", ""),
                raw_text=row.get("raw_text", ""),
            )
            for row in rows
        ]
        Transaction.objects.bulk_create(tx_objects, batch_size=500)

        # 5 — Run hybrid categorization on each transaction
        from .categorization_service import categorize_transaction
        for tx in stmt.transactions.all():
            try:
                categorize_transaction(tx, save=True)
            except Exception as cat_err:
                logger.warning("Failed auto-categorizing transaction %s: %s", tx.pk, cat_err)

        # 6 — Compute date range from rows
        dates = [r["date"] for r in rows if r.get("date")]
        date_from = min(dates) if dates else None
        date_to   = max(dates) if dates else None

        stmt.status            = Statement.Status.DONE
        stmt.bank_format       = format_name
        stmt.transaction_count = len(rows)
        stmt.date_from         = date_from
        stmt.date_to           = date_to
        stmt.processed_at      = datetime.now(tz=timezone.utc)
        stmt.save(update_fields=[
            "status", "bank_format", "transaction_count",
            "date_from", "date_to", "processed_at",
        ])

    except Exception as e:
        logger.error("process_uploaded_statement failed for stmt #%s: %s", stmt.pk, e, exc_info=True)
        stmt.status = Statement.Status.FAILED
        stmt.error_message = str(e)
        stmt.save(update_fields=["status", "error_message"])

    return stmt
