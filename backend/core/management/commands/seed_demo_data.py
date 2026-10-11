"""
seed_demo_data.py — Populates demo student user with 3 months of realistic
synthetic UPI transaction history, goals, and budget limits, then runs categorization
and the health score so the dashboard is immediately demo-ready.

Usage:
    python manage.py seed_demo_data
"""

from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import UserProfile, Statement, Transaction, PayeeMapping, Goal
from core.services.categorization_service import (
    normalize_payee,
    route_status_from_confidence,
)
from core.services.health_score_service import get_user_financial_health_score
from core.services.forecasting_service import calculate_cash_flow_runway
from core.services.dashboard_service import get_dashboard_summary


class Command(BaseCommand):
    help = (
        "Seeds demo student account with 3 months of realistic UPI transactions, "
        "ambiguous payees for review, adaptive goals, and precomputes health score."
    )

    def handle(self, *args, **options):
        self.stdout.write("--> Seeding 3 months of demo student data (Aug - Oct 2026)...")

        # 1. Create or get demo user
        user, created = User.objects.get_or_create(username="student")
        user.email = "student@campus.edu"
        user.set_password("password123")
        user.first_name = "Indrajeet"
        user.last_name = "Student"
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.college_roll_number = "CS2026-089"
        profile.monthly_budget_limit = Decimal("15000.00")
        profile.monthly_income = Decimal("25000.00")
        profile.save()

        # 2. Payee mappings (core differentiator: learned mappings for known payees)
        learned_mappings = [
            ("swiggy", "Food", 12),
            ("zomato", "Food", 9),
            ("nescafe", "Food", 7),
            ("dominos", "Food", 4),
            ("delhimetro", "Travel", 15),
            ("uber", "Travel", 8),
            ("ola", "Travel", 5),
            ("zepto", "Groceries/Shopping", 11),
            ("blinkit", "Groceries/Shopping", 6),
            ("spotify", "Subscriptions", 3),
            ("netflix", "Subscriptions", 3),
            ("github", "Subscriptions", 2),
            ("campus.hostel", "Rent/Hostel", 3),
        ]
        for key, cat, confirmed_count in learned_mappings:
            PayeeMapping.objects.update_or_create(
                user=user,
                payee_key=key,
                defaults={"category": cat, "times_confirmed": confirmed_count},
            )

        # 3. Create Statement records for each month
        statements = {}
        month_specs = [
            ("aug_2026_sbi_statement.csv", date(2026, 8, 1), date(2026, 8, 31)),
            ("sep_2026_sbi_statement.csv", date(2026, 9, 1), date(2026, 9, 30)),
            ("oct_2026_sbi_statement.csv", date(2026, 10, 1), date(2026, 10, 11)),
        ]
        for filename, start_d, end_d in month_specs:
            stmt, _ = Statement.objects.update_or_create(
                user=user,
                original_filename=filename,
                defaults={
                    "status": Statement.Status.DONE,
                    "bank_format": "sbi_csv",
                    "date_from": start_d,
                    "date_to": end_d,
                },
            )
            statements[filename] = stmt

        # Clear existing transactions for fresh deterministic seed
        Transaction.objects.filter(user=user).delete()

        # 4. Realistic 3-Month Synthetic Transactions
        # Fields: (date, amount, payee, upi, remark, category, status, confidence, is_debit, statement_key)
        all_transactions_data = [
            # ──────────────────────────────────────────────────────────────────
            # AUGUST 2026 (Month 1: Total debit ~Rs. 13,850 vs Income Rs. 25,000)
            # ──────────────────────────────────────────────────────────────────
            (date(2026, 8, 1), Decimal("25000.00"), "Semester Parent Allowance", "parent@sbi", "Monthly Student Stipend", "Other", Transaction.ParseStatus.AUTO, 1.0, False, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 1), Decimal("3500.00"), "Hostel Maintenance & Mess Fee", "campus.hostel@sbi", "Hostel Room Rent Aug", "Rent/Hostel", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 2), Decimal("500.00"), "Delhi Metro Smart Card", "delhimetro@sbi", "Metro Recharge Card 2891", "Travel", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 3), Decimal("180.00"), "Nescafe Campus Kiosk", "nescafe@upi", "Coffee & Croissant", "Food", Transaction.ParseStatus.AUTO, 0.98, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 4), Decimal("265.00"), "Swiggy Campus Delivery", "swiggy@axis", "Biryani Bowl Lunch", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 5), Decimal("59.00"), "Spotify Student Plan", "spotify@paytm", "Monthly Music Student Discount", "Subscriptions", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 6), Decimal("420.00"), "Zepto Dorm Grocery Snacks", "zepto@hdfc", "Maggi, chips & milk", "Groceries/Shopping", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 8), Decimal("160.00"), "Uber Ride to Metro Station", "uber@hdfc", "Campus to Central Metro", "Travel", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 10), Decimal("199.00"), "GitHub Student Pro Pack", "github@paypal", "Cloud Dev Subscription", "Subscriptions", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 12), Decimal("340.00"), "Zomato Dorm Dinner", "zomato@icici", "Paneer Roll & Shake", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 14), Decimal("450.00"), "Campus Bookstore", "campus.books@upi", "Data Structures Textbook Xerox", "Academics", Transaction.ParseStatus.AUTO, 0.92, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 16), Decimal("70.00"), "Auto Rickshaw UPI", "ramesh.auto@upi", "Market to Campus Gate", "Travel", Transaction.ParseStatus.AUTO, 0.88, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 18), Decimal("520.00"), "Dominos Pizza Night", "dominos@icici", "Pizza slice & garlic bread", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 20), Decimal("310.00"), "Blinkit Late Night Snacks", "blinkit@axis", "Dry fruits & cookies", "Groceries/Shopping", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 22), Decimal("220.00"), "Swiggy Lunch Order", "swiggy@axis", "South Indian Thali", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 24), Decimal("199.00"), "Netflix Dorm Screen Share", "netflix@icici", "Monthly plan student share", "Subscriptions", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 26), Decimal("650.00"), "Splitwise Dinner Settlement", "rohit.split@okhdfc", "Weekend group cafe dinner", "Friend/Split", Transaction.ParseStatus.AUTO, 0.91, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 28), Decimal("180.00"), "Uber Trip to Library", "uber@hdfc", "Uber Go ride", "Travel", Transaction.ParseStatus.AUTO, 1.0, True, "aug_2026_sbi_statement.csv"),
            (date(2026, 8, 30), Decimal("320.00"), "PVR Cinemas Student Pass", "pvr.cinemas@paytm", "Weekend movie ticket", "Entertainment", Transaction.ParseStatus.AUTO, 0.95, True, "aug_2026_sbi_statement.csv"),

            # ──────────────────────────────────────────────────────────────────
            # SEPTEMBER 2026 (Month 2: Total debit ~Rs. 14,200 vs Income Rs. 25,000)
            # ──────────────────────────────────────────────────────────────────
            (date(2026, 9, 1), Decimal("25000.00"), "Semester Parent Allowance", "parent@sbi", "Monthly Student Stipend Sep", "Other", Transaction.ParseStatus.AUTO, 1.0, False, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 1), Decimal("3500.00"), "Hostel Maintenance & Mess Fee", "campus.hostel@sbi", "Hostel Room Rent Sep", "Rent/Hostel", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 2), Decimal("500.00"), "Delhi Metro Smart Card", "delhimetro@sbi", "Metro Topup Card 2891", "Travel", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 3), Decimal("185.00"), "Nescafe Campus Kiosk", "nescafe@upi", "Cappuccino & Veg Puff", "Food", Transaction.ParseStatus.AUTO, 0.98, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 4), Decimal("310.00"), "Swiggy Campus Delivery", "swiggy@axis", "Dal Makhani & Roti Combo", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 5), Decimal("59.00"), "Spotify Student Plan", "spotify@paytm", "Spotify Sept Recurring", "Subscriptions", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 7), Decimal("480.00"), "Zepto Dorm Grocery Snacks", "zepto@hdfc", "Milk, bread, butter, coffee", "Groceries/Shopping", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 9), Decimal("175.00"), "Uber Ride to Exam Hall", "uber@hdfc", "Campus to City Center", "Travel", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 11), Decimal("199.00"), "GitHub Student Pro Pack", "github@paypal", "GitHub Sept Charge", "Subscriptions", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 13), Decimal("295.00"), "Zomato Dorm Dinner", "zomato@icici", "Fried Rice & Manchurian", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 15), Decimal("620.00"), "Amazon Bookstore Order", "amazon.books@axis", "Operating Systems textbook", "Academics", Transaction.ParseStatus.AUTO, 0.94, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 17), Decimal("80.00"), "Auto Rickshaw UPI", "ramesh.auto@upi", "Station to Hostel", "Travel", Transaction.ParseStatus.AUTO, 0.88, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 19), Decimal("480.00"), "Dominos Dorm Pizza", "dominos@icici", "Farmhouse medium pizza", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 21), Decimal("340.00"), "Blinkit Dorm Snacks", "blinkit@axis", "Instant oats & noodles", "Groceries/Shopping", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 23), Decimal("245.00"), "Swiggy Lunch Order", "swiggy@axis", "Chole Bhature lunch", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 25), Decimal("199.00"), "Netflix Dorm Screen Share", "netflix@icici", "Netflix Sept Share", "Subscriptions", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 27), Decimal("750.00"), "Splitwise Dinner Settlement", "rohit.split@okhdfc", "Fest celebration food share", "Friend/Split", Transaction.ParseStatus.AUTO, 0.93, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 28), Decimal("165.00"), "Uber Ride to Lab", "uber@hdfc", "Uber Go Campus", "Travel", Transaction.ParseStatus.AUTO, 1.0, True, "sep_2026_sbi_statement.csv"),
            (date(2026, 9, 29), Decimal("350.00"), "PVR Cinemas Movie", "pvr.cinemas@paytm", "College friends movie outing", "Entertainment", Transaction.ParseStatus.AUTO, 0.96, True, "sep_2026_sbi_statement.csv"),

            # ──────────────────────────────────────────────────────────────────
            # OCTOBER 2026 (Month 3: Current Month - 15 Transactions)
            # Designed to trigger the 80%+ Food Budget Alert and have Ambiguous items in Review
            # ──────────────────────────────────────────────────────────────────
            (date(2026, 10, 1), Decimal("25000.00"), "Semester Parent Allowance", "parent@sbi", "Monthly Student Stipend Oct", "Other", Transaction.ParseStatus.AUTO, 1.0, False, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 1), Decimal("3000.00"), "Hostel Mess Advance", "mess@sbi", "Hostel Room & Mess Advance", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 1), Decimal("59.00"), "Spotify Student Plan", "spotify@paytm", "Monthly Student Spotify", "Subscriptions", Transaction.ParseStatus.AUTO, 1.0, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 2), Decimal("500.00"), "Metro Smart Card Recharge", "delhimetro@sbi", "Smart Card Topup", "Travel", Transaction.ParseStatus.AUTO, 1.0, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 3), Decimal("85.00"), "Nescafe Campus Kiosk", "nescafe@upi", "Iced Tea & Sandwich", "Food", Transaction.ParseStatus.AUTO, 0.98, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 3), Decimal("199.00"), "GitHub Student Pro Pack", "github@paypal", "Oct Developer Tooling", "Subscriptions", Transaction.ParseStatus.AUTO, 1.0, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 4), Decimal("420.00"), "Zepto Dorm Grocery Snacks", "zepto@hdfc", "Maggi, chips & juice", "Groceries/Shopping", Transaction.ParseStatus.AUTO, 1.0, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 5), Decimal("265.00"), "Swiggy Campus Lunch", "swiggy@axis", "Biryani Bowl Lunch", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 6), Decimal("320.00"), "Engineering Lab Manuals", "univ.press@sbi", "Lab manual printing", "Academics", Transaction.ParseStatus.AUTO, 0.91, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 7), Decimal("185.00"), "Uber Ride to Railway Station", "uber@hdfc", "Uber Go ride to station", "Travel", Transaction.ParseStatus.AUTO, 1.0, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 8), Decimal("480.00"), "Dominos Dorm Pizza", "dominos@icici", "Pizza Night with roommate", "Food", Transaction.ParseStatus.AUTO, 1.0, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 8), Decimal("230.00"), "Campus Stationery & Notebooks", "campus.books@upi", "Spiral notebooks & pens", "Groceries/Shopping", Transaction.ParseStatus.AUTO, 0.89, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 9), Decimal("70.00"), "Auto Rickshaw UPI", "ramesh.auto@upi", "Auto fare gate 2", "Travel", Transaction.ParseStatus.AUTO, 0.85, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 10), Decimal("140.00"), "Campus Canteen Snacks", "canteen@paytm", "Evening Samosa & Tea", "Food", Transaction.ParseStatus.AUTO, 0.92, True, "oct_2026_sbi_statement.csv"),

            # ──────────────────────────────────────────────────────────────────
            # Ambiguous items specifically placed in the "Needs your review" queue
            # to showcase Phase 4 confidence routing and one-tap payee confirmation:
            # ──────────────────────────────────────────────────────────────────
            (date(2026, 10, 10), Decimal("380.00"), "UPI/88231940/Sharma Xerox & Print", "sharma.print@upi", "Project Report Xerox Printout", "Academics", Transaction.ParseStatus.VERIFY, 0.65, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 11), Decimal("750.00"), "AMZN-IN*STUDY-LAMP", "amzn@paytm", "Dorm Desk LED Study Lamp", "Groceries/Shopping", Transaction.ParseStatus.PENDING, 0.42, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 11), Decimal("320.00"), "GPay/Chirag/Mess-Split", "chirag.split@oksbi", "Shared weekend meal split", "Friend/Split", Transaction.ParseStatus.VERIFY, 0.68, True, "oct_2026_sbi_statement.csv"),
            (date(2026, 10, 11), Decimal("490.00"), "UPI/Gupta Kirana & General Store", "gupta.store@upi", "Toiletries & groceries", "Groceries/Shopping", Transaction.ParseStatus.PENDING, 0.46, True, "oct_2026_sbi_statement.csv"),
        ]

        # Bulk insert transaction records
        created_txs = []
        for (tx_date, amount, payee, upi, remark, cat, stat, conf, is_debit, stmt_key) in all_transactions_data:
            stmt = statements[stmt_key]
            tx = Transaction.objects.create(
                statement=stmt,
                user=user,
                date=tx_date,
                amount=amount,
                is_debit=is_debit,
                payee_name=payee,
                upi_id=upi,
                remark=remark,
                category=cat,
                confidence=conf,
                status=stat,
            )
            created_txs.append(tx)

        # Update statement transaction counts
        for filename, stmt in statements.items():
            cnt = Transaction.objects.filter(statement=stmt).count()
            stmt.transaction_count = cnt
            stmt.save(update_fields=["transaction_count"])

        # 5. Realistic Savings Goals
        Goal.objects.filter(user=user).delete()
        g1 = Goal.objects.create(
            user=user,
            name="MacBook Pro for Coding",
            target_amount=Decimal("80000.00"),
            saved_so_far=Decimal("26000.00"),
            deadline=date(2026, 12, 31),
            status=Goal.Status.ACTIVE,
        )
        g2 = Goal.objects.create(
            user=user,
            name="Placement Coding Bootcamp",
            target_amount=Decimal("6000.00"),
            saved_so_far=Decimal("4200.00"),
            deadline=date(2026, 11, 15),
            status=Goal.Status.ACTIVE,
        )
        g3 = Goal.objects.create(
            user=user,
            name="Semester Exam & Certification Fee",
            target_amount=Decimal("3500.00"),
            saved_so_far=Decimal("3500.00"),
            deadline=date(2026, 10, 5),
            status=Goal.Status.DONE,
        )

        # 6. Run and verify core analytical engines
        self.stdout.write("--> Running Financial Health Score engine...")
        health_score = get_user_financial_health_score(user)

        self.stdout.write("--> Running Cash-Flow Runway & ARIMA forecast engine...")
        runway = calculate_cash_flow_runway(user)

        self.stdout.write("--> Precomputing unified Dashboard Summary...")
        summary = get_dashboard_summary(user)

        # Summary output
        self.stdout.write(self.style.SUCCESS(
            "\n"
            "==========================================================\n"
            " DEMO STUDENT DATA SEEDING COMPLETE\n"
            "==========================================================\n"
            f" User: student | Password: password123\n"
            f" College Roll Number: {profile.college_roll_number}\n"
            f" Monthly Budget Limit: Rs. {profile.monthly_budget_limit:,.2f}\n"
            f" Monthly Income / Stipend: Rs. {profile.monthly_income:,.2f}\n"
            "----------------------------------------------------------\n"
            f" Transactions Created: {len(created_txs)} across 3 months (Aug - Oct)\n"
            f"   - Auto Categorized: {summary['transactions_summary']['counts']['auto']}\n"
            f"   - Needs Review Queue: {summary['transactions_summary']['needs_review_count']} (Pending + Verify)\n"
            f" Active Budget Alerts: {len(summary['budget_alerts'])}\n"
            f"   - Alert Title: {summary['budget_alerts'][0]['title'] if summary['budget_alerts'] else 'None'}\n"
            f" Financial Health Score: {health_score['total_score']}/100 (Grade: {health_score['grade']})\n"
            f" Projected Runway Date: {runway['runway_date']} ({runway['runway_days']} days)\n"
            f" Goals Created: 3 (2 Active, 1 Done)\n"
            "==========================================================\n"
            " You can now log into http://127.0.0.1:5173/ and present the demo!\n"
        ))
