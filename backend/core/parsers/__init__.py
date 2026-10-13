"""
parsers/__init__.py
Imports all parser modules so their @register_parser decorators fire,
and exposes the `parse_statement()` dispatcher.
"""

from __future__ import annotations

import logging
from typing import IO, List, Tuple

from .base import NormRow, get_registry
from .exceptions import (
    StatementParseError,
    PasswordProtectedPdfError,
    ScannedPdfError,
    UnsupportedLayoutError,
)

# Import parsers in priority order
from . import phonepe_pdf       # noqa: F401  — registers PhonePePdfParser
from . import slice_pdf         # noqa: F401  — registers SlicePdfParser
from . import hdfc_pdf          # noqa: F401  — registers HdfcPdfParser
from . import sbi_csv           # noqa: F401  — registers SbiCsvParser
from . import generic_csv       # noqa: F401  — registers GenericCsvParser
from . import universal_pdf     # noqa: F401  — registers UniversalPdfParser

logger = logging.getLogger(__name__)

__all__ = [
    "parse_statement",
    "get_registry",
    "StatementParseError",
    "PasswordProtectedPdfError",
    "ScannedPdfError",
    "UnsupportedLayoutError",
]


def parse_statement(file_bytes: bytes, filename: str) -> Tuple[List[NormRow], str]:
    """
    Detect the correct parser and return (normalised_rows, format_name).

    Detection order:
      1. Iterate registered parsers.
      2. Call cls.can_parse() — if True, attempt parser.parse().
      3. If parse() succeeds and yields rows > 0, return (rows, name).
      4. If parse() returns 0 rows, continue to next eligible parser.
      5. Fallback to UniversalPdfParser for PDFs or GenericCsvParser for CSVs.

    Raises:
      PasswordProtectedPdfError, ScannedPdfError, UnsupportedLayoutError on failure.
    """
    registry = get_registry()
    last_error: Exception | None = None

    # First pass: try specialized parsers before universal_pdf / generic_csv
    specialized = [p for p in registry if p.name not in ("universal_pdf", "generic_csv")]
    fallbacks   = [p for p in registry if p.name in ("universal_pdf", "generic_csv")]

    for parser_cls in specialized + fallbacks:
        try:
            if parser_cls.can_parse(file_bytes, filename):
                parser = parser_cls()
                rows = parser.parse(file_bytes, filename)
                if rows:
                    logger.info(
                        "parse_statement: %s parsed by '%s' with %d rows",
                        filename, parser_cls.name, len(rows),
                    )
                    return rows, parser_cls.name
                else:
                    logger.warning("Parser %s matched %s but extracted 0 rows. Trying next parser...", parser_cls.name, filename)
        except (PasswordProtectedPdfError, ScannedPdfError) as e:
            # Fatal security / document format errors should not be masked
            raise
        except Exception as e:
            logger.warning("Parser %s error for %s: %s", parser_cls.name, filename, e)
            last_error = e

    if last_error and isinstance(last_error, StatementParseError):
        raise last_error

    if filename.lower().endswith(".pdf"):
        raise UnsupportedLayoutError(
            f"unsupported statement layout — could not extract transactions from '{filename}'. "
            f"Please ensure it is a digital bank/UPI account statement."
        )
    elif filename.lower().endswith((".csv", ".tsv", ".txt")):
        raise UnsupportedLayoutError(
            f"could not find valid transaction header or data in CSV file '{filename}'."
        )

    raise UnsupportedLayoutError(f"unsupported file format for '{filename}'. Please upload a PDF or CSV statement.")
