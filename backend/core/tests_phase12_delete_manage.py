from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from .models import Statement, Transaction, PayeeMapping, ExpenseCategory, UserProfile
from .services.dashboard_service import get_dashboard_summary


class Phase12DeleteManageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student_delete_test",
            password="testpassword123",
            email="deltest@college.edu",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            college_roll_number="DEL-9999",
            monthly_income=Decimal("20000.00"),
            monthly_budget_limit=Decimal("15000.00"),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.statement = Statement.objects.create(
            user=self.user,
            original_filename="sample_test_statement.csv",
            status=Statement.Status.DONE,
            transaction_count=3,
        )

        self.tx1 = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date.today(),
            amount=Decimal("450.00"),
            is_debit=True,
            payee_name="Ramesh Grocery Store",
            upi_id="ramesh@upi",
            category=ExpenseCategory.GROCERIES_SHOPPING,
            status=Transaction.ParseStatus.CONFIRMED,
        )

        self.tx2 = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date.today(),
            amount=Decimal("120.00"),
            is_debit=True,
            payee_name="Campus Canteen",
            upi_id="canteen@upi",
            category=ExpenseCategory.FOOD,
            status=Transaction.ParseStatus.CONFIRMED,
        )

        # Create a learned PayeeMapping
        self.mapping = PayeeMapping.objects.create(
            user=self.user,
            payee_key="ramesh@upi",
            category=ExpenseCategory.GROCERIES_SHOPPING,
            times_confirmed=3,
        )

    def test_soft_delete_single_transaction_preserves_payee_mapping(self):
        """Deleting a transaction soft-deletes it, sets deleted_at, and preserves PayeeMapping."""
        res = self.client.delete(f"/api/transactions/{self.tx1.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["payee_mapping_preserved"])

        self.tx1.refresh_from_db()
        self.assertTrue(self.tx1.is_deleted)
        self.assertIsNotNone(self.tx1.deleted_at)

        # PayeeMapping MUST still exist!
        self.assertTrue(PayeeMapping.objects.filter(id=self.mapping.id).exists())

    def test_deleted_transaction_excluded_from_active_list_and_present_in_trash(self):
        """Active transactions list excludes deleted ones; deleted tab returns them."""
        # Delete tx1
        self.tx1.is_deleted = True
        self.tx1.save()

        # Default list (active only)
        res_active = self.client.get("/api/transactions/")
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        active_ids = [t["id"] for t in res_active.data["results"]]
        self.assertNotIn(self.tx1.id, active_ids)
        self.assertIn(self.tx2.id, active_ids)
        self.assertEqual(res_active.data["counts"]["deleted"], 1)

        # Recently deleted list
        res_deleted = self.client.get("/api/transactions/?status=deleted")
        self.assertEqual(res_deleted.status_code, status.HTTP_200_OK)
        deleted_ids = [t["id"] for t in res_deleted.data["results"]]
        self.assertIn(self.tx1.id, deleted_ids)
        self.assertNotIn(self.tx2.id, deleted_ids)

    def test_restore_single_transaction(self):
        """A soft-deleted transaction can be restored with one tap."""
        self.tx1.is_deleted = True
        self.tx1.save()

        res = self.client.post(f"/api/transactions/{self.tx1.id}/restore/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.tx1.refresh_from_db()
        self.assertFalse(self.tx1.is_deleted)
        self.assertIsNone(self.tx1.deleted_at)

    def test_bulk_delete_and_bulk_restore(self):
        """Bulk delete and bulk restore handle multiple IDs properly."""
        tx3 = Transaction.objects.create(
            statement=self.statement,
            user=self.user,
            date=date.today(),
            amount=Decimal("80.00"),
            is_debit=True,
            payee_name="Xerox Shop",
            category=ExpenseCategory.STATIONERY,
        )

        # Bulk delete tx1 and tx3
        res_del = self.client.post("/api/transactions/bulk-delete/", {"ids": [self.tx1.id, tx3.id]}, format="json")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertEqual(res_del.data["deleted_count"], 2)

        self.tx1.refresh_from_db()
        tx3.refresh_from_db()
        self.assertTrue(self.tx1.is_deleted)
        self.assertTrue(tx3.is_deleted)

        # Bulk restore
        res_rest = self.client.post("/api/transactions/bulk-restore/", {"ids": [self.tx1.id, tx3.id]}, format="json")
        self.assertEqual(res_rest.status_code, status.HTTP_200_OK)
        self.assertEqual(res_rest.data["restored_count"], 2)

        self.tx1.refresh_from_db()
        tx3.refresh_from_db()
        self.assertFalse(self.tx1.is_deleted)
        self.assertFalse(tx3.is_deleted)

    def test_delete_entire_statement_soft_deletes_statement_and_all_transactions(self):
        """Deleting a statement soft-deletes the statement and its children."""
        res = self.client.delete(f"/api/statements/{self.statement.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["payee_mapping_preserved"])

        self.statement.refresh_from_db()
        self.assertTrue(self.statement.is_deleted)
        self.assertIsNotNone(self.statement.deleted_at)

        self.tx1.refresh_from_db()
        self.tx2.refresh_from_db()
        self.assertTrue(self.tx1.is_deleted)
        self.assertTrue(self.tx2.is_deleted)

        # Statement does not appear in active statements list
        list_res = self.client.get("/api/statements/")
        stmt_ids = [s["id"] for s in list_res.data]
        self.assertNotIn(self.statement.id, stmt_ids)

    def test_deleted_transaction_does_not_inflate_dashboard_budget(self):
        """Deleted transactions are immediately excluded from dashboard spend calculations."""
        # Initial spend: 450 + 120 = 570
        initial_dash = get_dashboard_summary(self.user)
        self.assertEqual(initial_dash["budget"]["total_spent_month"], 570.0)

        # Delete tx1 (450)
        self.client.delete(f"/api/transactions/{self.tx1.id}/")

        # Spend after deletion must be 120.0
        updated_dash = get_dashboard_summary(self.user)
        self.assertEqual(updated_dash["budget"]["total_spent_month"], 120.0)
