"""
parsers/exceptions.py — Structured exceptions for statement parsing.
"""

class StatementParseError(Exception):
    """Base exception for parsing failures."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PasswordProtectedPdfError(StatementParseError):
    """Raised when a PDF requires a password to open."""
    def __init__(self, message: str = "password-protected PDF — please remove the password before uploading", details: dict | None = None):
        super().__init__(message, details)


class ScannedPdfError(StatementParseError):
    """Raised when a PDF contains no extractable digital text (scanned / image-only)."""
    def __init__(self, message: str = "this looks like a scanned PDF — OCR isn't supported yet, please upload a digital statement or CSV", details: dict | None = None):
        super().__init__(message, details)


class UnsupportedLayoutError(StatementParseError):
    """Raised when the layout cannot be parsed into transactions."""
    pass


class EmptyStatementError(StatementParseError):
    """Raised when file parses but contains zero transactions."""
    pass
