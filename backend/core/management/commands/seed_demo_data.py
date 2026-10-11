"""
seed_demo_data.py — Populates demo student user, transactions, statement, and goals.
Run via: python manage.py seed_demo_data
"""

from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import UserProfile, Statement, Transaction, PayeeMapping, Goal


class Command(BaseCommand):
    help = "Seeds demo student account with realistic transactions, goals, and budget alerts."

    def handle(self, *args, **options):
        self.stdout.write("Seeding demo student data...")

        # 1. Create or get demo user
        user, created = User.objects.get_or_create(username="student")
        user.email = "student@campus.edu"
        user.set_password("password123")
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.college_roll_number = "CS2026-089"
        profile.monthly_budget_limit = Decimal("15000.00")
        profile.monthly_income = Decimal("25000.00")
        profile.save()

        # 2. Payee mappings
        mappings = [
            ("swiggy", "Food"),
            ("nescafe", "Food"),
            ("dominos", "Food"),
            ("delhimetro", "Travel"),
            ("uber", "Travel"),
            ("zepto", "Groceries/Shopping"),
            ("spotify", "Subscriptions"),
            ("github", "Subscriptions"),
        ]
        for key, cat in mappings:
            PayeeMapping.objects.update_or_create(
                user=user,
                payee_key=key,
                defaults={"category": cat, "times_confirmed": 3},
            )

        # 3. Create Statement
        stmt, _ = Statement.objects.get_or_create(
            user=user,
            original_filename="october_2026_sbi_statement.csv",
            defaults={
                "status": Statement.Status.DONE,
                "bank_format": "sbi_csv",
                "date_from": date(2026, 10, 1),
                "date_to": date(2026, 10, 11),
                "transaction_count": 14,
            },
        )

        # Clear existing transactions for fresh demo
        Transaction.objects.filter(user=user).delete()

        # 4. Realistic transactions
        # Note: Food totals ~₹3,970 against benchmark share (30% of ₹15,000 = ₹4,500), which is ~88.2% (triggers 80%+ alert)
        demo_txs = [
            # Food
            (date(2026, 10, 1), Decimal("3000.00"), "Hostel Mess Advance", "mess@sbi", "Food", Transaction.ParseStatus.AUTO, 1.0),
            (date(2026, 10, 3), Decimal("85.00"), "Nescafe Campus Kiosk", "nescafe@upi", "Food", Transaction.ParseStatus.AUTO, 0.98),
            (date(2026, 10, 5), Decimal("265.00"), "Swiggy Campus Lunch", "swiggy@axis", "Food", Transaction.ParseStatus.AUTO, 0.95),
            (date(2026, 10, 8), Decimal("480.00"), "Dominos Dorm Pizza", "dominos@icici", "Food", Transaction.ParseStatus.AUTO, 0.96),
            (date(2026, 10, 10), Decimal("140.00"), "Campus Canteen Snacks", "canteen@paytm", "Food", Transaction.ParseStatus.AUTO, 0.92),

            # Travel
            (date(2026, 10, 2), Decimal("500.00"), "Metro Smart Card Recharge", "delhimetro@sbi", "Travel", Transaction.ParseStatus.AUTO, 0.97),
            (date(2026, 10, 7), Decimal("185.00"), "Uber Ride to Railway Station", "uber@hdfc", "Travel", Transaction.ParseStatus.AUTO, 0.94),
            (date(2026, 10, 9), Decimal("70.00"), "Auto Rickshaw UPI", "ramesh.auto@upi", "Travel", Transaction.ParseStatus.AUTO, 0.85),

            # Groceries/Shopping
            (date(2026, 10, 4), Decimal("420.00"), "Zepto Dorm Grocery Snacks", "zepto@icici", "Groceries/Shopping", Transaction.ParseStatus.AUTO, 0.92),
            (date(2026, 10, 8), Decimal("230.00"), "Campus Stationery & Notebooks", "campus.books@upi", "Groceries/Shopping", Transaction.ParseStatus.AUTO, 0.89),

            # Subscriptions
            (date(2026, 10, 1), Decimal("59.00"), "Spotify Student Plan", "spotify@paytm", "Subscriptions", Transaction.ParseStatus.AUTO, 0.99),
            (date(2026, 10, 3), Decimal("199.00"), "GitHub Student Pro Pack", "github@paypal", "Subscriptions", Transaction.ParseStatus.AUTO, 0.99),

            # Academics
            (date(2026, 10, 6), Decimal("320.00"), "Engineering Lab Manuals", "univ.press@sbi", "Academics", Transaction.ParseStatus.AUTO, 0.91),

            # Pending & Verify items for the review pipeline
            (date(2026, 10, 10), Decimal("380.00"), "UPI/88231940/Sharma Xerox & Print", "sharma.print@upi", "Academics", Transaction.ParseStatus.VERIFY, 0.65),
            (date(2026, 10, 11), Decimal("750.00"), "AMZN-IN*STUDY-LAMP", "amzn@paytm", "Groceries/Shopping", Transaction.ParseStatus.PENDING, 0.42),
        ]

        for tx_date, amount, payee, upi, cat, stat, conf in demo_txs:
            Transaction.objects.create(
                statement=stmt,
                user=user,
                date=tx_date,
                amount=amount,
                is_debit=True,
                payee_name=payee,
                upi_id=upi,
                remark=payee,
                category=cat,
                confidence=conf,
                status=stat,
            )

        # 5. Goals
        Goal.objects.filter(user=user).delete()
        Goal.objects.create(
            user=user,
            name="MacBook Pro for Coding",
            target_amount=Decimal("80000.00"),
            saved_so_far=Decimal("26000.00"),
            deadline=date(2026, 12, 31),
            status=Goal.Status.ACTIVE,
        )
        Goal.objects.create(
            user=user,
            name="Placement Coding Bootcamp",
            target_amount=Decimal("6000.00"),
            saved_so_far=Decimal("4200.00"),
            deadline=date(2026, 11, 15),
            status=Goal.Status.ACTIVE,
        )

        self.stdout.write(self.style.SUCCESS(
            "Successfully seeded demo student data!\n"
            "Credentials: username='student', password='password123'\n"
            f"Created {len(demo_txs)} transactions, 2 goals, and configured budget limit Rs. 15,000."
        ))

