import os
from datetime import date
from decimal import Decimal
from django.test import TestCase

from core.parsers import parse_statement, UnsupportedLayoutError
from core.parsers.slice_pdf import SlicePdfParser


class SliceParserTests(TestCase):
    def setUp(self):
        self.fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "slice_sample.pdf"
        )
        with open(self.fixture_path, "rb") as f:
            self.file_bytes = f.read()

    def test_slice_can_parse(self):
        """Verify SlicePdfParser correctly detects the Slice statement."""
        self.assertTrue(SlicePdfParser.can_parse(self.file_bytes, "slice_sample.pdf"))
        self.assertTrue(SlicePdfParser.can_parse(self.file_bytes, "statement.pdf"))

    def test_slice_parse_statement_dispatcher(self):
        """Verify parse_statement auto-selects slice_pdf and extracts all rows."""
        rows, parser_name = parse_statement(self.file_bytes, "slice_sample.pdf")
        self.assertEqual(parser_name, "slice_pdf")
        self.assertEqual(len(rows), 255)

    def test_slice_known_rows_accuracy(self):
        """Verify specific known rows parse to the exact date, amount, debit flag, and payee."""
        parser = SlicePdfParser()
        rows = parser.parse(self.file_bytes, "slice_sample.pdf")

        # Row 1: 23 Jul '26 Add Funds ₹50 (Credit)
        row1 = rows[0]
        self.assertEqual(row1["date"], date(2026, 7, 23))
        self.assertEqual(row1["amount"], Decimal("50"))
        self.assertFalse(row1["is_debit"])
        self.assertEqual(row1["payee_name"], "Add Funds")

        # Row 3: 23 Jul '26 Add money to Emergency fund atom -₹81 (Debit)
        row3 = rows[2]
        self.assertEqual(row3["date"], date(2026, 7, 23))
        self.assertEqual(row3["amount"], Decimal("81"))
        self.assertTrue(row3["is_debit"])
        self.assertEqual(row3["payee_name"], "Emergency Fund Deposit")

        # Row 4: 23 Jul '26 UPI-Debit-620487074829-MALLETHULA SHIVA... -₹10 (Debit)
        row4 = rows[3]
        self.assertEqual(row4["date"], date(2026, 7, 23))
        self.assertEqual(row4["amount"], Decimal("10"))
        self.assertTrue(row4["is_debit"])
        self.assertIn("MALLETHULA SHIVARU", row4["payee_name"])
        self.assertEqual(row4["upi_id"], "lucky9398@ibl")

        # Row 10: 24 Jul '26 UPI-Debit-620500939447-AMBATI PUSHPALATHA C... -₹50 (Debit)
        row10 = rows[9]
        self.assertEqual(row10["date"], date(2026, 7, 24))
        self.assertEqual(row10["amount"], Decimal("50"))
        self.assertTrue(row10["is_debit"])
        self.assertIn("AMBATI PUSHPALATHA", row10["payee_name"])
        self.assertEqual(row10["upi_id"], "paytm.s1x8ig0@pty")

    def test_future_unrecognized_format_error_preserved(self):
        """Verify unrecognized PDF formats still raise the specific Phase 11 layout error."""
        import io
        import reportlab.pdfgen.canvas as canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(100, 700, "Random college syllabus and notes without any financial tables.")
        c.drawString(100, 680, "Department of Computer Science semester guide.")
        c.save()
        unrecognized_pdf_bytes = buf.getvalue()

        with self.assertRaises(UnsupportedLayoutError) as ctx:
            parse_statement(unrecognized_pdf_bytes, "unknown_document.pdf")

        self.assertIn("unsupported statement layout", str(ctx.exception))
        self.assertIn("could not find a recognized transaction table", str(ctx.exception))
