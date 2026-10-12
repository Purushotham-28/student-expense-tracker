"""
tests_keyword_layer.py — Tests for Merchant Keyword Dictionary, 3-layer pipeline, and accuracy improvements.
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User

from core.models import Transaction, PayeeMapping, MerchantKeyword, ExpenseCategory
from core.services.categorization_service import (
    categorize_transaction,
    match_merchant_keyword,
    reload_merchant_keywords,
)


class MerchantKeywordLayerTests(TestCase):
    """Test merchant keyword matching and 3-layer pipeline execution."""

    def setUp(self):
        reload_merchant_keywords()
        self.user = User.objects.create_user(username="teststudent", password="password123")

    def test_direct_keyword_matches(self):
        cat, conf = match_merchant_keyword("BookMyShow Tickets", "Cinema hall 3D")
        self.assertEqual(cat, ExpenseCategory.ENTERTAINMENT)
        self.assertGreaterEqual(conf, 0.90)

        cat, conf = match_merchant_keyword("Sri Rama Tiffin Centre", "Morning idli")
        self.assertEqual(cat, ExpenseCategory.FOOD)

        cat, conf = match_merchant_keyword("Ganesh Chat Bhandar", "Pani puri")
        self.assertEqual(cat, ExpenseCategory.FOOD)

        cat, conf = match_merchant_keyword("Laxmi General Store", "Provisions soap")
        self.assertEqual(cat, ExpenseCategory.GROCERIES_SHOPPING)

        cat, conf = match_merchant_keyword("Balaji Book World", "Engineering books")
        self.assertEqual(cat, ExpenseCategory.STATIONERY)

        cat, conf = match_merchant_keyword("Bescom Electricity Bill", "Hostel power")
        self.assertEqual(cat, ExpenseCategory.UTILITIES)

    def test_pipeline_layer_order(self):
        # 1. User has explicit PayeeMapping -> Layer 1 must win over keyword
        PayeeMapping.objects.create(
            user=self.user,
            payee_key="bookmyshow",
            category=ExpenseCategory.OTHER,  # User override
        )
        tx = Transaction.objects.create(
            user=self.user,
            payee_name="BookMyShow",
            amount=Decimal("350.00"),
            is_debit=True,
        )
        cat, conf, layer = categorize_transaction(tx, save=True)
        self.assertEqual(layer, "payee_mapping")
        self.assertEqual(cat, ExpenseCategory.OTHER)
        self.assertEqual(conf, 1.0)
        self.assertEqual(tx.categorization_layer, "payee_mapping")

        # 2. No PayeeMapping, but matching merchant keyword -> Layer 2 wins
        tx2 = Transaction.objects.create(
            user=self.user,
            payee_name="Campus Canteen Special",
            amount=Decimal("80.00"),
            is_debit=True,
        )
        cat2, conf2, layer2 = categorize_transaction(tx2, save=True)
        self.assertEqual(layer2, "merchant_keyword")
        self.assertEqual(cat2, ExpenseCategory.FOOD)
        self.assertGreaterEqual(conf2, 0.90)
        self.assertEqual(tx2.categorization_layer, "merchant_keyword")

        # 3. Arbitrary unknown payee -> Layer 3 (ML Model) runs
        tx3 = Transaction.objects.create(
            user=self.user,
            payee_name="Unknown Unregistered Person 998877",
            amount=Decimal("45.00"),
            is_debit=True,
        )
        cat3, conf3, layer3 = categorize_transaction(tx3, save=True)
        self.assertEqual(layer3, "ml_model")
        self.assertEqual(tx3.categorization_layer, "ml_model")

    def test_dynamic_keyword_extension(self):
        """Verify adding a keyword to DB table dynamically categorizes without code changes."""
        MerchantKeyword.objects.create(
            keyword="customcampusprint",
            category=ExpenseCategory.STATIONERY,
            priority=50,
        )
        reload_merchant_keywords()

        cat, conf = match_merchant_keyword("customcampusprint", "prints")
        self.assertEqual(cat, ExpenseCategory.STATIONERY)

    def test_benchmark_30_real_transactions(self):
        """Confirm 30 real-world benchmark transactions achieve high accuracy (> 95%)."""
        benchmark = [
            ("BookMyShow", "bookmyshow@axb", "BookMyShow movie ticket Kalki 3D", ExpenseCategory.ENTERTAINMENT),
            ("PVR Cinemas", "pvrcinemas@hdfcbank", "PVR cinemas popcorn and ticket", ExpenseCategory.ENTERTAINMENT),
            ("INOX Leisure", "inox@axisbank", "Inox evening movie show", ExpenseCategory.ENTERTAINMENT),
            ("Steam Games", "steam@paytm", "Steam summer sale game purchase", ExpenseCategory.ENTERTAINMENT),
            ("Sri Rama Tiffin Centre", "tiffin@upi", "Idli vada tiffin breakfast", ExpenseCategory.FOOD),
            ("Annapurna Mess", "mess@upi", "Monthly mess thali extra bill", ExpenseCategory.FOOD),
            ("Ganesh Chat Bhandar", "chatbhandar@upi", "Pani puri sev puri bhandar", ExpenseCategory.FOOD),
            ("Campus Canteen", "canteen@upi", "Lunch meal special canteen", ExpenseCategory.FOOD),
            ("Sharma Hotel", "sharmahotel@paytm", "Dinner roti curry hotel", ExpenseCategory.FOOD),
            ("Bawarchi Restaurant", "bawarchi@upi", "Chicken biryani dinner restaurant", ExpenseCategory.FOOD),
            ("Zomato", "zomato@icici", "Zomato food delivery order", ExpenseCategory.FOOD),
            ("Swiggy", "swiggy@hdfcbank", "Swiggy lunch delivery order", ExpenseCategory.FOOD),
            ("Laxmi General Store", "generalstore@upi", "Provisions soap detergent daily items", ExpenseCategory.GROCERIES_SHOPPING),
            ("Sri Balaji Kirana", "kirana@upi", "Atta dal cooking oil kirana store", ExpenseCategory.GROCERIES_SHOPPING),
            ("Sree Supermarket", "supermarket@paytm", "Monthly hostel groceries supermarket", ExpenseCategory.GROCERIES_SHOPPING),
            ("Blinkit", "blinkit@icici", "Blinkit 10 mins grocery essentials", ExpenseCategory.GROCERIES_SHOPPING),
            ("Zepto", "zepto@hdfcbank", "Zepto quick snacks and milk delivery", ExpenseCategory.GROCERIES_SHOPPING),
            ("DMart Ready", "dmart@sbi", "DMart monthly provisions cart", ExpenseCategory.GROCERIES_SHOPPING),
            ("Sree Balaji Book World", "bookworld@paytm", "Engineering books and notebooks", ExpenseCategory.STATIONERY),
            ("Parimala Internet & Xerox", "xerox@upi", "Assignment xerox printout copies", ExpenseCategory.STATIONERY),
            ("College Book Depot", "bookdepot@sbi", "Drawing sheets drafter pencil set", ExpenseCategory.STATIONERY),
            ("Students Stationery Store", "stationery@upi", "Classmate notebooks pens markers", ExpenseCategory.STATIONERY),
            ("Universal Xerox & Spiral", "universal@upi", "Project report spiral binding", ExpenseCategory.STATIONERY),
            ("GATE Coaching Institute", "gatecoaching@hdfcbank", "GATE mock test series coaching fee", ExpenseCategory.ACADEMICS),
            ("University Exam Fee", "examfee@sbi", "Semester exam evaluation fee", ExpenseCategory.ACADEMICS),
            ("Coursera Learning", "coursera@paypal", "Python deep learning course certificate", ExpenseCategory.ACADEMICS),
            ("Bescom Electricity Bill", "bescom@sbi", "Hostel room electric meter bill", ExpenseCategory.UTILITIES),
            ("Airtel Prepaid Recharge", "airtel@axisbank", "Smartphone 1.5GB daily pack recharge", ExpenseCategory.UTILITIES),
            ("Jio Recharge", "jiorecharge@paytm", "Jio prepaid 5G unlimited recharge", ExpenseCategory.UTILITIES),
            ("ACT Fibernet Broadband", "actfibernet@hdfcbank", "Monthly hostel wifi broadband bill", ExpenseCategory.UTILITIES),
        ]
        correct = 0
        for name, upi, rem, expected in benchmark:
            tx = Transaction(payee_name=name, upi_id=upi, remark=rem, amount=Decimal("200.00"), is_debit=True)
            cat, conf, layer = categorize_transaction(tx, save=False)
            if cat == expected:
                correct += 1
        accuracy = correct / len(benchmark)
        self.assertGreaterEqual(accuracy, 0.95)
