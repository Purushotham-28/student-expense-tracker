"""
Phase 2 Backend Tests — Statement Upload & Parsing
Covers: SBI CSV parsing, HDFC PDF parsing, upload endpoint, and edge cases.
"""
import os
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status

from .models import Statement, Transaction
from .parsers import parse_statement
from .parsers.sbi_csv import SbiCsvParser
from .parsers.hdfc_pdf import HdfcPdfParser


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


class SbiCsvParserTests(TestCase):
    """
    Tests for the SBI CSV parser using the sample fixture file.
    The fixture contains 5 transactions (4 debits, 1 credit)
    spanning 01/09/2026 to 25/09/2026.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fixture_path = os.path.join(FIXTURES_DIR, 'sbi_sample.csv')
        with open(fixture_path, 'rb') as f:
            cls.file_bytes = f.read()
        cls.filename = 'sbi_sample.csv'

    def test_can_parse_detects_sbi_csv(self):
        """SbiCsvParser.can_parse() returns True for the SBI fixture."""
        self.assertTrue(SbiCsvParser.can_parse(self.file_bytes, self.filename))

    def test_can_parse_rejects_pdf(self):
        """SbiCsvParser.can_parse() returns False for a PDF filename."""
        self.assertFalse(SbiCsvParser.can_parse(self.file_bytes, 'statement.pdf'))

    def test_row_count(self):
        """Parser extracts exactly 5 transaction rows from the SBI fixture."""
        parser = SbiCsvParser()
        rows = parser.parse(self.file_bytes, self.filename)
        self.assertEqual(len(rows), 5)

    def test_date_range(self):
        """Extracted dates span from 2026-09-01 to 2026-09-25."""
        parser = SbiCsvParser()
        rows = parser.parse(self.file_bytes, self.filename)
        dates = [r['date'] for r in rows]
        self.assertEqual(min(dates), date(2026, 9, 1))
        self.assertEqual(max(dates), date(2026, 9, 25))

    def test_debit_credit_detection(self):
        """
        4 transactions are debits (Zomato, Swiggy, Amazon, Flipkart)
        and 1 is a credit (NEFT from John Doe).
        """
        parser = SbiCsvParser()
        rows = parser.parse(self.file_bytes, self.filename)
        debits = [r for r in rows if r['is_debit']]
        credits = [r for r in rows if not r['is_debit']]
        self.assertEqual(len(debits), 4)
        self.assertEqual(len(credits), 1)

    def test_amounts(self):
        """Check first and last transaction amounts are parsed correctly."""
        parser = SbiCsvParser()
        rows = parser.parse(self.file_bytes, self.filename)
        self.assertEqual(rows[0]['amount'], Decimal('250.00'))
        self.assertEqual(rows[1]['amount'], Decimal('180.50'))
        # The credit transaction (NEFT)
        credit_row = [r for r in rows if not r['is_debit']][0]
        self.assertEqual(credit_row['amount'], Decimal('15000.00'))

    def test_payee_extraction(self):
        """Payee names are extracted from UPI/NEFT narration patterns."""
        parser = SbiCsvParser()
        rows = parser.parse(self.file_bytes, self.filename)
        # First row: UPI-ZOMATO-... → payee should contain 'ZOMATO'
        self.assertIn('ZOMATO', rows[0]['payee_name'].upper())

    def test_upi_id_extraction(self):
        """UPI VPAs are extracted from description text."""
        parser = SbiCsvParser()
        rows = parser.parse(self.file_bytes, self.filename)
        # First row has 9876543210@okaxis in the description
        self.assertIn('@', rows[0]['upi_id'])

    def test_dispatch_picks_sbi(self):
        """parse_statement() picks 'sbi_csv' as the format name."""
        rows, fmt = parse_statement(self.file_bytes, self.filename)
        self.assertEqual(fmt, 'sbi_csv')
        self.assertEqual(len(rows), 5)


class HdfcPdfParserTests(TestCase):
    """
    Tests for the HDFC PDF parser using the generated fixture.
    The fixture contains 7 transactions (6 debits, 1 credit)
    spanning 01/09/2026 to 28/09/2026.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fixture_path = os.path.join(FIXTURES_DIR, 'hdfc_sample.pdf')
        if not os.path.exists(fixture_path):
            # Generate the fixture if it doesn't exist yet
            from .fixtures.generate_hdfc_pdf import (
                generate_with_reportlab, generate_with_fpdf,
                generate_minimal_pdf, USE_REPORTLAB, USE_FPDF,
            )
            os.makedirs(FIXTURES_DIR, exist_ok=True)
            if USE_REPORTLAB:
                generate_with_reportlab(fixture_path)
            elif USE_FPDF:
                generate_with_fpdf(fixture_path)
            else:
                generate_minimal_pdf(fixture_path)

        with open(fixture_path, 'rb') as f:
            cls.file_bytes = f.read()
        cls.filename = 'hdfc_sample.pdf'

    def test_can_parse_detects_hdfc_pdf(self):
        """HdfcPdfParser.can_parse() returns True for the HDFC fixture."""
        self.assertTrue(HdfcPdfParser.can_parse(self.file_bytes, self.filename))

    def test_can_parse_rejects_csv(self):
        """HdfcPdfParser.can_parse() returns False for a CSV filename."""
        self.assertFalse(HdfcPdfParser.can_parse(self.file_bytes, 'statement.csv'))

    def test_row_count(self):
        """Parser extracts exactly 7 transaction rows from the HDFC fixture."""
        parser = HdfcPdfParser()
        rows = parser.parse(self.file_bytes, self.filename)
        self.assertEqual(len(rows), 7)

    def test_date_range(self):
        """Extracted dates span from 2026-09-01 to 2026-09-28."""
        parser = HdfcPdfParser()
        rows = parser.parse(self.file_bytes, self.filename)
        dates = [r['date'] for r in rows]
        self.assertEqual(min(dates), date(2026, 9, 1))
        self.assertEqual(max(dates), date(2026, 9, 28))

    def test_debit_credit_detection(self):
        """6 debits and 1 credit in the HDFC fixture."""
        parser = HdfcPdfParser()
        rows = parser.parse(self.file_bytes, self.filename)
        debits = [r for r in rows if r['is_debit']]
        credits = [r for r in rows if not r['is_debit']]
        self.assertEqual(len(debits), 6)
        self.assertEqual(len(credits), 1)

    def test_amounts(self):
        """Spot-check amounts: first debit=85, credit=5000."""
        parser = HdfcPdfParser()
        rows = parser.parse(self.file_bytes, self.filename)
        self.assertEqual(rows[0]['amount'], Decimal('85.00'))
        credit_row = [r for r in rows if not r['is_debit']][0]
        self.assertEqual(credit_row['amount'], Decimal('5000.00'))

    def test_payee_extraction_from_narration(self):
        """Payee extraction works for UPI and NEFT patterns in PDF."""
        parser = HdfcPdfParser()
        rows = parser.parse(self.file_bytes, self.filename)
        # First row: UPI-RAPIDO-... → payee should contain RAPIDO
        self.assertIn('RAPIDO', rows[0]['payee_name'].upper())

    def test_dispatch_picks_hdfc(self):
        """parse_statement() picks 'hdfc_pdf' as the format name."""
        rows, fmt = parse_statement(self.file_bytes, self.filename)
        self.assertEqual(fmt, 'hdfc_pdf')
        self.assertEqual(len(rows), 7)


