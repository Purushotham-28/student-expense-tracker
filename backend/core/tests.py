"""
Phase 2 Backend Tests — Statement Upload & Parsing
Covers: SBI CSV parsing, HDFC PDF parsing, upload endpoint, and edge cases.
"""
import os
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status

from .models import Statement, Transaction, UserProfile, Goal, ChatMessage
from .parsers import parse_statement
from .parsers.sbi_csv import SbiCsvParser
from .parsers.hdfc_pdf import HdfcPdfParser
from .parsers.phonepe_pdf import PhonePePdfParser


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


class PhonePePdfParserTests(TestCase):
    """
    Tests for the PhonePe UPI PDF parser.
    """

    def test_can_parse_detects_phonepe_filename(self):
        self.assertTrue(PhonePePdfParser.can_parse(b'%PDF-dummy', 'PhonePe_Statement_Oct2025.pdf'))
        self.assertFalse(PhonePePdfParser.can_parse(b'%PDF-dummy', 'statement.csv'))

    def test_can_parse_detects_phonepe_identifiers_in_bytes(self):
        sample_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'statements', '2', 'PhonePe_Statement_Oct2025_Oct2026.pdf')
        if os.path.exists(sample_path):
            with open(sample_path, 'rb') as f:
                data = f.read()
            self.assertTrue(PhonePePdfParser.can_parse(data, 'statement.pdf'))
            rows, fmt = parse_statement(data, 'statement.pdf')
            self.assertEqual(fmt, 'phonepe_pdf')
            self.assertEqual(len(rows), 45)
            self.assertEqual(rows[0]['payee_name'], 'MEENAMARAKATHAMI')
            self.assertEqual(rows[0]['amount'], Decimal('1000'))
            self.assertFalse(rows[0]['is_debit'])  # Credit


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
        # In Phase 4, uploaded statements auto-categorize and route into confidence status
        self.assertIn(first.status, [Transaction.ParseStatus.AUTO, Transaction.ParseStatus.VERIFY, Transaction.ParseStatus.PENDING])
        self.assertIsNotNone(first.category)
        self.assertIsNotNone(first.confidence)


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
        self.assertEqual(tx.status, Transaction.ParseStatus.AUTO)

    def test_unmapped_transaction_returns_category_and_confidence_between_0_and_1(self):
        """
        2. An unmapped transaction without keyword match runs ML classifier,
        returns a valid category and confidence between 0 and 1.
        """
        tx = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 20),
            amount=Decimal("450.00"),
            payee_name="UniqueUnlistedRecipient987",
            upi_id="customuser987@bank",
            remark="Payment for miscellaneous item",
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
        self.assertIn(tx.status, [Transaction.ParseStatus.AUTO, Transaction.ParseStatus.VERIFY, Transaction.ParseStatus.PENDING])

    def test_synthetic_dataset_shape(self):
        """Synthetic dataset has 330 rows covering all 11 categories (30 each)."""
        df = generate_synthetic_dataset()
        self.assertEqual(len(df), len(CATEGORIES) * 30)
        self.assertEqual(df["category"].nunique(), len(CATEGORIES))
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


# ── Phase 4 Tests — Confidence Routing & Verification Flow ────────────────

from .services.categorization_service import route_status_from_confidence


