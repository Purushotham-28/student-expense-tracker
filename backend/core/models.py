import os
from datetime import date
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User


def statement_upload_path(instance, filename):
    """Store uploads under media/statements/<user_id>/<filename>."""
    return os.path.join("statements", str(instance.user.id), filename)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    college_roll_number = models.CharField(
        max_length=50, unique=True, help_text="Unique student/college roll number"
    )
    monthly_income = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Optional monthly stipend or allowance",
    )
    monthly_budget_limit = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Target spending limit per month",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.college_roll_number})"


class Statement(models.Model):
    """
    Represents a single bank/UPI statement file uploaded by a student.
    Tracks processing status and stores the original file.
    """

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="statements")
    file = models.FileField(upload_to=statement_upload_path)
    original_filename = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=10, blank=True, help_text="pdf or csv")
    bank_format = models.CharField(
        max_length=60, blank=True,
        help_text="Detected parser format name (e.g. 'hdfc_pdf', 'sbi_csv')",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PROCESSING
    )
    error_message = models.TextField(blank=True)
    transaction_count = models.IntegerField(default=0)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Statement #{self.pk} — {self.user.username} ({self.status})"


class Transaction(models.Model):
    """
    A single normalised transaction row extracted from a Statement.
    """

    class ParseStatus(models.TextChoices):
        AUTO = "auto", "Auto"
        VERIFY = "verify", "Verify"
        PENDING = "pending", "Pending"
        CATEGORISED = "categorised", "Categorised"
        CONFIRMED = "confirmed", "Confirmed"
        IGNORED = "ignored", "Ignored"

    statement = models.ForeignKey(
        Statement, on_delete=models.CASCADE, related_name="transactions",
        null=True, blank=True,
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="transactions"
    )

    # Core parsed fields
    date = models.DateField(null=True, blank=True)
    time = models.TimeField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # positive = credit, negative = debit
    is_debit = models.BooleanField(default=True)
    payee_name = models.CharField(max_length=255, blank=True)
    upi_id = models.CharField(max_length=255, blank=True)
    remark = models.CharField(max_length=512, blank=True)
    raw_text = models.TextField(blank=True)

    # Categorisation & provenance
    source = models.CharField(max_length=50, default="statement", help_text="statement, manual, chat, etc.")
    payment_mode = models.CharField(max_length=20, default="UPI", blank=True, help_text="Cash, UPI, Card, etc.")
    categorization_layer = models.CharField(max_length=50, default="ml_model", blank=True, help_text="payee_mapping, merchant_keyword, ml_model, manual")
    category = models.CharField(max_length=100, blank=True, null=True)
    confidence = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ParseStatus.choices,
        default=ParseStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        direction = "DR" if self.is_debit else "CR"
        return f"{self.date} {direction} ₹{self.amount} — {self.payee_name or self.remark}"


class ExpenseCategory(models.TextChoices):
    FOOD = "Food", "Food"
    TRAVEL = "Travel", "Travel"
    GROCERIES_SHOPPING = "Groceries/Shopping", "Groceries/Shopping"
    SUBSCRIPTIONS = "Subscriptions", "Subscriptions"
    RENT_HOSTEL = "Rent/Hostel", "Rent/Hostel"
    ACADEMICS = "Academics", "Academics"
    FRIEND_SPLIT = "Friend/Split", "Friend/Split"
    ENTERTAINMENT = "Entertainment", "Entertainment"
    UTILITIES = "Utilities", "Utilities"
    STATIONERY = "Stationery", "Stationery"
    OTHER = "Other", "Other"


class MerchantKeyword(models.Model):
    """
    Keyword/substring lookup table mapped to ExpenseCategory.
    Checked after user's PayeeMapping but before the ML classifier.
    """
    keyword = models.CharField(max_length=100, unique=True, db_index=True)
    category = models.CharField(max_length=100, choices=ExpenseCategory.choices)
    priority = models.IntegerField(default=10, help_text="Higher priority matches take precedence")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "keyword"]

    def __str__(self):
        return f"{self.keyword} -> {self.category} (priority {self.priority})"


class PayeeMapping(models.Model):
    """
    Stores user-specific category mappings for known payees or UPI IDs.
    Takes precedence over the ML categorizer with 1.0 confidence.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="payee_mappings"
    )
    payee_key = models.CharField(
        max_length=255, db_index=True,
        help_text="Normalized payee name or UPI ID",
    )
    category = models.CharField(
        max_length=100, choices=ExpenseCategory.choices,
    )
    times_confirmed = models.PositiveIntegerField(
        default=1,
        help_text="How many times the user has confirmed or assigned this mapping",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "payee_key"], name="unique_user_payee_mapping"
            )
        ]

    def __str__(self):
        return f"{self.user.username}: {self.payee_key} -> {self.category} ({self.times_confirmed}x)"


class Goal(models.Model):
    """
    Phase 6 — Goal Planner
    Allows students to track savings goals (laptop, exam fees, placement fund)
    with adaptive weekly savings targets.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DONE = "done", "Done"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="goals"
    )
    name = models.CharField(
        max_length=200, help_text="e.g. Laptop, Exam fees, Placement fund"
    )
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    saved_so_far = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    deadline = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["deadline", "-created_at"]

    @property
    def weeks_remaining(self) -> float:
        today = date.today()
        days_left = (self.deadline - today).days
        if days_left <= 0:
            return 1.0
        return max(1.0, round(days_left / 7.0, 2))

    @property
    def weekly_target(self) -> float:
        remaining = float(self.target_amount) - float(self.saved_so_far)
        if remaining <= 0 or self.status == self.Status.DONE:
            return 0.0
        return round(remaining / self.weeks_remaining, 2)

    @property
    def progress_percentage(self) -> float:
        if not self.target_amount or float(self.target_amount) <= 0:
            return 0.0
        pct = (float(self.saved_so_far) / float(self.target_amount)) * 100.0
        return round(min(100.0, max(0.0, pct)), 1)

    def contribute(self, amount: float | Decimal) -> Decimal:
        amount_dec = Decimal(str(amount))
        self.saved_so_far = self.saved_so_far + amount_dec
        if self.saved_so_far >= self.target_amount:
            self.status = self.Status.DONE
        self.save()
        return self.saved_so_far

    def __str__(self):
        return f"{self.user.username} — {self.name} (₹{self.saved_so_far}/₹{self.target_amount})"


class ChatMessage(models.Model):
    """
    Phase 8 — AI Chatbox (Claude API with Function Calling)
    Stores student conversation history and tool execution traces.
    """

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        SYSTEM = "system", "System"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="chat_messages"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    content = models.TextField()
    tool_calls = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user.username} [{self.role}]: {self.content[:40]}"
