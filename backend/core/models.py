import os
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
        IGNORED = "ignored", "Ignored"

    statement = models.ForeignKey(
        Statement, on_delete=models.CASCADE, related_name="transactions"
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

    # AI-categorisation fields (populated in Phase 3 & 4)
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
    OTHER = "Other", "Other"


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
