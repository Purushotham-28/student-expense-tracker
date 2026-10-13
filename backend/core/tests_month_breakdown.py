from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from .models import Statement, Transaction, ExpenseCategory, UserProfile
from .services.dashboard_service import (
    get_category_breakdown_for_month,
    get_available_months_for_user,
)


class MonthBreakdownTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student_month_test",
            password="testpassword123",
            email="monthtest@college.edu",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            college_roll_number="MTH-1001",
            monthly_income=Decimal("20000.00"),
            monthly_budget_limit=Decimal("15000.00"),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.statement = Statement.objects.create(
            user=self.user,
            original_filename="bank_statement.csv",
            status=Statement.Status.DONE,
            transaction_count=5,
        )

        # 1. September 2026 transactions (Active)
        self.tx_sep_food = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 10),
            amount=Decimal("350.00"),
            is_debit=True,
            payee_name="Campus Canteen",
            category=ExpenseCategory.FOOD,
            status=Transaction.ParseStatus.CONFIRMED,
        )
        self.tx_sep_travel = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 20),
            amount=Decimal("150.00"),
            is_debit=True,
            payee_name="Metro Rail",
            category=ExpenseCategory.TRAVEL,
            status=Transaction.ParseStatus.CONFIRMED,
        )

        # 2. September 2026 Soft-Deleted transaction (Must be excluded)
        self.tx_sep_deleted = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 12),
            amount=Decimal("999.00"),
            is_debit=True,
            is_deleted=True,
            payee_name="Wrong Charge",
            category=ExpenseCategory.OTHER,
            status=Transaction.ParseStatus.CONFIRMED,
        )

        # 3. September 2026 Duplicate transaction (Must be excluded)
        self.tx_sep_dup = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 9, 10),
            amount=Decimal("350.00"),
            is_debit=True,
            is_duplicate=True,
            payee_name="Campus Canteen Duplicate",
            category=ExpenseCategory.FOOD,
            status=Transaction.ParseStatus.CONFIRMED,
        )

        # 4. October 2026 transaction (Should NOT appear in September query)
        self.tx_oct_grocery = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date(2026, 10, 5),
            amount=Decimal("1200.00"),
            is_debit=True,
            payee_name="SuperMart",
            category=ExpenseCategory.GROCERIES_SHOPPING,
            status=Transaction.ParseStatus.CONFIRMED,
        )

    def test_past_month_breakdown_endpoint(self):
        """
        Requesting category breakdown for a specific past month returns only active
        transactions from that month, excluding other months, soft-deleted, and duplicates.
        """
        response = self.client.get('/api/dashboard/category-breakdown/', {'month': 9, 'year': 2026})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data['year'], 2026)
        self.assertEqual(data['month'], 9)
        self.assertEqual(data['month_key'], '2026-09')
        self.assertEqual(data['month_label'], 'September 2026')
        self.assertEqual(data['transaction_count'], 2)

        # Total spend: 350.00 (Food) + 150.00 (Travel) = 500.00
        # Excluded: 999.00 (deleted), 350.00 (dup), 1200.00 (October)
        self.assertEqual(data['total_spent_month'], 500.00)

        # Category breakdown checks
        categories = {item['category']: item for item in data['category_breakdown']}
        self.assertEqual(categories['Food']['spent'], 350.00)
        self.assertEqual(categories['Food']['transaction_count'], 1)
        self.assertEqual(categories['Travel']['spent'], 150.00)
        self.assertEqual(categories['Travel']['transaction_count'], 1)
        self.assertEqual(categories['Groceries/Shopping']['spent'], 0.0)

    def test_empty_month_breakdown_endpoint(self):
        """
        A month with no transactions returns an empty/zero result rather than an error.
        """
        response = self.client.get('/api/dashboard/category-breakdown/', {'month': 1, 'year': 2025})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data['year'], 2025)
        self.assertEqual(data['month'], 1)
        self.assertEqual(data['month_key'], '2025-01')
        self.assertEqual(data['transaction_count'], 0)
        self.assertEqual(data['total_spent_month'], 0.0)
        self.assertEqual(data['budget']['total_spent_month'], 0.0)
        self.assertEqual(data['budget']['percent_used'], 0.0)

        # All categories have spent == 0
        for item in data['category_breakdown']:
            self.assertEqual(item['spent'], 0.0)

    def test_default_current_month_when_no_params(self):
        """
        Omitting month/year defaults to the current month/year.
        """
        response = self.client.get('/api/dashboard/category-breakdown/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        today = date.today()
        self.assertEqual(response.data['year'], today.year)
        self.assertEqual(response.data['month'], today.month)
        self.assertTrue(response.data['is_current_month'])

    def test_available_months_endpoint(self):
        """
        Available months endpoint returns all 12 calendar months for the active year.
        """
        response = self.client.get('/api/dashboard/available-months/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        months = response.data['available_months']
        # All 12 calendar months for 2026 are included
        for m in range(1, 13):
            self.assertIn(f"2026-{m:02d}", months)

    def test_all_months_aggregate_breakdown(self):
        """
        Requesting month='all' aggregates transactions across all months of the year.
        """
        response = self.client.get('/api/dashboard/category-breakdown/', {'month': 'all', 'year': 2026})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data['month_key'], '2026-all')
        self.assertTrue(data['is_all_months'])
        # Sep Food (350) + Sep Travel (150) + Oct Groceries (1200) = 1700.00
        self.assertEqual(data['total_spent_month'], 1700.00)
        self.assertEqual(data['transaction_count'], 3)