@override_settings(MEDIA_ROOT=os.path.join(os.path.dirname(__file__), 'test_media'))
class StatementUploadEndpointTests(TestCase):
    """
    Integration tests for POST /api/statements/upload.
    Tests the full pipeline: upload → parse → persist → response.
    """

    def setUp(self):
        self.client = APIClient()
        self.upload_url = '/api/statements/upload/'
        self.list_url = '/api/statements/'

        # Create and authenticate a test user
        self.user = User.objects.create_user(
            username='test_student',
            email='test@campus.edu',
            password='TestPass123!',
        )
        from .models import UserProfile
        UserProfile.objects.create(
            user=self.user,
            college_roll_number='TEST-001',
        )
        self.client.force_authenticate(user=self.user)

    @classmethod
    def tearDownClass(cls):
        # Clean up test media (handle Windows file locks gracefully)
        import shutil
        media_dir = os.path.join(os.path.dirname(__file__), 'test_media')
        if os.path.exists(media_dir):
            shutil.rmtree(media_dir, ignore_errors=True)
        super().tearDownClass()

    def test_upload_csv_success(self):
        """
        POST /api/statements/upload with a valid SBI CSV file returns 201
        with the correct transaction count and date range.
        """
        fixture_path = os.path.join(FIXTURES_DIR, 'sbi_sample.csv')
        with open(fixture_path, 'rb') as f:
            csv_file = SimpleUploadedFile(
                'sbi_statement.csv',
                f.read(),
                content_type='text/csv',
            )

        response = self.client.post(self.upload_url, {'file': csv_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('summary', response.data)
        self.assertEqual(response.data['summary']['total_transactions'], 5)
        self.assertEqual(response.data['summary']['date_from'], '2026-09-01')
        self.assertEqual(response.data['summary']['date_to'], '2026-09-25')
        self.assertEqual(response.data['summary']['bank_format'], 'sbi_csv')

        # Verify database records
        stmt = Statement.objects.get(user=self.user)
        self.assertEqual(stmt.status, Statement.Status.DONE)
        self.assertEqual(stmt.transaction_count, 5)
        self.assertEqual(Transaction.objects.filter(statement=stmt).count(), 5)

    def test_upload_pdf_success(self):
        """
        POST /api/statements/upload with a valid HDFC PDF file returns 201
        with the correct transaction count.
        """
        fixture_path = os.path.join(FIXTURES_DIR, 'hdfc_sample.pdf')
        with open(fixture_path, 'rb') as f:
            pdf_file = SimpleUploadedFile(
                'hdfc_statement.pdf',
                f.read(),
                content_type='application/pdf',
            )

        response = self.client.post(self.upload_url, {'file': pdf_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['summary']['total_transactions'], 7)
        self.assertEqual(response.data['summary']['bank_format'], 'hdfc_pdf')

        # Verify transactions persisted
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 7)

    def test_upload_no_file_returns_400(self):
        """Upload without a file attachment returns 400."""
        response = self.client.post(self.upload_url, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_upload_unsupported_type_returns_400(self):
        """Upload with a .txt file returns 400 (unsupported type)."""
        txt_file = SimpleUploadedFile(
            'notes.txt',
            b'Just some text',
            content_type='text/plain',
        )
        response = self.client.post(self.upload_url, {'file': txt_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Unsupported', response.data['error'])

    def test_upload_requires_authentication(self):
        """Upload without authentication returns 401."""
        self.client.force_authenticate(user=None)
        fixture_path = os.path.join(FIXTURES_DIR, 'sbi_sample.csv')
        with open(fixture_path, 'rb') as f:
            csv_file = SimpleUploadedFile(
                'sbi_statement.csv', f.read(), content_type='text/csv',
            )
        response = self.client.post(self.upload_url, {'file': csv_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_statements_returns_uploads(self):
        """
        GET /api/statements/ returns the user's uploaded statements.
        """
        # Upload a file first
        fixture_path = os.path.join(FIXTURES_DIR, 'sbi_sample.csv')
        with open(fixture_path, 'rb') as f:
            csv_file = SimpleUploadedFile(
                'sbi_statement.csv', f.read(), content_type='text/csv',
            )
        self.client.post(self.upload_url, {'file': csv_file}, format='multipart')

        # List statements
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['transaction_count'], 5)

    def test_statement_detail_includes_transactions(self):
        """
        GET /api/statements/<pk>/ returns the statement with nested transactions.
        """
        fixture_path = os.path.join(FIXTURES_DIR, 'sbi_sample.csv')
        with open(fixture_path, 'rb') as f:
            csv_file = SimpleUploadedFile(
                'sbi_statement.csv', f.read(), content_type='text/csv',
            )
        upload_res = self.client.post(self.upload_url, {'file': csv_file}, format='multipart')
        stmt_id = upload_res.data['statement']['id']

        response = self.client.get(f'/api/statements/{stmt_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('transactions', response.data)
        self.assertEqual(len(response.data['transactions']), 5)

    def test_transaction_fields_populated(self):
        """
        After CSV upload, Transaction records have proper field values.
        """
        fixture_path = os.path.join(FIXTURES_DIR, 'sbi_sample.csv')
        with open(fixture_path, 'rb') as f:
            csv_file = SimpleUploadedFile(
                'sbi_statement.csv', f.read(), content_type='text/csv',
            )
        self.client.post(self.upload_url, {'file': csv_file}, format='multipart')

        txns = Transaction.objects.filter(user=self.user).order_by('date')
        first = txns.first()
        self.assertEqual(first.date, date(2026, 9, 1))
        self.assertTrue(first.is_debit)
        self.assertEqual(first.amount, Decimal('250.00'))
        self.assertIn('ZOMATO', first.payee_name.upper())
        self.assertEqual(first.status, Transaction.ParseStatus.PENDING)
        self.assertIsNone(first.category)
        self.assertIsNone(first.confidence)


# ── Phase 3 Tests — Hybrid Categorization Engine ──────────────────────────

from io import StringIO
from django.core.management import call_command
from .models import PayeeMapping, ExpenseCategory
from .services.categorization_service import (
    normalize_payee,
    get_amount_bucket,
    extract_features,
    categorize_transaction,
    generate_synthetic_dataset,
    CATEGORIES,
)


class HybridCategorizationEngineTests(TestCase):
    """
    Phase 3 Unit Tests covering:
      - normalize_payee function (UPI preference, lowercase, punctuation/spaces stripping)
      - PayeeMapping lookup with confidence 1.0
      - ML fallback classifier returning a valid category and confidence in (0, 1]
      - train_categorizer management command execution
      - Payee mapping API and transaction categorization endpoints
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='student_phase3',
            password='testpassword123',
            email='student3@college.edu',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.statement = Statement.objects.create(
            user=self.user,
            original_filename='test_stmt.csv',
            status=Statement.Status.DONE,
            transaction_count=2,
        )

    # ── Payee Normalization Tests ──────────────────────────────────────────

    def test_normalize_payee_prefers_upi_id(self):
        """Prefer the UPI ID as the key when present, lowercased and cleaned."""
        key = normalize_payee(name="Zomato Limited", upi_id="Zomato@hdfcbank ")
        self.assertEqual(key, "zomato@hdfcbank")

    def test_normalize_payee_strips_punctuation_and_spaces_from_name(self):
        """When upi_id is empty/None, lowercase and strip punctuation and extra spaces."""
        key = normalize_payee(name="  SWIGGY - Bangalore, Pvt. Ltd.!! ", upi_id=None)
        self.assertEqual(key, "swiggy bangalore pvt ltd")

    def test_normalize_payee_empty_or_none(self):
        """Handles empty and None strings safely."""
        self.assertEqual(normalize_payee(None, None), "")
        self.assertEqual(normalize_payee("", ""), "")
        self.assertEqual(normalize_payee("   ", "   "), "")

    def test_get_amount_bucket_tiers(self):
        """Amount buckets classify amounts into appropriate tiers."""
        self.assertEqual(get_amount_bucket(40), "micro")
        self.assertEqual(get_amount_bucket(150), "low")
        self.assertEqual(get_amount_bucket(500), "medium")
        self.assertEqual(get_amount_bucket(1200), "high")
        self.assertEqual(get_amount_bucket(3500), "very_high")
        self.assertEqual(get_amount_bucket(9000), "large")

    # ── Hybrid Categorization Logic Tests ──────────────────────────────────

    def test_known_payee_mapping_returns_confidence_1_0(self):
        """
        1. Look up PayeeMapping for this user+payee_key.
        If found, assign that category with confidence 1.0.
        """
        # Create PayeeMapping for user
        PayeeMapping.objects.create(
            user=self.user,
            payee_key="swiggy@icici",
            category=ExpenseCategory.FOOD,
            times_confirmed=3,
        )

        tx = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 15),
            amount=Decimal("350.00"),
            payee_name="Swiggy Delivery",
            upi_id="Swiggy@icici",
            remark="Dinner meal order",
        )

        category, confidence, source = categorize_transaction(tx, save=True)

        self.assertEqual(category, ExpenseCategory.FOOD)
        self.assertEqual(confidence, 1.0)
        self.assertEqual(source, "payee_mapping")

        # Verify transaction in database was updated
        tx.refresh_from_db()
        self.assertEqual(tx.category, ExpenseCategory.FOOD)
        self.assertEqual(tx.confidence, 1.0)
        self.assertEqual(tx.status, Transaction.ParseStatus.CATEGORISED)

    def test_unmapped_transaction_returns_category_and_confidence_between_0_and_1(self):
        """
        2. An unmapped transaction runs ML classifier, returns a valid category
        and confidence between 0 and 1.
        """
        tx = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 20),
            amount=Decimal("45.00"),
            payee_name="Rapido Bike Taxi",
            upi_id="rapido@upi",
            remark="Rapido ride to college gate",
        )

        category, confidence, source = categorize_transaction(tx, save=True)

        self.assertIn(category, CATEGORIES)
        self.assertGreater(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)
        self.assertEqual(source, "ml_model")

        # Verify transaction record is saved with category & confidence
        tx.refresh_from_db()
        self.assertEqual(tx.category, category)
        self.assertEqual(tx.confidence, confidence)
        self.assertEqual(tx.status, Transaction.ParseStatus.CATEGORISED)

    def test_synthetic_dataset_shape(self):
        """Synthetic dataset has 270 rows covering all 9 categories (30 each)."""
        df = generate_synthetic_dataset()
        self.assertEqual(len(df), 270)
        self.assertEqual(df["category"].nunique(), 9)
        for cat in CATEGORIES:
            self.assertEqual(len(df[df["category"] == cat]), 30)

    def test_train_categorizer_management_command(self):
        """The `train_categorizer` command executes cleanly and outputs success."""
        out = StringIO()
        call_command("train_categorizer", stdout=out)
        output = out.getvalue()
        self.assertIn("Successfully trained", output)
        self.assertIn("categorizer_model.joblib", output)

    # ── API Endpoints Tests ────────────────────────────────────────────────

    def test_payee_mapping_create_and_list_api(self):
        """POST /api/payee-mappings/ creates a mapping; GET lists user mappings."""
        post_res = self.client.post("/api/payee-mappings/", {
            "payee_name": "Campus Bookstore",
            "category": "Academics",
        }, format="json")
        self.assertEqual(post_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(post_res.data["category"], "Academics")
        self.assertEqual(post_res.data["payee_key"], "campus bookstore")

        # GET
        get_res = self.client.get("/api/payee-mappings/")
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_res.data), 1)

    def test_categorize_transaction_endpoint(self):
        """POST /api/transactions/<id>/categorize/ triggers categorization."""
        tx = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            amount=Decimal("150.00"),
            payee_name="PVR Cinemas",
            upi_id="pvrcinemas@hdfcbank",
            remark="Movie ticket",
        )
        res = self.client.post(f"/api/transactions/{tx.pk}/categorize/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("category", res.data)
        self.assertIn("confidence", res.data)
        self.assertGreater(res.data["confidence"], 0)
