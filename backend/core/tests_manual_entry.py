"""
tests_manual_entry.py — Tests for manual expense entry endpoint and budget integration.
"""

from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from core.models import Transaction, PayeeMapping, UserProfile, ExpenseCategory


class ManualExpenseEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student_manual", password="password123")
        self.profile = UserProfile.objects.create(
            user=self.user,
            college_roll_number="ROLL-MANUAL-001",
            monthly_budget_limit=Decimal("10000.00"),
            monthly_income=Decimal("15000.00"),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_manual_expense_creation(self):
        """POST /api/transactions/manual creates a confirmed transaction with source=manual."""
        payload = {
            "amount": "120.50",
            "category": "Food",
            "payee_name": "Sri Rama Tiffin Centre",
            "date": str(date.today()),
            "payment_mode": "UPI",
            "save_mapping": False,
        }
        res = self.client.post("/api/transactions/manual/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["message"], "Expense recorded successfully")
        self.assertTrue(res.data["offer_save_mapping"])

        # Check DB transaction
        tx = Transaction.objects.get(pk=res.data["transaction"]["id"])
        self.assertEqual(tx.amount, Decimal("120.50"))
        self.assertEqual(tx.category, "Food")
        self.assertEqual(tx.source, "manual")
        self.assertEqual(tx.status, Transaction.ParseStatus.CONFIRMED)
        self.assertEqual(tx.confidence, 1.0)
        self.assertEqual(tx.payment_mode, "UPI")
        self.assertEqual(tx.categorization_layer, "manual")

    def test_manual_expense_save_mapping(self):
        """Setting save_mapping=True creates PayeeMapping for future transactions."""
        payload = {
            "amount": "45.00",
            "category": "Stationery",
            "payee_name": "Campus Xerox Point",
            "date": str(date.today()),
            "payment_mode": "Cash",
            "save_mapping": True,
        }
        res = self.client.post("/api/transactions/manual/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertFalse(res.data["offer_save_mapping"])

        mapping = PayeeMapping.objects.filter(user=self.user, payee_key="campus xerox point").first()
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.category, "Stationery")

    def test_manual_expense_appears_in_list_and_counts_toward_budget(self):
        """Manually added expense must appear in transactions list and count toward monthly budget."""
        # 1. Add manual expense
        payload = {
            "amount": "500.00",
            "category": "Entertainment",
            "payee_name": "PVR Cinemas",
            "date": str(date.today()),
            "payment_mode": "Card",
        }
        res = self.client.post("/api/transactions/manual/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 2. Check transactions list endpoint
        list_res = self.client.get("/api/transactions/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(list_res.data["count"], 1)
        item = list_res.data["results"][0]
        self.assertEqual(item["source"], "manual")
        self.assertEqual(item["status"], "confirmed")
        self.assertEqual(float(item["amount"]), 500.0)

        # 3. Check dashboard summary endpoint
        dash_res = self.client.get("/api/dashboard/summary/")
        self.assertEqual(dash_res.status_code, status.HTTP_200_OK)
        # Total spent this month should reflect the 500.00 manual expense
        self.assertEqual(dash_res.data["budget"]["total_spent_month"], 500.0)
        self.assertEqual(dash_res.data["budget"]["remaining_budget"], 9500.0)

        # Check category breakdown
        ent_cat = next(
            (c for c in dash_res.data["category_breakdown"] if c["category"] == "Entertainment"),
            None,
        )
        self.assertIsNotNone(ent_cat)
        self.assertEqual(ent_cat["spent"], 500.0)
