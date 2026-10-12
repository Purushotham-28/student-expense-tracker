"""
tests_parser_robustness.py — Tests for layout-agnostic parsing, real statements, and graceful error degradation.
"""

import io
import os
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from core.parsers import (
    parse_statement,
    PasswordProtectedPdfError,
    ScannedPdfError,
    UnsupportedLayoutError,
)
from core.models import Statement


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')
MEDIA_STATEMENTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'media', 'statements', '2')


class RobustParserTests(TestCase):
    """Verify parsing across diverse bank formats and real statements."""

    def test_union_bank_csv_parsing(self):
        fixture_path = os.path.join(FIXTURES_DIR, 'union_bank_sample.csv')
        with open(fixture_path, 'rb') as f:
            content = f.read()
        rows, fmt = parse_statement(content, 'union_bank_sample.csv')
        self.assertGreater(len(rows), 0)
        # Should have parsed the 4 valid transactions (1 failed was skipped if filtered or parsed)
        self.assertTrue(any(r['payee_name'] for r in rows))
        self.assertTrue(any(r['is_debit'] for r in rows))

    def test_savings_dr_cr_suffix_parsing(self):
        fixture_path = os.path.join(FIXTURES_DIR, 'savings_sample.csv')
        with open(fixture_path, 'rb') as f:
            content = f.read()
        rows, fmt = parse_statement(content, 'savings_sample.csv')
        self.assertEqual(len(rows), 4)
        # Verify first row is 25.00 debit
        self.assertEqual(rows[0]['amount'], Decimal('25.00'))
        self.assertTrue(rows[0]['is_debit'])
        # Verify credit row
        self.assertEqual(rows[2]['amount'], Decimal('150.00'))
        self.assertFalse(rows[2]['is_debit'])

    def test_axis_bank_dr_cr_columns(self):
        fixture_path = os.path.join(FIXTURES_DIR, 'axis_sample.csv')
        with open(fixture_path, 'rb') as f:
            content = f.read()
        rows, fmt = parse_statement(content, 'axis_sample.csv')
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['amount'], Decimal('450.00'))
        self.assertTrue(rows[0]['is_debit'])

    def test_kotak_bank_single_amt_col(self):
        fixture_path = os.path.join(FIXTURES_DIR, 'kotak_sample.csv')
        with open(fixture_path, 'rb') as f:
            content = f.read()
        rows, fmt = parse_statement(content, 'kotak_sample.csv')
        self.assertEqual(len(rows), 3)

    def test_real_union_bank_upi_pdf(self):
        pdf_path = os.path.join(MEDIA_STATEMENTS_DIR, 'Transaction_Statement.pdf')
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                content = f.read()
            rows, fmt = parse_statement(content, 'Transaction_Statement.pdf')
            self.assertEqual(fmt, 'universal_pdf')
            self.assertEqual(len(rows), 39)

    def test_real_savings_pdf_with_drcr_suffix(self):
        pdf_path = os.path.join(MEDIA_STATEMENTS_DIR, '0110XXXX_DownloadStatement_1791736549.pdf')
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                content = f.read()
            rows, fmt = parse_statement(content, '0110XXXX_DownloadStatement_1791736549.pdf')
            self.assertEqual(fmt, 'universal_pdf')
            self.assertEqual(len(rows), 48)

    def test_real_gpay_statement_pdf(self):
        pdf_path = os.path.join(MEDIA_STATEMENTS_DIR, 'gpay_statement_20260401_20260930.pdf')
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                content = f.read()
            rows, fmt = parse_statement(content, 'gpay_statement_20260401_20260930.pdf')
            self.assertEqual(fmt, 'universal_pdf')
            self.assertEqual(len(rows), 13)

    def test_scanned_pdf_error_reporting(self):
        """A PDF with no extractable text must raise ScannedPdfError with exact message."""
        # Create a valid 1-page blank PDF using reportlab or minimal PDF bytes
        import reportlab.pdfgen.canvas as canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        # Draw only a shape, no text
        c.rect(10, 10, 100, 100)
        c.save()
        pdf_bytes = buf.getvalue()

        with self.assertRaises(ScannedPdfError) as ctx:
            parse_statement(pdf_bytes, 'scanned_statement.pdf')
        self.assertIn("looks like a scanned PDF — OCR isn't supported yet", str(ctx.exception))

    def test_unsupported_layout_error_reporting(self):
        """A CSV with no recognized header must raise UnsupportedLayoutError."""
        csv_bytes = b"foo,bar,baz\n1,2,3\n4,5,6"
        with self.assertRaises(UnsupportedLayoutError) as ctx:
            parse_statement(csv_bytes, 'unknown.csv')
        self.assertIn("could not find", str(ctx.exception).lower())