class ConfidenceRoutingAndVerificationFlowTests(TestCase):
    """
    Phase 4 Tests covering:
      - Confidence-based status routing (auto >= 0.80, verify 0.50-0.80, pending < 0.50)
      - GET /api/transactions?status=verify|pending|auto|all with pagination & sorting
      - POST /api/transactions/{id}/confirm upserts PayeeMapping & updates all matching
        past transactions for that payee.
      - Statement upload summary banner (auto_count, verify_count, pending_count).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='student_phase4',
            password='testpassword123',
            email='student4@college.edu',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.statement = Statement.objects.create(
            user=self.user,
            original_filename='sbi_sept.csv',
            status=Statement.Status.DONE,
            transaction_count=4,
        )

    def test_confidence_routing_thresholds(self):
        """Verify routing helper assigns auto, verify, or pending correctly."""
        self.assertEqual(route_status_from_confidence(0.95), Transaction.ParseStatus.AUTO)
        self.assertEqual(route_status_from_confidence(0.80), Transaction.ParseStatus.AUTO)
        self.assertEqual(route_status_from_confidence(0.79), Transaction.ParseStatus.VERIFY)
        self.assertEqual(route_status_from_confidence(0.50), Transaction.ParseStatus.VERIFY)
        self.assertEqual(route_status_from_confidence(0.49), Transaction.ParseStatus.PENDING)
        self.assertEqual(route_status_from_confidence(0.15), Transaction.ParseStatus.PENDING)

    def test_confirm_category_updates_all_matching_past_transactions_for_payee(self):
        """
        Confirming a category updates the target transaction, upserts PayeeMapping,
        and re-applies that mapping to this user's other transactions with the same
        payee_key that are still 'verify' or 'pending'.
        """
        # Create 3 transactions for the same payee (Swiggy) with various statuses
        tx1 = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 2),
            amount=Decimal("210.00"),
            payee_name="Swiggy Delivery",
            upi_id="swiggy@icici",
            status=Transaction.ParseStatus.VERIFY,
            confidence=0.65,
        )
        tx2 = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 10),
            amount=Decimal("340.00"),
            payee_name="Swiggy",
            upi_id="swiggy@icici",
            status=Transaction.ParseStatus.PENDING,
            confidence=0.45,
        )
        tx3 = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 15),
            amount=Decimal("180.00"),
            payee_name="Swiggy Order",
            upi_id="swiggy@icici",
            status=Transaction.ParseStatus.VERIFY,
            confidence=0.72,
        )

        # Unrelated transaction for Uber — should NOT be updated
        uber_tx = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 12),
            amount=Decimal("150.00"),
            payee_name="Uber India",
            upi_id="uber.india@hdfcbank",
            status=Transaction.ParseStatus.PENDING,
            confidence=0.40,
        )

        # Confirm category 'Food' on tx1
        res = self.client.post(
            f"/api/transactions/{tx1.pk}/confirm/",
            {"category": "Food", "apply_to_all": True},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["updated_count"], 3)  # tx1 + tx2 + tx3

        # 1. Target tx1 updated
        tx1.refresh_from_db()
        self.assertEqual(tx1.category, "Food")
        self.assertEqual(tx1.confidence, 1.0)
        self.assertEqual(tx1.status, Transaction.ParseStatus.AUTO)

        # 2. Other matching transactions tx2 and tx3 updated
        tx2.refresh_from_db()
        self.assertEqual(tx2.category, "Food")
        self.assertEqual(tx2.confidence, 1.0)
        self.assertEqual(tx2.status, Transaction.ParseStatus.AUTO)

        tx3.refresh_from_db()
        self.assertEqual(tx3.category, "Food")
        self.assertEqual(tx3.confidence, 1.0)
        self.assertEqual(tx3.status, Transaction.ParseStatus.AUTO)

        # 3. PayeeMapping upserted with times_confirmed = 1
        mapping = PayeeMapping.objects.get(user=self.user, payee_key="swiggy@icici")
        self.assertEqual(mapping.category, "Food")
        self.assertEqual(mapping.times_confirmed, 1)

        # 4. Uber transaction remained untouched
        uber_tx.refresh_from_db()
        self.assertEqual(uber_tx.status, Transaction.ParseStatus.PENDING)
        self.assertIsNone(uber_tx.category)

    def test_get_transactions_filtered_by_status(self):
        """GET /api/transactions?status=pending|verify|auto|all returns filtered results."""
        # Create transactions with various statuses
        Transaction.objects.create(
            statement=self.statement, user=self.user,
            amount=Decimal("50.00"), payee_name="Chai", status=Transaction.ParseStatus.AUTO,
        )
        Transaction.objects.create(
            statement=self.statement, user=self.user,
            amount=Decimal("500.00"), payee_name="Unknown 1", status=Transaction.ParseStatus.PENDING,
        )
        Transaction.objects.create(
            statement=self.statement, user=self.user,
            amount=Decimal("1200.00"), payee_name="Unknown 2", status=Transaction.ParseStatus.PENDING,
        )
        Transaction.objects.create(
            statement=self.statement, user=self.user,
            amount=Decimal("300.00"), payee_name="Verify 1", status=Transaction.ParseStatus.VERIFY,
        )

        # Filter: pending
        res_pending = self.client.get("/api/transactions/?status=pending")
        self.assertEqual(res_pending.status_code, status.HTTP_200_OK)
        self.assertEqual(res_pending.data["count"], 2)
        # Pending is sorted by amount DESCENDING (biggest unknowns first)
        results = res_pending.data["results"]
        self.assertEqual(float(results[0]["amount"]), 1200.00)
        self.assertEqual(float(results[1]["amount"]), 500.00)

        # Filter: verify
        res_verify = self.client.get("/api/transactions/?status=verify")
        self.assertEqual(res_verify.status_code, status.HTTP_200_OK)
        self.assertEqual(res_verify.data["count"], 1)

        # Filter: auto
        res_auto = self.client.get("/api/transactions/?status=auto")
        self.assertEqual(res_auto.status_code, status.HTTP_200_OK)
        self.assertEqual(res_auto.data["count"], 1)

        # Filter: all (checks counts object)
        res_all = self.client.get("/api/transactions/?status=all")
        self.assertEqual(res_all.status_code, status.HTTP_200_OK)
        self.assertEqual(res_all.data["count"], 4)
        self.assertEqual(res_all.data["counts"]["auto"], 1)
        self.assertEqual(res_all.data["counts"]["verify"], 1)
        self.assertEqual(res_all.data["counts"]["pending"], 2)

    def test_upload_response_summary_banner_counts(self):
        """Upload response contains auto_count, verify_count, and pending_count in summary."""
        fixture_path = os.path.join(FIXTURES_DIR, 'sbi_sample.csv')
        with open(fixture_path, 'rb') as f:
            csv_file = SimpleUploadedFile('sbi_statement.csv', f.read(), content_type='text/csv')

        res = self.client.post("/api/statements/upload/", {'file': csv_file}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("summary", res.data)
        summary = res.data["summary"]
        self.assertIn("auto_count", summary)
        self.assertIn("verify_count", summary)
        self.assertIn("pending_count", summary)
        # Total equals sum of all buckets
        total = summary["auto_count"] + summary["verify_count"] + summary["pending_count"]
        self.assertEqual(total, summary["total_transactions"])


# ── Phase 5 Tests — Forecasting & Cash-Flow Runway Simulator ──────────────

from .services.forecasting_service import (
    forecast_daily_spending,
    calculate_cash_flow_runway,
    simulate_whatif_adjustments,
)


class ForecastingAndRunwaySimulatorTests(TestCase):
    """
    Phase 5 Tests covering:
      - Cold-start fallback to baseline average when < 14 days of data.
      - ARIMA/Prophet forecasting with >= 14 days of data.
      - Runway date calculation given balance and forecasted burn rate.
      - GET /api/planning/runway endpoint.
      - POST /api/planning/whatif simulator reducing spend and extending runway.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='student_phase5',
            password='testpassword123',
            email='student5@college.edu',
        )
        UserProfile.objects.create(
            user=self.user,
            college_roll_number='ROLL-PHASE5',
            monthly_income=Decimal('15000.00'),
            monthly_budget_limit=Decimal('12000.00'),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.statement = Statement.objects.create(
            user=self.user,
            original_filename='phase5_stmt.csv',
            status=Statement.Status.DONE,
            transaction_count=10,
        )

    def test_cold_start_fallback_to_average_estimate(self):
        """When user has fewer than 14 days of transactions, fall back to baseline average."""
        # Create only 3 transactions
        today = date.today()
        for i in range(3):
            Transaction.objects.create(
                statement=self.statement,
                user=self.user,
                date=today - timedelta(days=i),
                amount=Decimal("250.00"),
                is_debit=True,
                category=ExpenseCategory.FOOD,
            )

        forecast = forecast_daily_spending(self.user, steps=30)
        self.assertEqual(forecast["method"], "baseline_average")
        self.assertEqual(len(forecast["forecast_values"]), 30)
        self.assertGreater(forecast["daily_avg"], 0)

    def test_arima_forecasting_with_sufficient_history(self):
        """When user has >= 14 days of data, fit ARIMA/Prophet time-series model."""
        today = date.today()
        for i in range(20):
            Transaction.objects.create(
                statement=self.statement,
                user=self.user,
                date=today - timedelta(days=i),
                amount=Decimal(str(150 + (i % 5) * 40)),
                is_debit=True,
                category=ExpenseCategory.FOOD if i % 2 == 0 else ExpenseCategory.TRAVEL,
            )

        forecast = forecast_daily_spending(self.user, steps=30)
        self.assertIn(forecast["method"], ["arima", "prophet"])
        self.assertEqual(len(forecast["forecast_values"]), 30)
        for v in forecast["forecast_values"]:
            self.assertGreaterEqual(v, 0)

    def test_runway_calculation_depletion_date(self):
        """Given current balance and daily burn, computes depletion date."""
        today = date.today()
        # Seed 5 transactions with ₹200 daily spend
        for i in range(5):
            Transaction.objects.create(
                statement=self.statement,
                user=self.user,
                date=today - timedelta(days=i),
                amount=Decimal("200.00"),
                is_debit=True,
                category=ExpenseCategory.FOOD,
            )

        # Balance = ₹1,000 → should deplete in ~5 days
        runway = calculate_cash_flow_runway(user=self.user, current_balance=1000.0)

        self.assertEqual(runway["current_balance"], 1000.0)
        self.assertTrue(runway["is_exhausted"])
        self.assertIsNotNone(runway["runway_date"])
        self.assertGreater(runway["runway_days"], 0)
        self.assertLessEqual(runway["runway_days"], 15)

    def test_get_runway_endpoint(self):
        """GET /api/planning/runway returns forecast series and runway date."""
        today = date.today()
        Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=today,
            amount=Decimal("300.00"),
            is_debit=True,
            category=ExpenseCategory.FOOD,
        )

        res = self.client.get("/api/planning/runway/?current_balance=4000")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("runway_date", res.data)
        self.assertIn("forecast_series", res.data)
        self.assertIn("daily_burn_rate", res.data)
        self.assertEqual(res.data["current_balance"], 4000.0)
        self.assertIsInstance(res.data["forecast_series"], list)

    def test_whatif_adjustment_extends_runway(self):
        """POST /api/planning/whatif with category reduction extends runway date and saves money."""
        today = date.today()
        # 10 days of heavy Food expenses (₹500/day)
        for i in range(10):
            Transaction.objects.create(
                statement=self.statement,
                user=self.user,
                date=today - timedelta(days=i),
                amount=Decimal("500.00"),
                is_debit=True,
                category=ExpenseCategory.FOOD,
            )

        # Call whatif endpoint to reduce Food by 50% with ₹2,500 balance
        payload = {
            "category": "Food",
            "reduce_percent": 50,
            "current_balance": 2500,
        }
        res = self.client.post("/api/planning/whatif/", payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("original_runway_date", res.data)
        self.assertIn("adjusted_runway_date", res.data)
        self.assertIn("days_saved", res.data)
        self.assertIn("money_saved_30d", res.data)

        # Reducing by 50% must save money and increase or maintain runway days
        self.assertGreater(res.data["money_saved_30d"], 0)
        self.assertGreaterEqual(res.data["adjusted_runway_days"], res.data["original_runway_days"])


class GoalPlannerTests(TestCase):
    """
    Phase 6 Tests — Goal Planner & Adaptive Savings
    Covers:
      - Goal model & dynamic weekly target calculation
      - Adaptive weekly target updates when saved_so_far or deadline changes
      - CRUD endpoints at /api/goals
      - Contribution endpoint at /api/goals/{id}/contribute
      - Background rate check & trim suggestions using Phase 5 forecasting
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="student_planner",
            email="planner@campus.edu",
            password="testpassword123",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            college_roll_number="CS2026-PLANNER",
            monthly_income=Decimal("15000.00"),
            monthly_budget_limit=Decimal("10000.00"),
        )
        self.statement = Statement.objects.create(
            user=self.user,
            original_filename="sample_stmt.csv",
            file_type="csv",
            status=Statement.Status.DONE,
        )
        self.client.force_authenticate(user=self.user)

    def test_weekly_target_calculation_and_adaptation(self):
        """
        Weekly target = (target_amount - saved_so_far) / weeks_remaining.
        Adapts dynamically when saved_so_far or deadline changes.
        """
        today = date.today()
        # Deadline 4 weeks (28 days) away, target = ₹8,000, saved = ₹0
        goal = Goal.objects.create(
            user=self.user,
            name="New Laptop",
            target_amount=Decimal("8000.00"),
            saved_so_far=Decimal("0.00"),
            deadline=today + timedelta(days=28),
        )

        # 28 days = exactly 4.0 weeks -> target is 8000 / 4 = 2000/week
        self.assertEqual(goal.weeks_remaining, 4.0)
        self.assertEqual(goal.weekly_target, 2000.0)
        self.assertEqual(goal.progress_percentage, 0.0)

        # Contribute ₹4,000 -> remaining ₹4,000 / 4 weeks = 1000/week
        goal.contribute(4000.00)
        goal.refresh_from_db()
        self.assertEqual(goal.saved_so_far, Decimal("4000.00"))
        self.assertEqual(goal.weekly_target, 1000.0)
        self.assertEqual(goal.progress_percentage, 50.0)

        # Deadline shortened to 2 weeks (14 days) -> remaining ₹4,000 / 2 = 2000/week
        goal.deadline = today + timedelta(days=14)
        goal.save()
        self.assertEqual(goal.weeks_remaining, 2.0)
        self.assertEqual(goal.weekly_target, 2000.0)

        # Target completed -> status becomes done, weekly target = 0
        goal.contribute(4000.00)
        goal.refresh_from_db()
        self.assertEqual(goal.status, Goal.Status.DONE)
        self.assertEqual(goal.weekly_target, 0.0)
        self.assertEqual(goal.progress_percentage, 100.0)

    def test_goals_crud_endpoints(self):
        """Tests full CRUD cycle on /api/goals and /api/goals/{id}/."""
        today = date.today()
        deadline_str = (today + timedelta(days=35)).isoformat()

        # 1. Create Goal
        create_res = self.client.post(
            "/api/goals/",
            {
                "name": "Exam Registration Fee",
                "target_amount": 3500.00,
                "saved_so_far": 500.00,
                "deadline": deadline_str,
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        goal_id = create_res.data["id"]
        self.assertEqual(create_res.data["name"], "Exam Registration Fee")
        self.assertIn("weekly_target", create_res.data)
        self.assertGreater(create_res.data["weekly_target"], 0)

        # 2. List Goals
        list_res = self.client.get("/api/goals/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertIn("goals", list_res.data)
        self.assertIn("summary", list_res.data)
        self.assertIn("evaluation", list_res.data)
        self.assertEqual(len(list_res.data["goals"]), 1)

        # 3. Retrieve Goal detail
        detail_res = self.client.get(f"/api/goals/{goal_id}/")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data["id"], goal_id)

        # 4. Update Goal (PATCH)
        patch_res = self.client.patch(
            f"/api/goals/{goal_id}/",
            {"name": "GATE Exam Fee"},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["name"], "GATE Exam Fee")

        # 5. Delete Goal
        del_res = self.client.delete(f"/api/goals/{goal_id}/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertFalse(Goal.objects.filter(id=goal_id).exists())

    def test_goal_contribute_endpoint(self):
        """POST /api/goals/{id}/contribute logs progress and transitions to done when reached."""
        today = date.today()
        goal = Goal.objects.create(
            user=self.user,
            name="Placement Suit Fund",
            target_amount=Decimal("5000.00"),
            saved_so_far=Decimal("2000.00"),
            deadline=today + timedelta(days=30),
        )

        # Partial contribution of ₹1,000
        res = self.client.post(
            f"/api/goals/{goal.id}/contribute/",
            {"amount": 1000},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["amount_contributed"], 1000.0)
        self.assertFalse(res.data["goal_completed"])
        self.assertEqual(float(res.data["goal"]["saved_so_far"]), 3000.0)

        # Final contribution of ₹2,000 (reaches target ₹5,000)
        res2 = self.client.post(
            f"/api/goals/{goal.id}/contribute/",
            {"amount": 2000},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertTrue(res2.data["goal_completed"])
        self.assertEqual(res2.data["goal"]["status"], Goal.Status.DONE)

    def test_background_check_and_category_trim_suggestion(self):
        """
        When student is falling behind their required weekly rate,
        the background check identifies the deficit and suggests a trimmable category cut.
        """
        today = date.today()
        # Active goal needing ₹2,000/week (₹8,000 due in 4 weeks)
        Goal.objects.create(
            user=self.user,
            name="Emergency Fund",
            target_amount=Decimal("8000.00"),
            saved_so_far=Decimal("0.00"),
            deadline=today + timedelta(days=28),
        )

        # User has high spending on Food (₹1,500/day over past 10 days)
        for i in range(10):
            Transaction.objects.create(
                statement=self.statement,
                user=self.user,
                date=today - timedelta(days=i),
                amount=Decimal("1500.00"),
                is_debit=True,
                category=ExpenseCategory.FOOD,
            )

        res = self.client.get("/api/goals/suggestion/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["has_active_goals"])
        self.assertTrue(res.data["is_behind"])
        self.assertGreater(res.data["needed_weekly_rate"], 0)
        self.assertGreater(res.data["weekly_deficit"], 0)
        self.assertEqual(res.data["suggested_category"], "Food")
        self.assertGreater(res.data["recommended_reduction_percent"], 0)
        self.assertGreater(res.data["projected_weekly_savings"], 0)
        self.assertIn("message", res.data)


from .services.health_score_service import calculate_financial_health_score  # noqa: E402


class FinancialHealthScoreTests(TestCase):
    """
    Phase 7 Tests — Financial Health Score
    Covers:
      - Savings rate component (0-40 pts)
      - Budget adherence component (0-30 pts)
      - Volatility component (0-30 pts, inverse of coefficient of variation)
      - Tip generation logic
      - GET /api/planning/health-score endpoint
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="student_health",
            email="health@campus.edu",
            password="testpassword123",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            college_roll_number="CS2026-HEALTH",
            monthly_income=Decimal("16000.00"),
            monthly_budget_limit=Decimal("12000.00"),
        )
        self.statement = Statement.objects.create(
            user=self.user,
            original_filename="health_stmt.csv",
            file_type="csv",
            status=Statement.Status.DONE,
        )
        self.client.force_authenticate(user=self.user)

    def test_perfect_saver_scores_near_100(self):
        """
        A student with >= 30% savings rate, 100% budget adherence, and steady
        weekly spending across 4 weeks should achieve a score near or at 100.
        """
        # Income = 20,000, Spend = 12,000 (Savings rate = 40% >= 30% -> 40 pts)
        # Budget = 15,000 (Spend 12,000 <= 15,000 -> 30 pts)
        # Weekly spends = exactly 3,000 each week (CV = 0 -> 30 pts)
        res = calculate_financial_health_score(
            income=20000.0,
            spend=12000.0,
            budget_limit=15000.0,
            weekly_spends=[3000.0, 3000.0, 3000.0, 3000.0],
        )

        self.assertEqual(res["total_score"], 100.0)
        self.assertEqual(res["grade"], "A+")
        self.assertEqual(res["status"], "Excellent")
        self.assertEqual(res["components"]["savings_rate"]["score"], 40.0)
        self.assertEqual(res["components"]["budget_adherence"]["score"], 30.0)
        self.assertEqual(res["components"]["spending_volatility"]["score"], 30.0)
        self.assertGreaterEqual(len(res["tips"]), 2)

    def test_overspender_with_high_volatility_scores_low(self):
        """
        A student with negative savings, severe budget overspend, and erratic
        lumpy spending should receive a low score and targeted corrective tips.
        """
        # Income = 10,000, Spend = 16,000 (Savings rate = -60% -> 0 pts)
        # Budget = 10,000 (Overspent by 60% -> 30 * (1 - 0.6) = 12 pts)
        # Weekly spends: [500, 12000, 1000, 2500] (High CV -> low volatility score < 16 pts)
        res = calculate_financial_health_score(
            income=10000.0,
            spend=16000.0,
            budget_limit=10000.0,
            weekly_spends=[500.0, 12000.0, 1000.0, 2500.0],
        )

        self.assertLess(res["total_score"], 35.0)
        self.assertEqual(res["grade"], "D")
        self.assertEqual(res["status"], "Needs Attention")
        self.assertEqual(res["components"]["savings_rate"]["score"], 0.0)
        self.assertLessEqual(res["components"]["budget_adherence"]["score"], 15.0)
        self.assertLess(res["components"]["spending_volatility"]["score"], 16.0)
        # Tips should flag savings or budget as top concern
        tips_text = " ".join(res["tips"]).lower()
        self.assertTrue("savings" in tips_text or "outflows" in tips_text or "budget" in tips_text)

    def test_moderate_steady_saver(self):
        """
        A steady student saving 15% of income within budget should score in the Good / B range (~75-80).
        """
        # Income = 15,000, Spend = 12,750 (Savings rate = 15% -> 20 pts)
        # Budget = 13,000 (Spend <= Budget -> 30 pts)
        # Weekly spends = [3100, 3200, 3250, 3200] (Very low CV ~0.016 -> ~29.5 pts)
        res = calculate_financial_health_score(
            income=15000.0,
            spend=12750.0,
            budget_limit=13000.0,
            weekly_spends=[3100.0, 3200.0, 3250.0, 3200.0],
        )

        self.assertGreaterEqual(res["total_score"], 75.0)
        self.assertLessEqual(res["total_score"], 85.0)
        self.assertIn(res["grade"], ["B", "A+"])
        self.assertEqual(res["components"]["budget_adherence"]["score"], 30.0)
        self.assertEqual(res["components"]["savings_rate"]["score"], 20.0)

    def test_health_score_endpoint(self):
        """GET /api/planning/health-score returns score, components, and tips."""
        today = date.today()
        # Seed 4 weeks of moderate expenses
        for week_idx in range(4):
            Transaction.objects.create(
                statement=self.statement,
                user=self.user,
                date=today - timedelta(days=week_idx * 7 + 2),
                amount=Decimal("2000.00"),
                is_debit=True,
                category=ExpenseCategory.FOOD,
            )

        res = self.client.get("/api/planning/health-score/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("total_score", res.data)
        self.assertIn("grade", res.data)
        self.assertIn("status", res.data)
        self.assertIn("components", res.data)
        self.assertIn("tips", res.data)

        # Confirm the 3 components exist
        comps = res.data["components"]
        self.assertIn("savings_rate", comps)
        self.assertIn("budget_adherence", comps)
        self.assertIn("spending_volatility", comps)
        self.assertIsInstance(res.data["tips"], list)
        self.assertGreaterEqual(len(res.data["tips"]), 2)


from .services.chat_service import execute_chat_tool, process_chat_message, CLAUDE_TOOLS  # noqa: E402


class AIChatboxFunctionCallingTests(TestCase):
    """
    Phase 8 Tests — AI Chatbox (Claude API with Function Calling)
    Covers:
      - Tool execution: add_expense, get_spending_summary, get_runway, run_whatif, get_goal_status, get_health_score
      - Multi-turn tool execution loop & real data grounding
      - ChatMessage persistence across interactions
      - POST /api/chat and GET /api/chat/history endpoints
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="student_ai",
            email="ai@campus.edu",
            password="testpassword123",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            college_roll_number="CS2026-AI",
            monthly_income=Decimal("15000.00"),
            monthly_budget_limit=Decimal("10000.00"),
        )
        self.statement = Statement.objects.create(
            user=self.user,
            original_filename="ai_stmt.csv",
            file_type="csv",
            status=Statement.Status.DONE,
        )
        self.client.force_authenticate(user=self.user)

    def test_tools_schema_definition(self):
        """All required tools exist with schemas: add_expense, get_spending_summary, get_runway, run_whatif, get_goal_status, get_health_score."""
        tool_names = [t["name"] for t in CLAUDE_TOOLS]
        self.assertIn("add_expense", tool_names)
        self.assertIn("get_spending_summary", tool_names)
        self.assertIn("get_runway", tool_names)
        self.assertIn("run_whatif", tool_names)
        self.assertIn("get_goal_status", tool_names)
        self.assertIn("get_health_score", tool_names)

    def test_add_expense_tool_creates_transaction(self):
        """add_expense tool creates a Transaction with accurate amount, payee, and category."""
        res = execute_chat_tool(
            self.user,
            "add_expense",
            {
                "amount": 180.0,
                "item": "Campus Coffee & Croissant",
                "category": "Food",
                "payee": "Nescafe Kiosk",
            },
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["amount"], 180.0)
        self.assertEqual(res["category"], "Food")

        # Verify transaction in database
        tx = Transaction.objects.get(id=res["transaction_id"])
        self.assertEqual(tx.user, self.user)
        self.assertEqual(tx.amount, Decimal("180.00"))
        self.assertEqual(tx.category, "Food")
        self.assertEqual(tx.payee_name, "Nescafe Kiosk")

    def test_get_spending_summary_tool_queries_real_totals(self):
        """get_spending_summary returns accurate sums and transaction counts."""
        today = date.today()
        # Seed 2 transactions under Food
        Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=today,
            amount=Decimal("250.00"),
            is_debit=True,
            category=ExpenseCategory.FOOD,
            payee_name="Zomato",
        )
        Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=today,
            amount=Decimal("350.00"),
            is_debit=True,
            category=ExpenseCategory.FOOD,
            payee_name="Swiggy",
        )

        res = execute_chat_tool(self.user, "get_spending_summary", {"category": "Food"})
        self.assertEqual(res["category"], "Food")
        self.assertEqual(res["total_spent"], 600.0)
        self.assertEqual(res["transaction_count"], 2)
        self.assertEqual(res["average_transaction"], 300.0)
        self.assertEqual(len(res["top_payees"]), 2)

    def test_runway_and_whatif_tools(self):
        """get_runway and run_whatif return concrete forecasting metrics."""
        today = date.today()
        # Seed recent transactions
        for i in range(5):
            Transaction.objects.create(
                statement=self.statement,
                user=self.user,
                date=today - timedelta(days=i),
                amount=Decimal("300.00"),
                is_debit=True,
                category=ExpenseCategory.FOOD,
            )

        # get_runway
        runway_res = execute_chat_tool(self.user, "get_runway", {})
        self.assertIn("current_balance", runway_res)
        self.assertIn("runway_date", runway_res)
        self.assertIn("daily_burn_rate", runway_res)

        # run_whatif
        whatif_res = execute_chat_tool(self.user, "run_whatif", {"category": "Food", "reduce_percent": 30})
        self.assertEqual(whatif_res["category"], "Food")
        self.assertIn("days_saved", whatif_res)
        self.assertIn("money_saved_30d", whatif_res)

    def test_goal_status_and_health_score_tools(self):
        """get_goal_status and get_health_score execute underlying planning engines."""
        today = date.today()
        Goal.objects.create(
            user=self.user,
            name="Laptop Fund",
            target_amount=Decimal("50000.00"),
            saved_so_far=Decimal("10000.00"),
            deadline=today + timedelta(days=60),
        )

        goal_res = execute_chat_tool(self.user, "get_goal_status", {"goal_name": "Laptop"})
        self.assertEqual(len(goal_res["goals"]), 1)
        self.assertEqual(goal_res["goals"][0]["name"], "Laptop Fund")

        health_res = execute_chat_tool(self.user, "get_health_score", {})
        self.assertIn("total_score", health_res)
        self.assertIn("grade", health_res)
        self.assertIn("tips", health_res)

    def test_chat_endpoint_stores_history_and_returns_real_response(self):
        """
        POST /api/chat records user message, executes tool, saves assistant message,
        and GET /api/chat/history returns the full persistent conversation.
        """
        # User asks about food spending
        res = self.client.post(
            "/api/chat/",
            {"message": "How much did I spend on food this month?"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("reply", res.data)
        self.assertIn("tools_executed", res.data)

        # Confirm ChatMessage model saved 2 records (user + assistant)
        msgs = ChatMessage.objects.filter(user=self.user).order_by("created_at")
        self.assertEqual(msgs.count(), 2)
        self.assertEqual(msgs[0].role, ChatMessage.Role.USER)
        self.assertEqual(msgs[1].role, ChatMessage.Role.ASSISTANT)

        # GET /api/chat/history
        hist_res = self.client.get("/api/chat/history/")
        self.assertEqual(hist_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(hist_res.data), 2)
        self.assertEqual(hist_res.data[0]["content"], "How much did I spend on food this month?")

        # DELETE /api/chat/history
        del_res = self.client.delete("/api/chat/history/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ChatMessage.objects.filter(user=self.user).count(), 0)


class UnifiedDashboardSummaryTests(TestCase):
    """
    Phase 9 Tests: Unified Dashboard Summary & Budget Alerts Engine
    - Budget vs actual calculation for current month
    - Category breakdown with benchmark allocations
    - 80% and 100% budget alert generation
    - Integration with Runway, Goals, and Health Score services
    - GET /api/dashboard/summary/ endpoint
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='student_phase9',
            password='testpassword123',
            email='student9@campus.edu',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.profile, _ = UserProfile.objects.get_or_create(
            user=self.user,
            defaults={'college_roll_number': 'ROLL-PHASE9'},
        )
        self.profile.monthly_budget_limit = Decimal("10000.00")
        self.profile.monthly_income = Decimal("20000.00")
        self.profile.save()

        self.statement = Statement.objects.create(
            user=self.user,
            original_filename="october_test.csv",
            status=Statement.Status.DONE,
            transaction_count=5,
        )

    def test_dashboard_summary_empty_state(self):
        """User with no transactions receives healthy empty state."""
        res = self.client.get("/api/dashboard/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual(data['budget']['total_spent_month'], 0.0)
        self.assertEqual(data['budget']['monthly_limit'], 10000.0)
        self.assertEqual(data['budget']['remaining_budget'], 10000.0)
        self.assertEqual(len(data['budget_alerts']), 0)
        self.assertIn('runway', data)
        self.assertIn('goals', data)
        self.assertIn('health_score', data)

    def test_dashboard_summary_80_percent_category_alert(self):
        """
        Food budget is 30% of Rs. 10,000 = Rs. 3,000.
        Spending Rs. 2,550 on Food (85% of share) triggers an 80%+ budget alert.
        """
        today = date.today()
        Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=today,
            amount=Decimal("2550.00"),
            is_debit=True,
            payee_name="Swiggy",
            category="Food",
            status=Transaction.ParseStatus.AUTO,
        )

        res = self.client.get("/api/dashboard/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        alerts = res.data['budget_alerts']
        self.assertTrue(any(a['category'] == 'Food' and a['level'] == 80 for a in alerts))

    def test_dashboard_summary_100_percent_exceeded_alert(self):
        """
        Entertainment budget is 8% of Rs. 10,000 = Rs. 800.
        Spending Rs. 950 on Entertainment (118% of share) triggers a 100%+ danger alert.
        """
        today = date.today()
        Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=today,
            amount=Decimal("950.00"),
            is_debit=True,
            payee_name="PVR Cinemas",
            category="Entertainment",
            status=Transaction.ParseStatus.AUTO,
        )

        res = self.client.get("/api/dashboard/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        alerts = res.data['budget_alerts']
        exceeded = [a for a in alerts if a['category'] == 'Entertainment']
        self.assertTrue(len(exceeded) > 0)
        self.assertEqual(exceeded[0]['level'], 100)
        self.assertEqual(exceeded[0]['severity'], 'danger')

