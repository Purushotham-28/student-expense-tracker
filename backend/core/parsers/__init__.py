"""
parsers/__init__.py
Imports all parser modules so their @register_parser decorators fire,
and exposes the `parse_statement()` dispatcher.
"""

from __future__ import annotations

import logging
from typing import IO, List, Tuple

from .base import NormRow, get_registry

# Import parsers in priority order (specific before generic)
from . import phonepe_pdf       # noqa: F401  — registers PhonePePdfParser
from . import hdfc_pdf          # noqa: F401  — registers HdfcPdfParser
from . import sbi_csv           # noqa: F401  — registers SbiCsvParser
from . import generic_csv       # noqa: F401  — registers GenericCsvParser

logger = logging.getLogger(__name__)

__all__ = ["parse_statement", "get_registry"]


def parse_statement(file_bytes: bytes, filename: str) -> Tuple[List[NormRow], str]:
    """
    Detect the correct parser and return (normalised_rows, format_name).

    Detection order:
      1. Iterate the registry (ordered by registration).
      2. Call cls.can_parse() — first True wins.
      3. Fall back to GenericCsvParser if the file is a CSV.

    Returns:
        (rows, format_name) — rows is empty list on failure.
    """
    registry = get_registry()
    for parser_cls in registry:
        try:
            if parser_cls.can_parse(file_bytes, filename):
                parser = parser_cls()
                rows = parser.parse(file_bytes, filename)
                logger.info(
                    "parse_statement: %s selected '%s', extracted %d rows",
                    filename, parser_cls.name, len(rows),
                )
                return rows, parser_cls.name
        except Exception as e:
            logger.warning("Parser %s raised during can_parse: %s", parser_cls.name, e)

    logger.warning("parse_statement: no parser matched for '%s'", filename)
    return [], "unknown"
